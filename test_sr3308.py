#!/usr/bin/env python3
"""
Yanzeo SR3308 Diagnostic Tester
===============================

Standalone diagnostic tool that exercises every SR3308 function wuzu-scanner
will need, with verbose step-by-step hex tracing.

Run this on a machine with the SR3308 plugged in via USB. The reader
defaults to USB-HID mode, so this script tries HID first, switches the
reader to serial + command-polled mode, then reconnects over serial and
runs the remaining tests.

    1. Auto-detect the SR3308 (HID first, then serial fallback)
    2. Read device info
    3. Read base parameters (current output/work mode)
    4. Switch the reader into serial + command-polled mode
       (auto-reconnects over serial after the switch)
    5. Verify the mode change
    6. Read current TX power
    7. Set TX power to 20 dBm
    8. Fire the beeper (you listen)
    9. Run inventory polls against a placed Gen2 tag

Everything printed to the console is also written to a log file
    sr3308_test_YYYYMMDD_HHMMSS.log
in the current directory. When something doesn't work, send that log back
to the developer for analysis.

Dependencies:
    pip install pyserial

For HID support (recommended — needed if reader is in default HID mode):
    sudo apt install libhidapi-dev    # Linux / Raspberry Pi
    pip install hidapi

Usage:
    python test_sr3308.py                 # auto-detect (HID first, then serial)
    python test_sr3308.py --hid           # force HID-only detection
    python test_sr3308.py --serial        # force serial-only detection
    python test_sr3308.py /dev/ttyUSB0    # use explicit serial port
    python test_sr3308.py COM5            # Windows explicit port

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

# HID support is optional — gracefully degrade if not available
try:
    import hid as hidapi
    HID_AVAILABLE = True
except ImportError:
    HID_AVAILABLE = False


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

# HID report size (typical for USB full-speed HID)
HID_REPORT_SIZE = 64


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


def extract_frames(rx_buf, log=None):
    """Extract complete RCP frames from a byte buffer.

    Modifies rx_buf in place (removes consumed bytes).
    Returns list of parsed frame dicts.
    """
    out = []
    while True:
        try:
            idx = rx_buf.index(PREAMBLE_RX)
        except ValueError:
            rx_buf.clear()
            return out
        if idx > 0:
            if log:
                log.warn(f"dropping {idx} pre-preamble byte(s): "
                         + " ".join(f"{b:02X}" for b in rx_buf[:idx]))
            del rx_buf[:idx]
        if len(rx_buf) < 7:
            return out
        length = rx_buf[5]
        total = 7 + length
        if len(rx_buf) < total:
            return out
        frame = bytes(rx_buf[:total])
        del rx_buf[:total]
        if not verify_checksum(frame):
            if log:
                log.warn(f"bad checksum on frame (dropping preamble + resyncing): "
                         + " ".join(f"{b:02X}" for b in frame))
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


def log_parsed_frame(log, idx, f):
    tm = f["type_masked"]
    tm_name = {0x00: "OK", 0x01: "ERR", 0x02: "DATA", 0x05: "AUTO"}.get(tm, "?")
    log.detail(
        f"    <- frame[{idx}] addr=0x{f['addr']:04X}, "
        f"code=0x{f['code']:02X} ({OPCODE_NAMES.get(f['code'],'?')}), "
        f"type=0x{f['type']:02X} (masked=0x{tm:02X}/{tm_name}), "
        f"len={f['len']}, payload="
        + (" ".join(f"{b:02X}" for b in f["payload"]) or "(empty)")
    )


# ----------------------------------------------------------------------------
# Transport layer — abstract send/receive over HID or Serial
# ----------------------------------------------------------------------------
class SerialTransport:
    """Wraps pyserial for RCP communication."""
    name = "serial"

    def __init__(self, port, baud=SERIAL_BAUD):
        self.port = port
        self.baud = baud
        self.ser = None

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

    def send(self, data):
        self.ser.reset_input_buffer()
        self.ser.write(data)
        self.ser.flush()

    def receive(self, timeout=0.8):
        """Read bytes until timeout. Returns raw bytearray."""
        buf = bytearray()
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = self.ser.read(256)
            if chunk:
                buf.extend(chunk)
            elif buf:
                # got data, then silence — give a short grace period
                grace = time.time() + 0.15
                while time.time() < grace:
                    more = self.ser.read(256)
                    if more:
                        buf.extend(more)
                break
        return buf

    @property
    def description(self):
        return f"serial:{self.port}@{self.baud}"


class HidTransport:
    """Wraps hidapi for RCP communication over USB HID."""
    name = "hid"

    def __init__(self, device_path, vid=0, pid=0):
        self.device_path = device_path
        self.vid = vid
        self.pid = pid
        self.dev = None

    def open(self):
        self.dev = hidapi.device()
        self.dev.open_path(self.device_path)
        self.dev.set_nonblocking(True)

    def close(self):
        if self.dev:
            try:
                self.dev.close()
            except Exception:
                pass
            self.dev = None

    def send(self, data):
        """Send RCP frame wrapped in an HID report.

        HID reports: prepend 0x00 report ID, then the RCP frame bytes,
        pad with 0x00 to HID_REPORT_SIZE.
        """
        report = bytearray(HID_REPORT_SIZE)
        report[0] = 0x00  # report ID
        report[1:1+len(data)] = data
        self.dev.write(bytes(report))

    def receive(self, timeout=0.8):
        """Read HID reports until timeout, strip padding, return raw bytes."""
        buf = bytearray()
        deadline = time.time() + timeout
        while time.time() < deadline:
            report = self.dev.read(HID_REPORT_SIZE)
            if report:
                # Strip trailing zero padding — RCP frames are shorter than
                # the full report. We keep everything up to the last non-zero
                # byte (or all of it if the frame legitimately contains zeros
                # in the payload). The frame parser will handle validation.
                buf.extend(bytes(report))
                # Check if we have a plausible complete frame already
                if PREAMBLE_RX in buf:
                    # give a short grace for any follow-up reports
                    grace = time.time() + 0.15
                    while time.time() < grace:
                        more = self.dev.read(HID_REPORT_SIZE)
                        if more:
                            buf.extend(bytes(more))
                    break
            else:
                time.sleep(0.01)  # brief sleep to avoid busy-waiting
        return buf

    @property
    def description(self):
        return f"hid:{self.vid:04X}:{self.pid:04X} ({self.device_path})"


# ----------------------------------------------------------------------------
# Reader class — transport-agnostic
# ----------------------------------------------------------------------------
class Sr3308:
    def __init__(self, transport, log):
        self.transport = transport
        self.log = log
        self.rx_buf = bytearray()

    def open(self):
        self.transport.open()

    def close(self):
        self.transport.close()

    def send_and_receive(self, code, msg_type, payload=b"", *,
                         expect_frames=1, read_timeout=0.8):
        """Build a TX frame, send it, drain RX, reassemble any 0xCC-preambled
        frames, and return a list of parsed frames.

        Every step of this is logged in hex so remote debugging is possible."""
        tx = build_frame(code, msg_type, payload)
        self.log.hex_line("TX", tx)
        self.log.detail(
            f"    -> code=0x{code:02X} ({OPCODE_NAMES.get(code,'?')}), "
            f"type=0x{msg_type:02X} ({MSGTYPE_NAMES.get(msg_type,'?')}), "
            f"payload_len={len(payload)}"
        )

        self.rx_buf.clear()
        raw = self.transport.receive(timeout=0.05)  # flush any stale data
        self.transport.send(tx)
        raw = self.transport.receive(timeout=read_timeout)

        if raw:
            self.log.hex_line("RX", bytes(raw))
        else:
            self.log.warn("RX: (no bytes received before timeout)")

        self.rx_buf.extend(raw)
        frames = extract_frames(self.rx_buf, self.log)

        if not frames and raw:
            self.log.warn("Bytes were received but no valid 0xCC-framed packets could be parsed")
            if self.rx_buf:
                self.log.hex_line("buf", bytes(self.rx_buf))

        for i, f in enumerate(frames):
            log_parsed_frame(self.log, i, f)

        return frames


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
# HID device discovery
# ----------------------------------------------------------------------------
def detect_hid(log):
    """Enumerate HID devices and probe each with an INFO GET command.

    Returns an HidTransport connected to the SR3308, or None.
    """
    if not HID_AVAILABLE:
        log.warn("hidapi not installed — skipping HID detection")
        log.detail("Install for HID support:")
        log.detail("  sudo apt install libhidapi-dev   # Linux / Raspberry Pi")
        log.detail("  pip install hidapi")
        return None

    log.info("Enumerating USB HID devices...")
    try:
        devices = hidapi.enumerate()
    except Exception as e:
        log.warn(f"HID enumeration failed: {e}")
        return None

    if not devices:
        log.info("  No HID devices found")
        return None

    log.info(f"  Found {len(devices)} HID interface(s):")
    for d in devices:
        vid, pid = d.get("vendor_id", 0), d.get("product_id", 0)
        mfg = d.get("manufacturer_string", "") or ""
        prod = d.get("product_string", "") or ""
        path = d.get("path", b"")
        log.info(f"    VID={vid:04X} PID={pid:04X} mfg={mfg!r} prod={prod!r}")
        log.detail(f"    path={path}")

    # Try each HID device — send INFO GET and look for a valid RCP response
    for d in devices:
        vid = d.get("vendor_id", 0)
        pid = d.get("product_id", 0)
        path = d.get("path", b"")
        mfg = d.get("manufacturer_string", "") or ""
        prod = d.get("product_string", "") or ""

        log.info(f"  Probing VID={vid:04X} PID={pid:04X} ({mfg} {prod})...")

        transport = HidTransport(path, vid, pid)
        try:
            transport.open()
        except Exception as e:
            log.detail(f"    could not open: {e}")
            continue

        # Send INFO GET and see if we get a valid RCP frame back
        info_frame = build_frame(CMD_INFO, MSG_GET)
        log.hex_line("TX", info_frame)
        try:
            transport.send(info_frame)
            raw = transport.receive(timeout=1.0)
        except Exception as e:
            log.detail(f"    send/receive error: {e}")
            transport.close()
            continue

        if raw:
            log.hex_line("RX", bytes(raw))
        else:
            log.detail("    no response")
            transport.close()
            continue

        # Try to parse RCP frames from the response
        rx_buf = bytearray(raw)
        frames = extract_frames(rx_buf, log)
        for f in frames:
            if f["code"] == CMD_INFO and f["type_masked"] in (RSP_DATA, RSP_OK) and f["len"] >= 1:
                info_text = bytes(f["payload"]).decode("ascii", errors="replace").strip()
                log.ok(f"SR3308 found via HID! VID={vid:04X} PID={pid:04X}")
                log.ok(f"Device info: {info_text!r}")
                return transport

        log.detail("    valid HID device but not an SR3308 (no INFO response)")
        transport.close()

    log.info("  No SR3308 found via HID")
    return None


# ----------------------------------------------------------------------------
# Serial port detection
# ----------------------------------------------------------------------------
def detect_serial(log):
    """Scan COM ports for an SR3308. Returns a SerialTransport or None."""
    log.info("Scanning serial/COM ports for an SR3308...")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        log.fail("No serial ports detected on this machine")
        return None

    log.info(f"Found {len(ports)} port(s):")
    for p in ports:
        log.info(f"  - {p.device}  ({p.description})")

    for p in ports:
        log.info(f"  Trying {p.device} @ {SERIAL_BAUD}...")
        transport = SerialTransport(p.device)
        try:
            transport.open()
        except Exception as e:
            log.warn(f"    could not open: {e}")
            continue

        reader = Sr3308(transport, log)
        try:
            frames = reader.send_and_receive(CMD_INFO, MSG_GET,
                                             expect_frames=1, read_timeout=0.6)
        except Exception as e:
            log.warn(f"    send/receive error: {e}")
            transport.close()
            continue

        for f in frames:
            if f["code"] == CMD_INFO and f["type_masked"] in (RSP_DATA, RSP_OK) and f["len"] >= 1:
                log.ok(f"SR3308 responded on {p.device}")
                return transport

        log.detail("    no valid SR3308 response on this port")
        transport.close()

    log.fail("No SR3308 detected on any serial port")
    return None


def wait_for_serial_reconnect(log, max_wait=10):
    """After switching from HID to serial mode, wait for the device to
    re-enumerate as a serial port and return a SerialTransport.

    Polls every second for up to max_wait seconds.
    """
    log.info(f"Waiting up to {max_wait}s for the reader to re-appear as a serial port...")

    for elapsed in range(max_wait):
        time.sleep(1)
        log.detail(f"  ({elapsed+1}s) scanning ports...")
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            # Skip well-known built-in ports that aren't USB
            if p.device in ("/dev/ttyS0", "/dev/ttyAMA0"):
                continue
            log.detail(f"    trying {p.device} ({p.description})...")
            transport = SerialTransport(p.device)
            try:
                transport.open()
            except Exception:
                continue
            reader = Sr3308(transport, log)
            try:
                frames = reader.send_and_receive(CMD_INFO, MSG_GET,
                                                 expect_frames=1, read_timeout=0.6)
            except Exception:
                transport.close()
                continue
            for f in frames:
                if f["code"] == CMD_INFO and f["type_masked"] in (RSP_DATA, RSP_OK) and f["len"] >= 1:
                    log.ok(f"SR3308 reconnected on {p.device}")
                    return transport
            transport.close()

    log.fail("SR3308 did not appear on any serial port after mode switch")
    return None


# ----------------------------------------------------------------------------
# Test steps
# ----------------------------------------------------------------------------
TOTAL_STEPS = 9


def step_info(r, log):
    log.step(2, TOTAL_STEPS, "Getting device info (RCP_CMD_INFO, GET)")
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


def step_get_params(r, log, step_num=3):
    log.step(step_num, TOTAL_STEPS, "Getting base parameters (RCP_CMD_PARA, GET)")
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
        log.fail(f"payload too short ({len(pl)} bytes, need >= 2)")
        return None
    outputmode, workmode = pl[0], pl[1]
    om_name = OUTPUTMODE_NAMES.get(outputmode, f"unknown(0x{outputmode:02X})")
    wm_name = WORKMODE_NAMES.get(workmode, f"unknown(0x{workmode:02X})")
    log.ok(f"outputmode=0x{outputmode:02X} ({om_name}), workmode=0x{workmode:02X} ({wm_name})")
    return (outputmode, workmode)


def step_set_serial_mode(r, log):
    log.step(4, TOTAL_STEPS, "Switching reader to serial + command-polled mode (RCP_CMD_PARA, SET)")
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
    log.step(6, TOTAL_STEPS, "Getting TX power (RCP_CMD_GET_TX_PWR, GET)")
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
    log.step(7, TOTAL_STEPS, f"Setting TX power to {dbm} dBm (RCP_CMD_SET_TX_PWR, SET)")
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
    log.step(8, TOTAL_STEPS, "Testing beeper (RCP_CMD_SOUND, CMD) — 2 short beeps")
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
    try:
        ans = input("    Did you hear the beeps? [y/N]: ").strip().lower()
    except EOFError:
        ans = ""
    log.detail(f"    user answered: {ans!r}")
    return ans.startswith("y")


def step_inventory(r, log):
    log.step(9, TOTAL_STEPS, f"Inventory polls ({INVENTORY_POLLS} rounds @ {int(INVENTORY_INTERVAL*1000)} ms)")
    log.info(">>> Place an EPC Gen2 UHF tag on the reader, then press ENTER <<<")
    try:
        input()
    except EOFError:
        pass

    seen_epcs = {}
    for poll in range(1, INVENTORY_POLLS + 1):
        log.detail(f"  Poll {poll}/{INVENTORY_POLLS}:")
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

    # Parse CLI arguments
    force_hid = "--hid" in sys.argv
    force_serial = "--serial" in sys.argv
    port_override = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            port_override = arg
            break

    # ---------------- Step 1: detection ----------------
    log.step(1, TOTAL_STEPS, "Detecting SR3308")

    transport = None
    connected_via_hid = False

    if port_override:
        # Explicit serial port
        log.info(f"Using explicit serial port from command line: {port_override}")
        transport = SerialTransport(port_override)
    elif force_serial:
        log.info("Forced serial-only detection (--serial)")
        transport = detect_serial(log)
    elif force_hid:
        log.info("Forced HID-only detection (--hid)")
        transport = detect_hid(log)
        if transport:
            connected_via_hid = True
    else:
        # Default: try HID first, then fall back to serial
        log.info("Trying HID detection first (reader defaults to USB-HID mode)...")
        transport = detect_hid(log)
        if transport:
            connected_via_hid = True
        else:
            log.info("")
            log.info("HID detection failed — falling back to serial port scan...")
            transport = detect_serial(log)

    if not transport:
        log.info("")
        log.info("Could not find an SR3308 on any interface.")
        log.info("")
        log.info("Troubleshooting:")
        log.info("  1. Is the SR3308 plugged in via USB?")
        log.info("       lsusb                         # should show the device")
        log.info("  2. Check for HID devices:")
        log.info("       ls /dev/hidraw*")
        log.info("  3. Check for serial devices:")
        log.info("       ls /dev/ttyUSB* /dev/ttyACM*")
        log.info("  4. Permissions — add your user to the input and dialout groups:")
        log.info("       sudo usermod -aG input,dialout $USER")
        log.info("       (then log out and back in)")
        if not HID_AVAILABLE:
            log.info("  5. Install hidapi for HID support:")
            log.info("       sudo apt install libhidapi-dev")
            log.info("       pip install hidapi")
        log.info("")
        log.info("You can also rerun with an explicit port:")
        log.info("    python test_sr3308.py /dev/ttyUSB0")
        log.close()
        sys.exit(2)

    # ---------------- Open session ----------------
    if port_override:
        # Explicit port — need to open it
        try:
            transport.open()
        except Exception as e:
            log.fail(f"Could not open {port_override}: {e}")
            log.close()
            sys.exit(3)

    r = Sr3308(transport, log)
    log.ok(f"Connected via {transport.description}")

    results = {"transport": transport.description}

    # ---------------- Steps 2..9 ----------------
    try:
        # Step 2: device info
        results["info"] = _safe(log, "INFO", step_info, r, log)

        # Step 3: read current params
        results["params_before"] = _safe(log, "PARA GET", step_get_params, r, log, step_num=3)

        # Step 4: switch to serial + command mode
        if connected_via_hid:
            log.info("")
            log.info("    Reader is connected via HID — will switch to serial mode")
            log.info("    and reconnect over serial for remaining tests.")
            mode_ok = _safe(log, "PARA SET", step_set_serial_mode, r, log)
            results["set_serial_mode"] = mode_ok

            if mode_ok:
                # Close HID, wait for serial re-enumeration, reconnect
                log.info("")
                log.info("    Closing HID connection...")
                r.close()
                time.sleep(2)  # give the device a moment to re-enumerate

                serial_transport = wait_for_serial_reconnect(log, max_wait=10)
                if serial_transport:
                    transport = serial_transport
                    r = Sr3308(transport, log)
                    connected_via_hid = False
                    log.ok(f"Reconnected via {transport.description}")
                else:
                    log.fail("Could not reconnect over serial after mode switch.")
                    log.info("    The mode change may still have worked. Try rerunning:")
                    log.info("    python test_sr3308.py")
                    log.close()
                    sys.exit(4)
            else:
                log.warn("Mode switch failed or was rejected — continuing tests over HID")
        else:
            # Already on serial — still send the mode set to ensure correct config
            results["set_serial_mode"] = _safe(log, "PARA SET", step_set_serial_mode, r, log)

        # Step 5: verify params
        results["params_after"] = _safe(log, "PARA GET (verify)", step_get_params, r, log, step_num=5)

        # Steps 6-9: power, beep, inventory
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
    log.info(f"  Transport:           {results.get('transport')}")
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
