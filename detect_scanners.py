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
    values = {'uhf_port': None, 'uhf_baudrate': None}
    try:
        with open(path, 'r') as f:
            text = f.read()

        m = re.search(r'^uhf_port\s*=\s*"([^"]*)"', text, re.MULTILINE)
        if m:
            values['uhf_port'] = m.group(1)

        m = re.search(r'^uhf_baudrate\s*=\s*(\d+)', text, re.MULTILINE)
        if m:
            values['uhf_baudrate'] = int(m.group(1))

    except FileNotFoundError:
        print(f"  Config file not found: {path}")
    return values


def update_config(path, uhf_port=None, uhf_baudrate=None):
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

    # --- UHF ---
    print()
    print("Scanning serial ports for UHF readers...")
    uhf_found = detect_uhf()

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
        print(f"  UHF Reader: {best['port']} @ {best['baudrate']} baud ({best['description']})")
    else:
        print("  UHF Reader: Not found")

    if nfc_found:
        for name in nfc_found:
            print(f"  NFC Reader: {name}")
    else:
        print("  NFC Reader: Not found")

    # --- Config update ---
    if not uhf_found:
        print()
        print("No UHF reader detected - nothing to update in config.toml.")
        return

    config_path = find_config()
    current = read_current_config(config_path)
    best = uhf_found[0]

    print()
    print(f"Current config.toml values:")
    print(f'  uhf_port     = "{current["uhf_port"]}"')
    print(f'  uhf_baudrate = {current["uhf_baudrate"]}')
    print()
    print(f"Detected values:")
    print(f'  uhf_port     = "{best["port"]}"')
    print(f'  uhf_baudrate = {best["baudrate"]}')

    if current['uhf_port'] == best['port'] and current['uhf_baudrate'] == best['baudrate']:
        print()
        print("Config already matches detected values. No update needed.")
        return

    print()
    answer = input("Update config.toml with detected values? [y/N]: ").strip().lower()
    if answer == 'y':
        update_config(config_path, uhf_port=best['port'], uhf_baudrate=best['baudrate'])
        print("config.toml updated.")
    else:
        print("No changes made.")


if __name__ == "__main__":
    main()
