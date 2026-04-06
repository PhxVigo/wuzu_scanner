# detect_scanners.py
"""
WUZU Scanner Auto-Detect Tool
Detects attached UHF and NFC readers, offers to update config.toml.

Supports:
  - GeeNFC UR-2000 (serial/COM port)
  - Yanzeo SR3308 (USB HID)
  - NFC readers via PC/SC (e.g., ACR122U)
"""

import os
import sys
import re
import time
import platform


# =============================================================================
# CRC16 (same algorithm as wuzu_scanner.py UHFReader, for UR-2000)
# =============================================================================
def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else crc >> 1
    return crc


# =============================================================================
# SR3308 RCP protocol helpers (minimal inline subset)
# =============================================================================
_SR3308_PREAMBLE_TX = 0x7C
_SR3308_PREAMBLE_RX = 0xCC
_SR3308_VID = 0x04D8
_SR3308_PID = 0x033F
_SR3308_CMD_INFO = 0x82
_SR3308_CMD_PARA = 0x81
_SR3308_CMD_USB = 0xBD
_SR3308_MSG_CMD = 0x00
_SR3308_MSG_SET = 0x31
_SR3308_MSG_GET = 0x32


def _sr3308_checksum(frame_without_chk):
    return (-sum(frame_without_chk)) & 0xFF


def _sr3308_build_frame(code, msg_type, payload=b""):
    header = bytes([
        _SR3308_PREAMBLE_TX,
        0xFF, 0xFF,  # broadcast address
        code, msg_type, len(payload),
    ])
    body = header + bytes(payload)
    return body + bytes([_sr3308_checksum(body)])


def _sr3308_extract_frames(buf):
    """Extract complete RCP frames from a byte buffer. Returns list of dicts."""
    out = []
    while True:
        try:
            idx = buf.index(_SR3308_PREAMBLE_RX)
        except ValueError:
            buf.clear()
            return out
        if idx > 0:
            del buf[:idx]
        if len(buf) < 7:
            return out
        length = buf[5]
        total = 7 + length
        if len(buf) < total:
            return out
        frame = bytes(buf[:total])
        del buf[:total]
        if (sum(frame) & 0xFF) != 0:
            continue
        out.append({
            "code": frame[3],
            "type_masked": frame[4] & 0x7F,
            "len": length,
            "payload": frame[6:6+length],
        })


def _sr3308_hid_send_receive(dev, rcp_frame, timeout=1.0):
    """Send an RCP frame in a length-prefixed HID report and read the response."""
    report = bytearray(64)
    report[0] = 0x00  # report ID
    report[1] = len(rcp_frame)
    report[2:2+len(rcp_frame)] = rcp_frame
    dev.write(bytes(report))

    buf = bytearray()
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = dev.read(64)
        if data:
            valid_len = data[0]
            if 0 < valid_len < len(data):
                buf.extend(bytes(data[1:1+valid_len]))
            if _SR3308_PREAMBLE_RX in buf:
                grace = time.time() + 0.15
                while time.time() < grace:
                    more = dev.read(64)
                    if more:
                        vl = more[0]
                        if 0 < vl < len(more):
                            buf.extend(bytes(more[1:1+vl]))
                break
        else:
            time.sleep(0.01)

    return _sr3308_extract_frames(buf)


# =============================================================================
# UHF Detection — UR-2000 (serial)
# =============================================================================
def probe_uhf(port, baudrate, timeout=0.5):
    """
    Probe a serial port for a UR-2000 UHF reader by sending
    the Get Reader Info command (0x21).
    Returns True if a valid response is received.
    """
    try:
        import serial
    except ImportError:
        return False

    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
        )
        time.sleep(0.1)
        ser.reset_input_buffer()

        # Build Get Reader Info command: Len=0x04, Adr=0x00, Cmd=0x21
        cmd_data = bytes([0x04, 0x00, 0x21])
        crc = crc16(cmd_data)
        frame = cmd_data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

        ser.write(frame)
        ser.flush()

        # Read response
        time.sleep(0.3)
        response = b''
        start = time.time()
        while time.time() - start < timeout:
            if ser.in_waiting > 0:
                response += ser.read(ser.in_waiting)
                time.sleep(0.05)
            elif len(response) > 0:
                break
            else:
                time.sleep(0.02)

        ser.close()

        # Validate: minimum frame is 5 bytes (Len, Adr, Cmd, Status, CRC16)
        if len(response) >= 5:
            payload = response[:-2]
            crc_recv = int.from_bytes(response[-2:], "little")
            if crc16(payload) == crc_recv:
                return True

        return False

    except Exception:
        return False


def detect_uhf_serial():
    """
    Scan all serial ports for UR-2000 UHF readers.
    Returns list of dicts: [{'port': str, 'baudrate': int, 'description': str, 'type': 'ur2000'}]
    """
    try:
        import serial.tools.list_ports
    except ImportError:
        print("  pyserial not installed - cannot detect serial UHF readers.")
        print("  Install with: pip install pyserial")
        return []

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("  No serial ports found.")
        return []

    found = []
    baudrates = [57600, 115200]

    for port_info in ports:
        port = port_info.device
        desc = port_info.description or "Unknown"

        for baud in baudrates:
            status = f"  {port:<8} - {desc:<40} "
            sys.stdout.write(status)
            sys.stdout.flush()

            if probe_uhf(port, baud):
                print(f"--> UR-2000 DETECTED ({baud} baud)")
                found.append({
                    'port': port,
                    'baudrate': baud,
                    'description': desc,
                    'type': 'ur2000',
                })
                break
            else:
                print(f"--> No response ({baud} baud)")

    return found


# =============================================================================
# UHF Detection — SR3308 (USB HID)
# =============================================================================
def detect_uhf_hid():
    """
    Scan USB HID devices for an SR3308 UHF reader.
    Returns list of dicts: [{'path': bytes, 'vid': int, 'pid': int,
                             'info': str, 'usb_mode': int, 'type': 'sr3308'}]
    """
    try:
        import hid as hidapi
    except ImportError:
        print("  hidapi not installed - cannot detect HID UHF readers.")
        print("  Install with:")
        if platform.system() == "Linux":
            print("    sudo apt install libhidapi-dev")
        print("    pip install hidapi")
        return []

    try:
        devices = hidapi.enumerate()
    except Exception as e:
        print(f"  HID enumeration error: {e}")
        return []

    # Filter to known SR3308 VID/PID
    candidates = [d for d in devices
                  if d.get("vendor_id") == _SR3308_VID
                  and d.get("product_id") == _SR3308_PID]

    if not candidates:
        print("  No SR3308 HID devices found.")
        return []

    found = []
    for d in candidates:
        path = d.get("path", b"")
        iface = d.get("interface_number", -1)
        prod = d.get("product_string", "") or ""

        sys.stdout.write(f"  VID={_SR3308_VID:04X} PID={_SR3308_PID:04X} iface={iface} ({prod}) ")
        sys.stdout.flush()

        try:
            dev = hidapi.device()
            dev.open_path(path)
            dev.set_nonblocking(True)
            time.sleep(0.1)  # settle time after open
        except Exception as e:
            print(f"--> could not open: {e}")
            continue

        # Send INFO GET
        info_frame = _sr3308_build_frame(_SR3308_CMD_INFO, _SR3308_MSG_GET)
        frames = _sr3308_hid_send_receive(dev, info_frame, timeout=1.0)

        info_text = None
        for f in frames:
            if f["code"] == _SR3308_CMD_INFO and f["type_masked"] in (0x00, 0x02) and f["len"] >= 1:
                info_text = bytes(f["payload"]).decode("ascii", errors="replace").strip()
                break

        if info_text is None:
            print("--> no valid response")
            try:
                dev.close()
            except Exception:
                pass
            continue

        # Read USB mode
        usb_frame = _sr3308_build_frame(_SR3308_CMD_USB, _SR3308_MSG_GET)
        usb_frames = _sr3308_hid_send_receive(dev, usb_frame, timeout=0.8)
        usb_mode = None
        for f in usb_frames:
            if f["code"] == _SR3308_CMD_USB and f["type_masked"] == 0x00 and f["len"] >= 1:
                usb_mode = f["payload"][0]
                break

        try:
            dev.close()
        except Exception:
            pass

        usb_mode_name = {0: "HID+KBD", 1: "HID+KBD+CDC", 2: "HID-only"}.get(usb_mode, "?")
        print(f"--> SR3308 DETECTED (USB mode={usb_mode} {usb_mode_name})")
        print(f"       info: {info_text}")

        found.append({
            'path': path,
            'vid': _SR3308_VID,
            'pid': _SR3308_PID,
            'info': info_text,
            'usb_mode': usb_mode,
            'type': 'sr3308',
        })
        break  # only need to find one; skip the second interface

    return found


# =============================================================================
# SR3308 — disable keyboard interface
# =============================================================================
def sr3308_disable_keyboard(path):
    """
    Switch an SR3308 to HID-only mode (USB mode 2), disabling the keyboard
    interface that causes phantom typing.

    Returns True if successful.
    """
    try:
        import hid as hidapi
    except ImportError:
        return False

    print("  Switching to HID-only mode (disabling keyboard)...")

    try:
        dev = hidapi.device()
        dev.open_path(path)
        dev.set_nonblocking(True)
    except Exception as e:
        print(f"  Could not open device: {e}")
        return False

    # Also set command-polled mode
    para_frame = _sr3308_build_frame(_SR3308_CMD_PARA, _SR3308_MSG_SET,
                                     payload=bytes([0x01, 0x01]))
    _sr3308_hid_send_receive(dev, para_frame, timeout=0.5)

    # Send USB SET mode=2 (HID-only)
    usb_frame = _sr3308_build_frame(_SR3308_CMD_USB, _SR3308_MSG_SET,
                                    payload=bytes([0x02]))
    frames = _sr3308_hid_send_receive(dev, usb_frame, timeout=0.8)

    ok = False
    for f in frames:
        if f["code"] == _SR3308_CMD_USB and f["type_masked"] == 0x00:
            ok = True
            break

    try:
        dev.close()
    except Exception:
        pass

    if ok:
        print("  USB mode set to HID-only. Device is re-enumerating...")
        time.sleep(3)

        # Verify by reconnecting
        try:
            devices = hidapi.enumerate(_SR3308_VID, _SR3308_PID)
            if devices:
                dev2 = hidapi.device()
                dev2.open_path(devices[0]["path"])
                dev2.set_nonblocking(True)
                verify_frame = _sr3308_build_frame(_SR3308_CMD_USB, _SR3308_MSG_GET)
                vframes = _sr3308_hid_send_receive(dev2, verify_frame, timeout=0.8)
                dev2.close()
                for f in vframes:
                    if f["code"] == _SR3308_CMD_USB and f["payload"][0] == 2:
                        print("  Verified: keyboard interface is now DISABLED.")
                        return True
        except Exception:
            pass

        print("  Mode change sent but could not verify. Unplug/replug to confirm.")
        return True
    else:
        print("  Device rejected the mode change.")
        return False


# =============================================================================
# NFC Detection
# =============================================================================
def detect_nfc():
    """
    Detect NFC readers via PC/SC.
    Returns list of reader name strings.
    """
    try:
        from smartcard.System import readers
    except ImportError:
        print("  pyscard not installed - cannot detect NFC readers.")
        if platform.system() == "Linux":
            print("  Install with: sudo apt install pcscd && pip install pyscard")
        else:
            print("  Install with: pip install pyscard")
        return []

    try:
        rlist = readers()
    except Exception as e:
        print(f"  PC/SC error: {e}")
        if platform.system() == "Linux":
            print("  Make sure pcscd service is running: sudo systemctl start pcscd")
        return []

    found = []
    if not rlist:
        print("  No NFC/PC/SC readers found.")
        return []

    for r in rlist:
        name = str(r)
        print(f"  {name:<50} --> DETECTED")
        found.append(name)

    return found


# =============================================================================
# Config handling
# =============================================================================
def find_config():
    """Find config.toml relative to this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "config.toml")


def read_current_config(path):
    """Read current hardware values from config.toml."""
    values = {'uhf_port': None, 'uhf_baudrate': None, 'uhf_type': None}
    try:
        with open(path, 'r') as f:
            text = f.read()

        m = re.search(r'^uhf_port\s*=\s*"([^"]*)"', text, re.MULTILINE)
        if m:
            values['uhf_port'] = m.group(1)

        m = re.search(r'^uhf_baudrate\s*=\s*(\d+)', text, re.MULTILINE)
        if m:
            values['uhf_baudrate'] = int(m.group(1))

        m = re.search(r'^uhf_type\s*=\s*"([^"]*)"', text, re.MULTILINE)
        if m:
            values['uhf_type'] = m.group(1)

    except FileNotFoundError:
        print(f"  Config file not found: {path}")
    return values


def update_config(path, uhf_port=None, uhf_baudrate=None, uhf_type=None):
    """Update config.toml in-place, preserving comments and formatting."""
    with open(path, 'r') as f:
        text = f.read()

    if uhf_port is not None:
        text = re.sub(
            r'^(uhf_port\s*=\s*)"[^"]*"',
            f'\\1"{uhf_port}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )

    if uhf_baudrate is not None:
        text = re.sub(
            r'^(uhf_baudrate\s*=\s*)\d+',
            f'\\g<1>{uhf_baudrate}',
            text,
            count=1,
            flags=re.MULTILINE,
        )

    if uhf_type is not None:
        # Add uhf_type if it doesn't exist, or update it
        if re.search(r'^uhf_type\s*=', text, re.MULTILINE):
            text = re.sub(
                r'^(uhf_type\s*=\s*)"[^"]*"',
                f'\\1"{uhf_type}"',
                text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            # Insert after uhf_baudrate line
            text = re.sub(
                r'^(uhf_baudrate\s*=\s*\d+)',
                f'\\1\nuhf_type = "{uhf_type}"',
                text,
                count=1,
                flags=re.MULTILINE,
            )

    with open(path, 'w') as f:
        f.write(text)


# =============================================================================
# Main
# =============================================================================
def main():
    print()
    print("=" * 60)
    print("  WUZU Scanner Auto-Detect")
    print("=" * 60)

    # --- HID UHF (SR3308) ---
    print()
    print("Scanning USB HID for SR3308 UHF readers...")
    hid_found = detect_uhf_hid()

    # --- Serial UHF (UR-2000) ---
    print()
    print("Scanning serial ports for UR-2000 UHF readers...")
    serial_found = detect_uhf_serial()

    # --- NFC ---
    print()
    print("Scanning for NFC readers (PC/SC)...")
    nfc_found = detect_nfc()

    # --- Summary ---
    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)

    uhf_best = None

    if hid_found:
        sr = hid_found[0]
        usb_mode_name = {0: "HID+KBD", 1: "HID+KBD+CDC", 2: "HID-only"}.get(sr['usb_mode'], "?")
        print(f"  UHF (HID):    SR3308 — {sr['info']} (USB mode={usb_mode_name})")
        uhf_best = sr
    else:
        print("  UHF (HID):    Not found")

    if serial_found:
        ur = serial_found[0]
        print(f"  UHF (Serial): UR-2000 — {ur['port']} @ {ur['baudrate']} baud ({ur['description']})")
        if uhf_best is None:
            uhf_best = ur
    else:
        print("  UHF (Serial): Not found")

    if nfc_found:
        for name in nfc_found:
            print(f"  NFC Reader:   {name}")
    else:
        print("  NFC Reader:   Not found")

    # --- SR3308 keyboard disable ---
    if hid_found:
        sr = hid_found[0]
        if sr['usb_mode'] is not None and sr['usb_mode'] != 2:
            print()
            print("=" * 60)
            print("  SR3308 Keyboard Interface")
            print("=" * 60)
            print()
            print("  The SR3308 keyboard interface is ACTIVE.")
            print("  This causes the reader to type scanned tag data as")
            print("  keystrokes, which interferes with the application.")
            print()
            answer = input("  Disable keyboard interface? [Y/n]: ").strip().lower()
            if answer != "n":
                sr3308_disable_keyboard(sr['path'])
                # Update the usb_mode in our result
                sr['usb_mode'] = 2
            else:
                print("  Keyboard interface left active.")

    # --- Config update ---
    if not uhf_best:
        print()
        print("No UHF reader detected - nothing to update in config.toml.")
        return

    config_path = find_config()
    current = read_current_config(config_path)

    print()
    print(f"Current config.toml values:")
    print(f'  uhf_port     = "{current["uhf_port"]}"')
    print(f'  uhf_baudrate = {current["uhf_baudrate"]}')
    print(f'  uhf_type     = "{current.get("uhf_type", "")}"')

    print()
    if uhf_best['type'] == 'sr3308':
        print(f"Detected: SR3308 via USB HID")
        new_port = "HID"
        new_baud = 0
        new_type = "sr3308"
    else:
        print(f"Detected: UR-2000 on {uhf_best['port']} @ {uhf_best['baudrate']} baud")
        new_port = uhf_best['port']
        new_baud = uhf_best['baudrate']
        new_type = "ur2000"

    answer = input("Update config.toml with detected values? [y/N]: ").strip().lower()
    if answer == "y":
        update_config(config_path,
                      uhf_port=new_port, uhf_baudrate=new_baud, uhf_type=new_type)
        print("config.toml updated.")
    else:
        print("No changes made.")


if __name__ == "__main__":
    main()
