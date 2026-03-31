#!/usr/bin/env python3
"""
RFID Reader Diagnostic Tool
Use this to troubleshoot connection and tag reading issues
"""

import serial
import serial.tools.list_ports
import time
from uhf_rfid_tool import URFIDReader

def list_ports():
    """List all available COM ports"""
    print("\n" + "="*60)
    print("Available COM Ports:")
    print("="*60)
    
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("  No COM ports found!")
        return []
    
    port_list = []
    for i, port in enumerate(ports, 1):
        print(f"  {i}. {port.device}")
        print(f"     Description: {port.description}")
        print(f"     Hardware ID: {port.hwid}")
        print()
        port_list.append(port.device)
    
    return port_list

def test_raw_communication(port: str):
    """Test raw serial communication"""
    print("\n" + "="*60)
    print(f"Testing raw communication on {port}")
    print("="*60)
    
    try:
        ser = serial.Serial(
            port=port,
            baudrate=57600,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=2.0
        )
        
        print("✓ Port opened successfully")
        time.sleep(0.2)
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # Try to send Get Reader Info command
        # Len=0x04, Adr=0x00, Cmd=0x21, CRC-16
        cmd = bytes([0x04, 0x00, 0x21])
        crc = 0x7E49  # Pre-calculated CRC for this command
        cmd += bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        
        print(f"\nSending Get Reader Info command...")
        print(f"  TX: {cmd.hex().upper()}")
        
        ser.write(cmd)
        ser.flush()
        
        # Wait and read response
        time.sleep(0.5)
        response = b''
        
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting)
            print(f"  RX: {response.hex().upper()}")
            print(f"  Length: {len(response)} bytes")
            
            if len(response) >= 5:
                print(f"\n  Parsed:")
                print(f"    Len: 0x{response[0]:02X}")
                print(f"    Adr: 0x{response[1]:02X}")
                print(f"    Cmd: 0x{response[2]:02X}")
                print(f"    Status: 0x{response[3]:02X}")
                if response[3] == 0x00:
                    print("    ✓ Success!")
                else:
                    print(f"    ✗ Error status")
        else:
            print("  ✗ No response received")
        
        ser.close()
        return len(response) > 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_reader(port: str):
    """Test using URFIDReader class"""
    print("\n" + "="*60)
    print(f"Testing with URFIDReader class on {port}")
    print("="*60)
    
    reader = URFIDReader(port)
    
    if not reader.connect():
        return False
    
    # Run diagnostic test
    reader.test_connection()
    
    # Try multiple inventory attempts
    print("\n" + "="*60)
    print("Multiple inventory attempts (5 tries):")
    print("="*60)
    
    for i in range(5):
        print(f"\nAttempt {i+1}/5:")
        tags = reader.inventory(retry_count=1)
        if tags:
            print(f"✓ Found {len(tags)} tag(s)")
            for j, tag in enumerate(tags, 1):
                print(f"  Tag {j}: {tag}")
            reader.disconnect()
            return True
        time.sleep(0.5)
    
    reader.disconnect()
    return False

def main():
    print("="*60)
    print("RFID Reader Diagnostic Tool")
    print("="*60)
    
    # List ports
    ports = list_ports()
    
    if not ports:
        print("\n⚠️  No COM ports detected!")
        print("   - Check USB connection")
        print("   - Install USB-to-Serial drivers if needed")
        return
    
    # Select port
    print("\nEnter port to test (or press Enter for COM3): ", end='')
    port_input = input().strip()
    
    if not port_input:
        port = "COM3"
    else:
        port = port_input
    
    print(f"\nTesting {port}...")
    
    # Test 1: Raw communication
    print("\n" + "="*60)
    print("TEST 1: Raw Serial Communication")
    print("="*60)
    raw_ok = test_raw_communication(port)
    
    if not raw_ok:
        print("\n❌ Raw communication test failed!")
        print("\n💡 Troubleshooting:")
        print("   - Wrong COM port selected")
        print("   - Reader not powered on")
        print("   - USB cable issue")
        print("   - Driver issue")
        return
    
    print("\n✓ Raw communication works!")
    
    # Test 2: Reader class
    print("\n" + "="*60)
    print("TEST 2: Reader Class Communication")
    print("="*60)
    reader_ok = test_reader(port)
    
    if not reader_ok:
        print("\n⚠️  Reader works but cannot find tags")
        print("\n💡 Tag Reading Issues:")
        print("   1. Tag placement: Try different positions/orientations")
        print("   2. Tag distance: Keep within 1-5cm of antenna")
        print("   3. Tag compatibility: Ensure tag is EPC Gen2 compatible")
        print("   4. Reader power: May need to increase RF power")
        print("   5. Interference: Move away from metal/electronic devices")
        print("\n   What other software are you using that works?")
        print("   Compare settings (power, region, scan time)")
    else:
        print("\n✅ All tests passed! Tags detected successfully!")
    
    print("\n" + "="*60)
    print("Diagnostic complete")
    print("="*60)

if __name__ == "__main__":
    main()