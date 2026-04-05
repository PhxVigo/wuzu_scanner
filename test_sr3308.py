#!/usr/bin/env python3
"""
Yanzeo SR3308 Diagnostic Tester
===============================

Standalone diagnostic tool that exercises every SR3308 function wuzu-scanner
will need, with verbose step-by-step hex tracing.

Run this on a machine with the SR3308 plugged in via USB (appears as a COM
port). It will:

    1. Auto-detect which COM port has the SR3308
    2. Read device info
    3. Read base parameters (current output/work mode)
    4. Switch the reader into serial + command-polled mode
    5. Read current TX power
    6. Set TX power to 20 dBm
    7. Fire the beeper (you listen)
    8. Run inventory polls against a placed Gen2 tag

Everything printed to the console is also written to a log file
    sr3308_test_YYYYMMDD_HHMMSS.log
in the current directory. When something doesn't work, send that log back
to the developer for analysis.

Dependencies: pyserial only.
    pip install pyserial

Usage:
    python test_sr3308.py              # auto-detect port
    python test_sr3308.py COM5         # skip auto-detect, use COM5
    python test_sr3308.py /dev/ttyUSB0 # Linux

Reference: docs/yanzeo-sr3308-protocol.md
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
# Protocol constants (see docs/yanzeo-sr3308-protocol.md)
# ----------------------------------------------------------------------------
PREAMBLE_TX = 0x7C
PREAMBLE_RX = 0xCC
ADDR_BROADCAST = 0xFFFF

# Message types (host -> reader)
MSG_CMD = 0x00
MSG_SET = 0x31
MSG_GET = 0x32

# Response TYPE codes (masked with & 0x7F)
RSP_OK = 0x00
RSP_ERR = 0x01
RSP_DATA = 0x02
RSP_AUTO = 0x05

# Opcodes
CMD_INVENTORY = 0x20
CMD_GET_TX_PWR = 0x50
CMD_SET_TX_PWR = 0x51
CMD_PARA = 0x81
CMD_INFO = 0x82
CMD_SOUND = 0xBC
CMD_RESET = 0xD0

OPCODE_NAMES = {
    0x20: "READ_C_UII (inventory)",
    0x50: "GET_TX_PWR",
    0x51: "SET_TX_PWR",
    0x81: "PARA (base params)",
    0x82: "INFO (device info)",
    0xBC: "SOUND (beeper)",
    0xD0: "RESET",
}
MSGTYPE_NAMES = {
    0x00: "CMD/OK",
    0x01: "ERR",
    0x02: "DATA",
    0x05: "AUTO",
    0x31: "SET",
    0x32: "GET",
}

OUTPUTMODE_NAMES = {
    0x01: "Serial",
    0x06: "USB-HID",
    0x09: "Network",
}
WORKMODE_NAMES = {
    0x00: "Auto-read (pushes tags)",
    0x01: "Command-read (host polls)",
}

SERIAL_BAUD = 57600
SERIAL_TIMEOUT = 0.5  # seconds per read attempt
INVENTORY_POLLS = 10
INVENTORY_INTERVAL = 0.2  # seconds


# ----------------------------------------------------------------------------
# Logger — tees to stdout and log file
# ----------------------------------------------------------------------------
class Logger:
    def __init__(self, path):
        self.path = path
        self.fp = open(path, "w", encoding="utf-8")
        self.fp.write(f"SR3308 diagnostic tester — started {datetime.datetime.now().isoformat()}\n")
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
def checksum(frame_without_chk):
    return (-sum(frame_without_chk)) & 0xFF


def build_frame(code, msg_type, payload=b"", addr=ADDR_BROADCAST):
    header = bytes([
        PREAMBLE_TX,
        addr & 0xFF, (addr >> 8) & 0xFF,
        code, msg_type, len(payload),
    ])
    body = header + bytes(payload)
    return body + bytes([checksum(body)])


def verify_checksum(frame):
    return (sum(frame) & 0xFF) == 0


# ----------------------------------------------------------------------------
# Reader class
# ----------------------------------------------------------------------------
class Sr3308:
    def __init__(self, port, log, baud=SERIAL_BAUD):
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

    def send_and_receive(self, code, msg_type, payload=b"", *,
                         expect_frames=1, read_timeout=0.8):
        """Build a TX frame, send it, drain RX for read_timeout seconds,
        reassemble any 0xCC-preambled frames, and return a list of parsed frames.

        Every step of this is logged in hex so remote debugging is possible."""
        tx = build_frame(code, msg_type, payload)
        self.log.hex_line("TX", tx)
        self.log.detail(
            f"    -> code=0x{code:02X} ({OPCODE_NAMES.get(code,'?')}), "
            f"type=0x{msg_type:02X} ({MSGTYPE_NAMES.get(msg_type,'?')}), "
            f"payload_len={len(payload)}"
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
                # try to extract frames
                extracted = self._extract_frames()
                frames.extend(extracted)
                if expect_frames and len(frames) >= expect_frames:
                    # small grace period for additional frames
                    grace_end = time.time() + 0.15
                    while time.time() < grace_end:
                        more = self.ser.read(256)
                        if more:
                            raw.extend(more)
                            self.rx_buf.extend(more)
                            frames.extend(self._extract_frames())
                    break
            else:
                # no new bytes; if we already have enough, stop
                if expect_frames and len(frames) >= expect_frames:
                    break

        if raw:
            self.log.hex_line("RX", bytes(raw))
        else:
            self.log.warn("RX: (no bytes received before timeout)")

        if not frames and raw:
            self.log.warn("Bytes were received but no valid 0xCC-framed packets could be parsed")
            if self.rx_buf:
                self.log.hex_line("buf", bytes(self.rx_buf))

        for i, f in enumerate(frames):
            self._log_parsed_frame(i, f)

        return frames

    def _extract_frames(self):
        """Drain self.rx_buf of any complete frames. Returns list of dicts."""
        out = []
        while True:
            # resync to 0xCC
            try:
                idx = self.rx_buf.index(PREAMBLE_RX)
            except ValueError:
                # no preamble in buffer at all
                self.rx_buf.clear()
                return out
            if idx > 0:
                # drop garbage before preamble
                self.log.warn(f"dropping {idx} pre-preamble byte(s): "
                              + " ".join(f"{b:02X}" for b in self.rx_buf[:idx]))
                del self.rx_buf[:idx]
            if len(self.rx_buf) < 7:
                return out  # wait for more
            length = self.rx_buf[5]
            total = 7 + length
            if len(self.rx_buf) < total:
                return out  # wait for full frame
            frame = bytes(self.rx_buf[:total])
            del self.rx_buf[:total]
            if not verify_checksum(frame):
                self.log.warn(f"bad checksum on frame (dropping preamble + resyncing): "
                              + " ".join(f"{b:02X}" for b in frame))
                # dropped the bad frame; loop and try next preamble
                continue
            out.append({
                "raw": frame,
                "preamble": frame[0],
                "addr": frame[1] | (frame[2] << 8),
                "code": frame[3],
                "type": frame[4],
                "type_masked": frame[4] & 0x7F,
                "len": length,
                "payload": frame[6:6+length],
                "checksum": frame[6+length],
            })

    def _log_parsed_frame(self, idx, f):
        tm = f["type_masked"]
        tm_name = {0x00: "OK", 0x01: "ERR", 0x02: "DATA", 0x05: "AUTO"}.get(tm, "?")
        self.log.detail(
            f"    <- frame[{idx}] addr=0x{f['addr']:04X}, "
            f"code=0x{f['code']:02X} ({OPCODE_NAMES.get(f['code'],'?')}), "
            f"type=0x{f['type']:02X} (masked=0x{tm:02X}/{tm_name}), "
            f"len={f['len']}, payload="
            + (" ".join(f"{b:02X}" for b in f["payload"]) or "(empty)")
        )


# ----------------------------------------------------------------------------
# Helper: parse inventory tag record
# ----------------------------------------------------------------------------
def parse_tag_record(payload):
    length = len(payload)
    if length == 0:
        return None
    rssi = None
    if length % 2 == 0:
        rssi = payload[-1]
        length -= 1
    p = payload[:length]
    if len(p) < 3:
        return None
    i = 0
    antenna = p[i] & 0x1F
    tag_type = (p[i] & 0xE0) | 2
    i += 1
    if i < len(p) and p[i] == 0x00:
        i += 2
    if i + 2 > len(p):
        return None
    pc = p[i:i+2]
    epc_len = ((pc[0] >> 3) + 1) * 2
    if i + 2 + epc_len > len(p):
        return None
    epc = p[i+2:i+2+epc_len]
    return {
        "antenna": antenna,
        "tag_type": tag_type,
        "pc": pc.hex().upper(),
        "epc": bytes(epc).hex().upper(),
        "epc_len": epc_len,
        "rssi": rssi,
    }


# ----------------------------------------------------------------------------
# Port detection
# ----------------------------------------------------------------------------
def detect_port(log):
    log.info("Scanning COM ports for an SR3308...")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        log.fail("No serial ports detected on this machine")
        return None

    log.info(f"Found {len(ports)} port(s):")
    for p in ports:
        log.info(f"  - {p.device}  ({p.description})")

    for p in ports:
        log.info(f"  Trying {p.device} @ {SERIAL_BAUD}...")
        try:
            r = Sr3308(p.device, log)
            r.open()
        except Exception as e:
            log.warn(f"    could not open: {e}")
            continue

        try:
            frames = r.send_and_receive(CMD_INFO, MSG_GET, expect_frames=1, read_timeout=0.6)
        except Exception as e:
            log.warn(f"    send/receive error: {e}")
            r.close()
            continue

        r.close()

        for f in frames:
            if f["code"] == CMD_INFO and f["type_masked"] in (RSP_DATA, RSP_OK) and f["len"] >= 1:
                log.ok(f"SR3308 responded on {p.device}")
                return p.device

        log.detail("    no valid SR3308 response on this port")

    log.fail("No SR3308 detected on any port")
    return None


# ----------------------------------------------------------------------------
# Test steps
# ----------------------------------------------------------------------------
def step_info(r, log):
    log.step(2, 8, "Getting device info (RCP_CMD_INFO, GET)")
    frames = r.send_and_receive(CMD_INFO, MSG_GET, expect_frames=1, read_timeout=0.8)
    if not frames:
        log.fail("no response")
        return None
    f = frames[-1]
    if f["code"] != CMD_INFO:
        log.fail(f"unexpected code 0x{f['code']:02X}")
        return None
    if f["type_masked"] not in (RSP_DATA, RSP_OK):
        log.fail(f"bad response type 0x{f['type']:02X}")
        return None
    info_text = bytes(f["payload"]).decode("ascii", errors="replace").strip()
    log.ok(f'device info: "{info_text}"')
    return info_text


def step_get_params(r, log):
    log.step(3, 8, "Getting base parameters (RCP_CMD_PARA, GET)")
    frames = r.send_and_receive(CMD_PARA, MSG_GET, expect_frames=1, read_timeout=0.8)
    if not frames:
        log.fail("no response")
        return None
    f = frames[-1]
    if f["code"] != CMD_PARA or f["type_masked"] not in (RSP_DATA, RSP_OK):
        log.fail(f"bad response: code=0x{f['code']:02X}, type=0x{f['type']:02X}")
        return None
    pl = f["payload"]
    if len(pl) < 2:
        log.fail(f"payload too short ({len(pl)} bytes, need ≥2)")
        return None
    outputmode, workmode = pl[0], pl[1]
    om_name = OUTPUTMODE_NAMES.get(outputmode, f"unknown(0x{outputmode:02X})")
    wm_name = WORKMODE_NAMES.get(workmode, f"unknown(0x{workmode:02X})")
    log.ok(f"outputmode=0x{outputmode:02X} ({om_name}), workmode=0x{workmode:02X} ({wm_name})")
    return (outputmode, workmode)


def step_set_serial_mode(r, log):
    log.step(4, 8, "Switching reader to serial + command-polled mode (RCP_CMD_PARA, SET)")
    frames = r.send_and_receive(CMD_PARA, MSG_SET, payload=bytes([0x01, 0x01]),
                                expect_frames=1, read_timeout=0.8)
    if not frames:
        log.fail("no response")
        return False
    f = frames[-1]
    if f["code"] != CMD_PARA:
        log.fail(f"unexpected code 0x{f['code']:02X}")
        return False
    if f["type_masked"] == RSP_OK:
        log.ok("reader accepted the mode change")
        return True
    if f["type_masked"] == RSP_ERR:
        log.fail("reader rejected the mode change (ERR response)")
        return False
    log.warn(f"unexpected response type 0x{f['type']:02X}")
    return False


def step_get_power(r, log):
    log.step(5, 8, "Getting TX power (RCP_CMD_GET_TX_PWR, GET)")
    frames = r.send_and_receive(CMD_GET_TX_PWR, MSG_GET, expect_frames=1, read_timeout=0.8)
    if not frames:
        log.fail("no response")
        return None
    f = frames[-1]
    if f["code"] != CMD_GET_TX_PWR or f["type_masked"] not in (RSP_DATA, RSP_OK):
        log.fail(f"bad response: code=0x{f['code']:02X}, type=0x{f['type']:02X}")
        return None
    if f["len"] < 1:
        log.fail("empty payload")
        return None
    dbm = f["payload"][0]
    log.ok(f"current TX power: {dbm} dBm")
    return dbm


def step_set_power(r, log, dbm=20):
    log.step(6, 8, f"Setting TX power to {dbm} dBm (RCP_CMD_SET_TX_PWR, SET)")
    frames = r.send_and_receive(CMD_SET_TX_PWR, MSG_SET, payload=bytes([dbm]),
                                expect_frames=1, read_timeout=0.8)
    if not frames:
        log.fail("no response")
        return False
    f = frames[-1]
    if f["code"] != CMD_SET_TX_PWR:
        log.fail(f"unexpected code 0x{f['code']:02X}")
        return False
    if f["type_masked"] == RSP_OK:
        log.ok(f"TX power set to {dbm} dBm")
        return True
    if f["type_masked"] == RSP_ERR:
        log.fail("reader rejected the power change (ERR response)")
        return False
    log.warn(f"unexpected response type 0x{f['type']:02X}")
    return False


def step_beep(r, log):
    log.step(7, 8, "Testing beeper (RCP_CMD_SOUND, CMD) — 2 short beeps")
    log.info(">>> LISTEN FOR 2 SHORT BEEPS NOW <<<")
    frames = r.send_and_receive(CMD_SOUND, MSG_CMD, payload=bytes([0x02, 0x01, 0x02]),
                                expect_frames=1, read_timeout=1.5)
    if not frames:
        log.fail("no response")
        return None
    f = frames[-1]
    if f["code"] != CMD_SOUND:
        log.fail(f"unexpected code 0x{f['code']:02X}")
        return None
    if f["type_masked"] != RSP_OK:
        log.warn(f"non-OK response type 0x{f['type']:02X}")
    else:
        log.ok("reader acknowledged the beep command")
    # subjective check
    try:
        ans = input("    Did you hear the beeps? [y/N]: ").strip().lower()
    except EOFError:
        ans = ""
    log.detail(f"    user answered: {ans!r}")
    return ans.startswith("y")


def step_inventory(r, log):
    log.step(8, 8, f"Inventory polls ({INVENTORY_POLLS} rounds @ {int(INVENTORY_INTERVAL*1000)} ms)")
    log.info(">>> Place an EPC Gen2 UHF tag on the reader, then press ENTER <<<")
    try:
        input()
    except EOFError:
        pass

    seen_epcs = {}
    for poll in range(1, INVENTORY_POLLS + 1):
        log.detail(f"  Poll {poll}/{INVENTORY_POLLS}:")
        # Expect: 0..N data frames (one per tag) plus a terminating OK frame.
        # We conservatively ask for many frames with a short-ish timeout.
        frames = r.send_and_receive(CMD_INVENTORY, MSG_CMD,
                                    expect_frames=0, read_timeout=0.5)
        tag_frames = [f for f in frames
                      if f["code"] == CMD_INVENTORY and f["type_masked"] == RSP_DATA]
        for f in tag_frames:
            rec = parse_tag_record(f["payload"])
            if rec is None:
                log.warn(f"    could not parse tag record from payload: "
                         + " ".join(f"{b:02X}" for b in f["payload"]))
                continue
            log.ok(
                f"TAG: epc={rec['epc']} "
                f"(len={rec['epc_len']}), ant={rec['antenna']}, "
                f"pc={rec['pc']}, rssi={rec['rssi']}"
            )
            seen_epcs[rec["epc"]] = seen_epcs.get(rec["epc"], 0) + 1
        if not tag_frames:
            log.detail("    (no tags this poll)")
        time.sleep(INVENTORY_INTERVAL)

    log.info("")
    log.info(f"Inventory summary: {len(seen_epcs)} unique EPC(s) across {INVENTORY_POLLS} polls")
    for epc, count in seen_epcs.items():
        log.info(f"  - {epc}  (seen {count}x)")
    return seen_epcs


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"sr3308_test_{ts}.log"
    log = Logger(log_path)

    log.info("=" * 72)
    log.info("  Yanzeo SR3308 Diagnostic Tester")
    log.info("=" * 72)

    # ---------------- Step 1: port detection ----------------
    log.step(1, 8, "Detecting SR3308 on available COM ports")

    port_override = sys.argv[1] if len(sys.argv) > 1 else None
    if port_override:
        log.info(f"Using port override from command line: {port_override}")
        port = port_override
    else:
        port = detect_port(log)
        if not port:
            log.info("")
            log.info("Auto-detect failed. You can rerun with an explicit port:")
            log.info("    python test_sr3308.py COM5")
            log.info("    python test_sr3308.py /dev/ttyUSB0")
            log.close()
            sys.exit(2)

    # ---------------- Open the real session ----------------
    r = Sr3308(port, log)
    try:
        r.open()
    except Exception as e:
        log.fail(f"Could not open {port}: {e}")
        log.close()
        sys.exit(3)

    results = {"port": port}

    # ---------------- Steps 2..8 ----------------
    # Each step is wrapped so that a failure in one step doesn't abort the rest
    try:
        results["info"] = _safe(log, "INFO", step_info, r, log)
        results["params_before"] = _safe(log, "PARA GET", step_get_params, r, log)
        results["set_serial_mode"] = _safe(log, "PARA SET", step_set_serial_mode, r, log)
        # re-read params to confirm the change took effect
        log.step(4, 8, "Re-reading base parameters to confirm the change")
        results["params_after"] = _safe(log, "PARA GET (verify)", step_get_params, r, log)
        results["tx_power_before"] = _safe(log, "GET_TX_PWR", step_get_power, r, log)
        results["set_power"] = _safe(log, "SET_TX_PWR", step_set_power, r, log)
        results["beep_heard"] = _safe(log, "SOUND", step_beep, r, log)
        results["tags"] = _safe(log, "INVENTORY", step_inventory, r, log)
    finally:
        r.close()

    # ---------------- Summary ----------------
    log.info("")
    log.info("=" * 72)
    log.info("  SUMMARY")
    log.info("=" * 72)
    log.info(f"  Port:                {results.get('port')}")
    log.info(f"  Device info:         {results.get('info')}")
    log.info(f"  Params before:       {results.get('params_before')}")
    log.info(f"  Set serial+cmd mode: {results.get('set_serial_mode')}")
    log.info(f"  Params after:        {results.get('params_after')}")
    log.info(f"  TX power before:     {results.get('tx_power_before')}")
    log.info(f"  Set TX power:        {results.get('set_power')}")
    log.info(f"  Beep heard by user:  {results.get('beep_heard')}")
    tags = results.get("tags") or {}
    log.info(f"  Unique tags read:    {len(tags)}")
    for epc, count in tags.items():
        log.info(f"    - {epc}  (seen {count}x)")

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
