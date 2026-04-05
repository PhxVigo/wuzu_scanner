#!/usr/bin/env python3
"""
UR-2000 (GeeNFC UHF) Diagnostic Tester
======================================

Standalone diagnostic tool that exercises every UR-2000 function wuzu-scanner
uses, with verbose step-by-step hex tracing. Mirrors test_sr3308.py so the
two harnesses are easy to compare side-by-side.

Run this on a machine with the UR-2000 plugged in via USB (appears as a COM
port). It will:

    1. Auto-detect which COM port + baud has the UR-2000
    2. Read reader info (0x21)
    3. (skipped — no dedicated get-power opcode in our protocol)
    4. Set TX power to 20 dBm (0x2F)
    5. Fire the beeper (0x33) — you listen
    6. Run inventory polls (0x01) against a placed Gen2 tag

Everything printed to the console is also written to a log file
    ur2000_test_YYYYMMDD_HHMMSS.log
in the current directory. When something doesn't work, send that log back
to the developer for analysis.

Dependencies: pyserial only.
    pip install pyserial

Usage:
    python test_ur2000.py              # auto-detect port + baud
    python test_ur2000.py COM5         # skip auto-detect, use COM5 @ 57600
    python test_ur2000.py COM5 115200  # explicit port + baud
    python test_ur2000.py /dev/ttyUSB0 # Linux

Reference: wuzu_scanner.py (UHFReader), detect_scanners.py (probe_uhf)
"""

import sys
import time
import datetime

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial is required. Install with: pip install pyserial")
    sys.exit(1)


# ----------------------------------------------------------------------------
# Protocol constants (UR-2000 / GeeNFC)
# Frame TX: [Len, Adr=0x00, Cmd, ...data, CRC_lo, CRC_hi]  with Len = len(data)+4
# Frame RX: [Len, Adr,      Cmd, Status, ...data, CRC_lo, CRC_hi]
# CRC16: poly 0x8408, init 0xFFFF, little-endian on wire
# ----------------------------------------------------------------------------
ADDR_DEFAULT = 0x00

# Opcodes used by wuzu-scanner
CMD_INVENTORY = 0x01
CMD_INFO      = 0x21
CMD_SET_PWR   = 0x2F
CMD_BEEP      = 0x33

OPCODE_NAMES = {
    0x01: "INVENTORY",
    0x21: "GET_READER_INFO",
    0x2F: "SET_TX_PWR",
    0x33: "BEEP",
}

SERIAL_BAUDS = [57600, 115200]
DEFAULT_BAUD = 57600
SERIAL_TIMEOUT = 0.5
INVENTORY_POLLS = 10
INVENTORY_INTERVAL = 0.2


# ----------------------------------------------------------------------------
# CRC16 (poly 0x8408, init 0xFFFF)
# ----------------------------------------------------------------------------
def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else crc >> 1
    return crc


# ----------------------------------------------------------------------------
# Logger — tees to stdout and log file
# ----------------------------------------------------------------------------
class Logger:
    def __init__(self, path):
        self.path = path
        self.fp = open(path, "w", encoding="utf-8")
        self.fp.write(f"UR-2000 diagnostic tester — started {datetime.datetime.now().isoformat()}\n")
        self.fp.write(f"Python: {sys.version.split()[0]} on {sys.platform}\n")
        self.fp.write("=" * 72 + "\n")
        self.fp.flush()

    def _write(self, s):
        print(s)
        self.fp.write(s + "\n")
        self.fp.flush()

    def info(self, msg):
        self._write(msg)

    def step(self, n, total, msg):
        self._write("")
        self._write(f"[{n}/{total}] {msg}")

    def detail(self, msg):
        self._write(f"    {msg}")

    def ok(self, msg):
        self._write(f"    [OK] {msg}")

    def warn(self, msg):
        self._write(f"    [!!] {msg}")

    def fail(self, msg):
        self._write(f"    [XX] {msg}")

    def hex_line(self, label, data):
        s = " ".join(f"{b:02X}" for b in data)
        self._write(f"    {label:4s} ({len(data)} B): {s}")

    def close(self):
        self._write("")
        self._write(f"Log saved to: {self.path}")
        self.fp.close()


# ----------------------------------------------------------------------------
# Protocol helpers
# ----------------------------------------------------------------------------
def build_frame(cmd, data=b"", addr=ADDR_DEFAULT):
    length = len(data) + 4  # Len counts: Adr, Cmd, data..., CRC_lo, CRC_hi
    body = bytes([length, addr, cmd]) + bytes(data)
    c = crc16(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])


def verify_checksum(frame):
    if len(frame) < 5:
        return False
    body = frame[:-2]
    crc_got = frame[-2] | (frame[-1] << 8)
    return crc16(body) == crc_got


# ----------------------------------------------------------------------------
# Reader class
# ----------------------------------------------------------------------------
class Ur2000:
    def __init__(self, port, log, baud=DEFAULT_BAUD):
        self.port = port
        self.log = log
        self.baud = baud
        self.ser = None
        self.rx_buf = bytearray()

    def open(self):
        self.ser = serial.Serial(self.port, baudrate=self.baud,
                                 bytesize=8, parity="N", stopbits=1,
                                 timeout=SERIAL_TIMEOUT)

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def send_and_receive(self, cmd, data=b"", *,
                         expect_frames=1, read_timeout=0.8):
        """Build a TX frame, send it, drain RX for read_timeout seconds,
        reassemble any length-prefixed frames, and return a list of parsed frames.

        Every step of this is logged in hex so remote debugging is possible."""
        tx = build_frame(cmd, data)
        self.log.hex_line("TX", tx)
        self.log.detail(
            f"    -> cmd=0x{cmd:02X} ({OPCODE_NAMES.get(cmd,'?')}), "
            f"data_len={len(data)}"
        )

        self.ser.reset_input_buffer()
        self.rx_buf.clear()
        self.ser.write(tx)
        self.ser.flush()

        deadline = time.time() + read_timeout
        frames = []
        raw = bytearray()
        while time.time() < deadline:
            chunk = self.ser.read(256)
            if chunk:
                raw.extend(chunk)
                self.rx_buf.extend(chunk)
                extracted = self._extract_frames()
                frames.extend(extracted)
                if expect_frames and len(frames) >= expect_frames:
                    grace_end = time.time() + 0.15
                    while time.time() < grace_end:
                        more = self.ser.read(256)
                        if more:
                            raw.extend(more)
                            self.rx_buf.extend(more)
                            frames.extend(self._extract_frames())
                    break
            else:
                if expect_frames and len(frames) >= expect_frames:
                    break

        if raw:
            self.log.hex_line("RX", bytes(raw))
        else:
            self.log.warn("RX: (no bytes received before timeout)")

        if not frames and raw:
            self.log.warn("Bytes were received but no valid length-framed packets could be parsed")
            if self.rx_buf:
                self.log.hex_line("buf", bytes(self.rx_buf))

        for i, f in enumerate(frames):
            self._log_parsed_frame(i, f)

        return frames

    def _extract_frames(self):
        """Drain self.rx_buf of any complete frames. Returns list of dicts.

        UR-2000 frames are length-prefixed (no fixed preamble). First byte
        is Len, which counts Adr+Cmd+Status+data+CRC(2). Total frame size
        on the wire is Len+1."""
        out = []
        while True:
            if len(self.rx_buf) < 1:
                return out
            length = self.rx_buf[0]
            total = length + 1
            # sanity: Len must be at least 5 (Adr, Cmd, Status, CRC_lo, CRC_hi)
            if length < 5 or length > 250:
                self.log.warn(f"implausible length byte 0x{length:02X}, dropping 1 byte")
                del self.rx_buf[0]
                continue
            if len(self.rx_buf) < total:
                return out  # wait for full frame
            frame = bytes(self.rx_buf[:total])
            if not verify_checksum(frame):
                self.log.warn(f"bad checksum on frame (dropping 1 byte + resyncing): "
                              + " ".join(f"{b:02X}" for b in frame))
                del self.rx_buf[0]
                continue
            del self.rx_buf[:total]
            out.append({
                "raw": frame,
                "len": length,
                "addr": frame[1],
                "cmd": frame[2],
                "status": frame[3],
                "data": frame[4:-2],
                "crc": frame[-2] | (frame[-1] << 8),
            })

    def _log_parsed_frame(self, idx, f):
        self.log.detail(
            f"    <- frame[{idx}] addr=0x{f['addr']:02X}, "
            f"cmd=0x{f['cmd']:02X} ({OPCODE_NAMES.get(f['cmd'],'?')}), "
            f"status=0x{f['status']:02X}, "
            f"len={f['len']}, data="
            + (" ".join(f"{b:02X}" for b in f["data"]) or "(empty)")
        )


# ----------------------------------------------------------------------------
# Helper: parse inventory response
# Response data layout (after Status byte): [tag_count, {epc_len, ...epc}*]
# ----------------------------------------------------------------------------
def parse_inventory(data):
    if len(data) < 1:
        return []
    num = data[0]
    tags = []
    pos = 1
    for _ in range(num):
        if pos >= len(data):
            break
        epc_len = data[pos]
        pos += 1
        if pos + epc_len > len(data):
            break
        epc = data[pos:pos + epc_len]
        tags.append({
            "epc": epc.hex().upper(),
            "epc_len": epc_len,
        })
        pos += epc_len
    return tags


# ----------------------------------------------------------------------------
# Port detection
# ----------------------------------------------------------------------------
def detect_port(log):
    log.info("Scanning COM ports for a UR-2000...")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        log.fail("No serial ports detected on this machine")
        return None, None

    log.info(f"Found {len(ports)} port(s):")
    for p in ports:
        log.info(f"  - {p.device}  ({p.description})")

    for p in ports:
        for baud in SERIAL_BAUDS:
            log.info(f"  Trying {p.device} @ {baud}...")
            try:
                r = Ur2000(p.device, log, baud=baud)
                r.open()
            except Exception as e:
                log.warn(f"    could not open: {e}")
                continue

            try:
                frames = r.send_and_receive(CMD_INFO, expect_frames=1, read_timeout=0.6)
            except Exception as e:
                log.warn(f"    send/receive error: {e}")
                r.close()
                continue

            r.close()

            for f in frames:
                if f["cmd"] == CMD_INFO:
                    log.ok(f"UR-2000 responded on {p.device} @ {baud}")
                    return p.device, baud

            log.detail("    no valid UR-2000 response on this port/baud")

    log.fail("No UR-2000 detected on any port/baud")
    return None, None


# ----------------------------------------------------------------------------
# Test steps
# ----------------------------------------------------------------------------
def step_info(r, log):
    log.step(2, 7, "Getting reader info (CMD 0x21)")
    frames = r.send_and_receive(CMD_INFO, expect_frames=1, read_timeout=0.8)
    if not frames:
        log.fail("no response")
        return None
    f = frames[-1]
    if f["cmd"] != CMD_INFO:
        log.fail(f"unexpected cmd 0x{f['cmd']:02X}")
        return None
    log.ok(f"status=0x{f['status']:02X}, data={f['data'].hex().upper() or '(empty)'}")
    ascii_repr = bytes(f["data"]).decode("ascii", errors="replace").strip()
    printable = "".join(c if 32 <= ord(c) < 127 else "." for c in ascii_repr)
    if printable.strip("."):
        log.detail(f"    ascii: \"{printable}\"")
    return f["data"]


def step_get_power_stub(r, log):
    log.step(3, 7, "Get TX power — SKIPPED (UR-2000 has no dedicated get-power opcode)")
    log.detail("(wuzu-scanner doesn't query this; it only sets power. Step kept for parity with SR3308 tester.)")
    return None


def step_set_power(r, log, dbm=20):
    log.step(4, 7, f"Setting TX power to {dbm} dBm (CMD 0x2F)")
    if not 0 <= dbm <= 30:
        log.fail(f"dbm out of range 0..30: {dbm}")
        return False
    frames = r.send_and_receive(CMD_SET_PWR, data=bytes([dbm]),
                                expect_frames=1, read_timeout=0.8)
    if not frames:
        log.fail("no response")
        return False
    f = frames[-1]
    if f["cmd"] != CMD_SET_PWR:
        log.fail(f"unexpected cmd 0x{f['cmd']:02X}")
        return False
    if f["status"] == 0x00:
        log.ok(f"TX power set to {dbm} dBm (status=0x00)")
        return True
    log.warn(f"non-zero status 0x{f['status']:02X} — power may or may not have taken")
    return False


def step_beep(r, log):
    log.step(5, 7, "Testing beeper (CMD 0x33) — 2 short beeps")
    log.info(">>> LISTEN FOR 2 SHORT BEEPS NOW <<<")
    frames = r.send_and_receive(CMD_BEEP, data=bytes([0x02, 0x01, 0x02]),
                                expect_frames=1, read_timeout=1.5)
    if not frames:
        log.fail("no response")
        return None
    f = frames[-1]
    if f["cmd"] != CMD_BEEP:
        log.fail(f"unexpected cmd 0x{f['cmd']:02X}")
        return None
    if f["status"] != 0x00:
        log.warn(f"non-zero status 0x{f['status']:02X}")
    else:
        log.ok("reader acknowledged the beep command")
    try:
        ans = input("    Did you hear the beeps? [y/N]: ").strip().lower()
    except EOFError:
        ans = ""
    log.detail(f"    user answered: {ans!r}")
    return ans.startswith("y")


def step_inventory(r, log):
    log.step(6, 7, f"Inventory polls ({INVENTORY_POLLS} rounds @ {int(INVENTORY_INTERVAL*1000)} ms)")
    log.info(">>> Place an EPC Gen2 UHF tag on the reader, then press ENTER <<<")
    try:
        input()
    except EOFError:
        pass

    seen_epcs = {}
    for poll in range(1, INVENTORY_POLLS + 1):
        log.detail(f"  Poll {poll}/{INVENTORY_POLLS}:")
        frames = r.send_and_receive(CMD_INVENTORY, expect_frames=1, read_timeout=0.5)
        inv_frames = [f for f in frames if f["cmd"] == CMD_INVENTORY]
        got_any = False
        for f in inv_frames:
            tags = parse_inventory(f["data"])
            if not tags:
                log.detail(f"    (empty inventory frame, status=0x{f['status']:02X})")
                continue
            got_any = True
            for t in tags:
                log.ok(f"TAG: epc={t['epc']} (len={t['epc_len']})")
                seen_epcs[t["epc"]] = seen_epcs.get(t["epc"], 0) + 1
        if not inv_frames:
            log.detail("    (no inventory response)")
        elif not got_any:
            log.detail("    (no tags this poll)")
        time.sleep(INVENTORY_INTERVAL)

    log.info("")
    log.info(f"Inventory summary: {len(seen_epcs)} unique EPC(s) across {INVENTORY_POLLS} polls")
    for epc, count in seen_epcs.items():
        log.info(f"  - {epc}  (seen {count}x)")
    return seen_epcs


def step_final_info(r, log):
    log.step(7, 7, "Re-reading reader info to confirm link still healthy")
    frames = r.send_and_receive(CMD_INFO, expect_frames=1, read_timeout=0.8)
    if not frames:
        log.fail("no response")
        return False
    log.ok("link still alive")
    return True


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"ur2000_test_{ts}.log"
    log = Logger(log_path)

    log.info("=" * 72)
    log.info("  UR-2000 (GeeNFC UHF) Diagnostic Tester")
    log.info("=" * 72)

    # ---------------- Step 1: port detection ----------------
    log.step(1, 7, "Detecting UR-2000 on available COM ports")

    port_override = sys.argv[1] if len(sys.argv) > 1 else None
    baud_override = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if port_override:
        port = port_override
        baud = baud_override or DEFAULT_BAUD
        log.info(f"Using override from command line: {port} @ {baud}")
    else:
        port, baud = detect_port(log)
        if not port:
            log.info("")
            log.info("Auto-detect failed. You can rerun with an explicit port:")
            log.info("    python test_ur2000.py COM5")
            log.info("    python test_ur2000.py COM5 115200")
            log.info("    python test_ur2000.py /dev/ttyUSB0")
            log.close()
            sys.exit(2)

    # ---------------- Open the real session ----------------
    r = Ur2000(port, log, baud=baud)
    try:
        r.open()
    except Exception as e:
        log.fail(f"Could not open {port} @ {baud}: {e}")
        log.close()
        sys.exit(3)

    results = {"port": port, "baud": baud}

    # ---------------- Steps 2..7 ----------------
    try:
        results["info"]             = _safe(log, "INFO",       step_info,            r, log)
        results["get_power"]        = _safe(log, "GET_PWR",    step_get_power_stub,  r, log)
        results["set_power"]        = _safe(log, "SET_PWR",    step_set_power,       r, log)
        results["beep_heard"]       = _safe(log, "BEEP",       step_beep,            r, log)
        results["tags"]             = _safe(log, "INVENTORY",  step_inventory,       r, log)
        results["final_info_ok"]    = _safe(log, "INFO (end)", step_final_info,      r, log)
    finally:
        r.close()

    # ---------------- Summary ----------------
    log.info("")
    log.info("=" * 72)
    log.info("  SUMMARY")
    log.info("=" * 72)
    log.info(f"  Port:                {results.get('port')} @ {results.get('baud')}")
    info_data = results.get('info')
    if info_data is not None:
        log.info(f"  Reader info:         {bytes(info_data).hex().upper()}")
    else:
        log.info(f"  Reader info:         (none)")
    log.info(f"  Get TX power:        (skipped — no opcode)")
    log.info(f"  Set TX power:        {results.get('set_power')}")
    log.info(f"  Beep heard by user:  {results.get('beep_heard')}")
    tags = results.get("tags") or {}
    log.info(f"  Unique tags read:    {len(tags)}")
    for epc, count in tags.items():
        log.info(f"    - {epc}  (seen {count}x)")
    log.info(f"  Final info probe OK: {results.get('final_info_ok')}")

    log.close()


def _safe(log, label, fn, *args, **kwargs):
    """Run a step, catch and log exceptions, return None on failure."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        log.fail(f"[{label}] exception: {type(e).__name__}: {e}")
        import traceback
        for line in traceback.format_exc().splitlines():
            log.detail(f"    {line}")
        return None


if __name__ == "__main__":
    main()
