# detect_scanners.py
"""
WUZU Scanner Auto-Detect Tool
Detects attached UHF and NFC readers, offers to update config.toml
"""

import os
import sys
import re
import time
import platform


# =============================================================================
# CRC16 (same algorithm as wuzu_scanner.py UHFReader)
# =============================================================================
def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else crc >> 1
    return crc


# =============================================================================
# UHF Detection
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


def scan_serial_uhf(port, baudrate, timeout=10):
    """
    Run inventory on a serial UHF reader and wait for a tag.
    Returns the EPC hex string of the first tag found, or None on timeout.
    """
    try:
        import serial
    except ImportError:
        return None

    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=0.5,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
        )
        time.sleep(0.1)

        print()
        print(f"  Hold a UHF tag near the reader... ({timeout}s timeout, Ctrl+C to skip)")
        print()

        start = time.time()
        while time.time() - start < timeout:
            # Send inventory command (0x01)
            cmd_data = bytes([0x04, 0x00, 0x01])
            crc_val = crc16(cmd_data)
            frame = cmd_data + bytes([crc_val & 0xFF, (crc_val >> 8) & 0xFF])

            ser.reset_input_buffer()
            ser.write(frame)
            ser.flush()

            # Read response
            time.sleep(0.3)
            resp = b''
            read_start = time.time()
            while time.time() - read_start < 0.5:
                if ser.in_waiting > 0:
                    resp += ser.read(ser.in_waiting)
                    time.sleep(0.05)
                elif len(resp) > 0:
                    break
                else:
                    time.sleep(0.02)

            # Parse inventory response: if len > 5 and tag count > 0
            if len(resp) > 5 and resp[4] > 0:
                pos = 5
                epc_len = resp[pos]
                pos += 1
                if pos + epc_len <= len(resp) - 2:
                    epc = resp[pos:pos + epc_len].hex().upper()
                    ser.close()
                    return epc

            time.sleep(0.2)

        ser.close()
        print("  (timed out - no tag detected)")
        return None

    except KeyboardInterrupt:
        try:
            ser.close()
        except Exception:
            pass
        print("  (skipped)")
        return None
    except Exception:
        return None


def detect_uhf():
    """
    Scan all serial ports for UHF readers.
    Returns list of dicts: [{'port': str, 'baudrate': int, 'description': str}]
    """
    try:
        import serial.tools.list_ports
    except ImportError:
        print("  pyserial not installed - cannot detect UHF readers.")
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
        detected = False

        for baud in baudrates:
            status = f"  {port:<8} - {desc:<40} "
            sys.stdout.write(status)
            sys.stdout.flush()

            if probe_uhf(port, baud):
                print(f"--> UHF Reader DETECTED ({baud} baud)")
                found.append({
                    'port': port,
                    'baudrate': baud,
                    'description': desc,
                })
                detected = True
                break
            else:
                print(f"--> No response ({baud} baud)")

        if not detected and len(baudrates) > 1:
            # Already printed per-baud results
            pass

    return found


# =============================================================================
# Keyboard Wedge UHF Detection
# =============================================================================
def _read_char_nonblocking():
    """Read a single character without blocking, or return None."""
    if platform.system() == "Windows":
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                return ch.decode("utf-8")
            except Exception:
                return None
    else:
        import select
        dr, _, _ = select.select([sys.stdin], [], [], 0.02)
        if dr:
            return sys.stdin.read(1)
    return None


def prompt_scan(label, timeout=15):
    """
    Prompt user to scan a tag (or press Escape to skip).
    Captures keyboard-wedge input (rapid chars + Enter).
    Returns the captured ID string, or None if skipped/timeout.
    """
    print()
    print(f"  {label}")
    print(f"  Scan a tag now, or press Escape to skip... ({timeout}s timeout)")
    print()
    sys.stdout.write("  > ")
    sys.stdout.flush()

    buf = ""
    start = time.time()

    while time.time() - start < timeout:
        ch = _read_char_nonblocking()
        if ch is None:
            time.sleep(0.02)
            continue
        if ch == "\x1b":  # Escape
            print(" (skipped)")
            return None
        if ch in ("\r", "\n"):
            if buf:
                print()
                return buf
            continue
        buf += ch
        sys.stdout.write(ch)
        sys.stdout.flush()

    print(" (timed out)")
    return buf if buf else None


def detect_keyboard_wedge():
    """
    Test for a keyboard wedge UHF reader by prompting the user to scan.
    Returns the scanned tag ID or None.
    """
    tag_id = prompt_scan("Keyboard Wedge UHF Test")
    if tag_id:
        print(f"  Captured ID: {tag_id}")
        print(f"  Length: {len(tag_id)} characters")
        return tag_id
    return None


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
    values = {'uhf_type': None, 'uhf_port': None, 'uhf_baudrate': None}
    try:
        with open(path, 'r') as f:
            text = f.read()

        m = re.search(r'^uhf_type\s*=\s*"([^"]*)"', text, re.MULTILINE)
        if m:
            values['uhf_type'] = m.group(1)

        m = re.search(r'^uhf_port\s*=\s*"([^"]*)"', text, re.MULTILINE)
        if m:
            values['uhf_port'] = m.group(1)

        m = re.search(r'^uhf_baudrate\s*=\s*(\d+)', text, re.MULTILINE)
        if m:
            values['uhf_baudrate'] = int(m.group(1))

    except FileNotFoundError:
        print(f"  Config file not found: {path}")
    return values


def update_config(path, uhf_type=None, uhf_port=None, uhf_baudrate=None):
    """Update config.toml in-place, preserving comments and formatting."""
    with open(path, 'r') as f:
        text = f.read()

    if uhf_type is not None:
        if re.search(r'^uhf_type\s*=', text, re.MULTILINE):
            text = re.sub(
                r'^(uhf_type\s*=\s*)"[^"]*"',
                f'\\1"{uhf_type}"',
                text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            # Insert uhf_type before uhf_port
            text = re.sub(
                r'^(uhf_port\s*=)',
                f'uhf_type = "{uhf_type}"           # "serial" for UR-2000, "keyboard" for USB keyboard wedge scanner\n\\1',
                text,
                count=1,
                flags=re.MULTILINE,
            )

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

    # --- Serial UHF ---
    print()
    print("Scanning serial ports for UHF readers...")
    uhf_found = detect_uhf()

    serial_scan_id = None
    if uhf_found:
        best = uhf_found[0]
        print(f"\n  Found: {best['port']} @ {best['baudrate']} baud")
        serial_scan_id = scan_serial_uhf(best['port'], best['baudrate'])
        if serial_scan_id:
            print(f"  Tag EPC: {serial_scan_id}")

    # --- Keyboard Wedge UHF ---
    wedge_scan_id = None
    if not uhf_found:
        print()
        print("Testing for keyboard wedge UHF reader...")
        wedge_scan_id = detect_keyboard_wedge()

    # --- NFC ---
    print()
    print("Scanning for NFC readers (PC/SC)...")
    nfc_found = detect_nfc()

    # --- Summary ---
    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)

    if uhf_found:
        best = uhf_found[0]
        label = f"{best['port']} @ {best['baudrate']} baud ({best['description']})"
        if serial_scan_id:
            label += f" - verified (tag: {serial_scan_id})"
        print(f"  Serial UHF:   {label}")
    else:
        print("  Serial UHF:   Not found")

    if wedge_scan_id:
        print(f"  Keyboard UHF: Detected (tag: {wedge_scan_id})")
    else:
        print("  Keyboard UHF: Not found / skipped")

    if nfc_found:
        for name in nfc_found:
            print(f"  NFC Reader:   {name}")
    else:
        print("  NFC Reader:   Not found")

    # --- Config update ---
    config_path = find_config()
    current = read_current_config(config_path)

    if not uhf_found and not wedge_scan_id:
        print()
        print("No UHF reader detected - nothing to update in config.toml.")
        return

    print()
    print(f"Current config.toml values:")
    print(f'  uhf_type     = "{current["uhf_type"]}"')
    print(f'  uhf_port     = "{current["uhf_port"]}"')
    print(f'  uhf_baudrate = {current["uhf_baudrate"]}')

    # Determine what to offer
    if uhf_found and wedge_scan_id:
        print()
        print("Both serial and keyboard wedge UHF readers detected.")
        print("  [1] Use serial reader")
        print("  [2] Use keyboard wedge reader")
        print("  [N] No changes")
        answer = input("Choice: ").strip().lower()
        if answer == "1":
            best = uhf_found[0]
            update_config(config_path, uhf_type="serial",
                          uhf_port=best['port'], uhf_baudrate=best['baudrate'])
            print("config.toml updated (serial mode).")
        elif answer == "2":
            update_config(config_path, uhf_type="keyboard")
            print("config.toml updated (keyboard wedge mode).")
        else:
            print("No changes made.")
    elif uhf_found:
        best = uhf_found[0]
        print()
        print(f"Detected serial UHF: {best['port']} @ {best['baudrate']} baud")
        answer = input("Update config.toml with detected values? [y/N]: ").strip().lower()
        if answer == "y":
            update_config(config_path, uhf_type="serial",
                          uhf_port=best['port'], uhf_baudrate=best['baudrate'])
            print("config.toml updated (serial mode).")
        else:
            print("No changes made.")
    elif wedge_scan_id:
        print()
        print(f"Detected keyboard wedge UHF (tag: {wedge_scan_id})")
        answer = input("Update config.toml to use keyboard wedge mode? [y/N]: ").strip().lower()
        if answer == "y":
            update_config(config_path, uhf_type="keyboard")
            print("config.toml updated (keyboard wedge mode).")
        else:
            print("No changes made.")


if __name__ == "__main__":
    main()
