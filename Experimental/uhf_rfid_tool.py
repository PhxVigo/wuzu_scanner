#!/usr/bin/env python3
"""
UHF RFID Reader/Writer Tool for UR-2000
Supports Impinj Monza R6-P chip operations

Memory Banks:
- Bank 0 (Reserved): Kill Password (0x00-0x01) + Access Password (0x02-0x03)
- Bank 1 (EPC): CRC, PC, EPC data
- Bank 2 (TID): Manufacturer ID, Model, Serial (Read-Only)
- Bank 3 (User): User-programmable memory (32-64 bits)
"""

import serial
import struct
import time
import os
import platform
from typing import Optional, List, Tuple
from enum import IntEnum

# Enable ANSI colors on Windows
if platform.system() == "Windows":
    os.system("")


class Colors:
    """ANSI color codes for terminal output"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"


class MemoryBank(IntEnum):
    """RFID Tag Memory Banks"""
    RESERVED = 0x00  # Password memory
    EPC = 0x01       # EPC memory
    TID = 0x02       # Tag ID memory (read-only)
    USER = 0x03      # User memory


class LockAction(IntEnum):
    """Lock/Unlock Actions"""
    WRITABLE_ANY = 0x00          # Readable and writable from any state
    WRITABLE_PERMANENT = 0x01    # Permanently writable
    WRITABLE_SECURED = 0x02      # Writable from secured state only
    NEVER_WRITABLE = 0x03        # Never writable (permanently locked)


class LockTarget(IntEnum):
    """Lock Target Selection"""
    KILL_PASSWORD = 0x00
    ACCESS_PASSWORD = 0x01
    EPC_MEMORY = 0x02
    TID_MEMORY = 0x03
    USER_MEMORY = 0x04


class StatusCode(IntEnum):
    """Reader Status Codes"""
    SUCCESS = 0x00
    INVENTORY_COMPLETE = 0x01
    INVENTORY_TIMEOUT = 0x02
    MORE_DATA = 0x03
    BUFFER_FULL = 0x04
    ACCESS_PASSWORD_ERROR = 0x05
    KILL_ERROR = 0x09
    KILL_PASSWORD_ZERO = 0x0A
    COMMAND_NOT_SUPPORTED = 0x0B
    ACCESS_PASSWORD_REQUIRED = 0x0C
    ALREADY_PROTECTED = 0x0D
    NOT_PROTECTED = 0x0E
    COMMAND_ERROR = 0xF9
    POOR_COMMUNICATION = 0xFA
    NO_TAG = 0xFB
    TAG_ERROR = 0xFC
    LENGTH_ERROR = 0xFD
    ILLEGAL_COMMAND = 0xFE
    PARAMETER_ERROR = 0xFF


class URFIDReader:
    """UR-2000 UHF RFID Reader Interface"""
    
    # Command codes
    CMD_INVENTORY = 0x01
    CMD_READ_DATA = 0x02
    CMD_WRITE_DATA = 0x03
    CMD_WRITE_EPC = 0x04
    CMD_KILL_TAG = 0x05
    CMD_LOCK = 0x06
    CMD_BLOCK_ERASE = 0x07
    CMD_GET_READER_INFO = 0x21
    CMD_SET_POWER = 0x2F
    CMD_ACOUSTO_OPTIC = 0x33
    
    def __init__(self, port: str, baudrate: int = 57600, address: int = 0x00):
        """
        Initialize RFID Reader
        
        Args:
            port: COM port (e.g., 'COM3' on Windows)
            baudrate: Communication speed (default: 57600)
            address: Reader address (default: 0x00)
        """
        self.port = port
        self.baudrate = baudrate
        self.address = address
        self.serial = None
        
    def connect(self) -> bool:
        """Open serial connection to reader"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2.0
            )
            time.sleep(0.2)  # Allow port to stabilize
            
            # Clear any stale data
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            time.sleep(0.1)
            
            print(f"✓ Connected to {self.port} at {self.baudrate} bps")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("✓ Disconnected")
    
    @staticmethod
    def calculate_crc16(data: bytes) -> int:
        """
        Calculate CRC-16 checksum
        
        Args:
            data: Byte array to calculate CRC for
            
        Returns:
            16-bit CRC value
        """
        PRESET_VALUE = 0xFFFF
        POLYNOMIAL = 0x8408
        
        crc = PRESET_VALUE
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ POLYNOMIAL
                else:
                    crc = crc >> 1
        
        return crc & 0xFFFF
    
    def build_command(self, cmd: int, data: bytes = b'') -> bytes:
        """
        Build command packet with CRC
        
        Args:
            cmd: Command code
            data: Command data (optional)
            
        Returns:
            Complete command packet
        """
        length = len(data) + 4
        packet = bytes([length, self.address, cmd]) + data
        crc = self.calculate_crc16(packet)
        packet += struct.pack('<H', crc)  # LSB first
        return packet
    
    def send_command(self, cmd: int, data: bytes = b'', timeout: float = 2.0, debug: bool = False) -> Optional[bytes]:
        """
        Send command and receive response
        
        Args:
            cmd: Command code
            data: Command data
            timeout: Response timeout in seconds
            debug: Print debug information
            
        Returns:
            Response data or None on error
        """
        if not self.serial or not self.serial.is_open:
            print("✗ Serial port not open")
            return None
        
        # Build and send command
        command = self.build_command(cmd, data)
        
        if debug:
            print(f"  TX: {command.hex().upper()}")
        
        # Clear buffers before sending
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        time.sleep(0.05)
        
        # Send command
        self.serial.write(command)
        self.serial.flush()
        
        # Read response - wait for complete packet
        self.serial.timeout = 0.1
        response = b''
        start_time = time.time()
        last_data_time = start_time
        
        while time.time() - start_time < timeout:
            waiting = self.serial.in_waiting
            if waiting > 0:
                chunk = self.serial.read(waiting)
                if chunk:
                    response += chunk
                    last_data_time = time.time()
                    
                    # Check if we have enough for a complete packet
                    if len(response) >= 5:  # Min: Len + Adr + Cmd + Status + CRC(2)
                        expected_len = response[0] + 3  # Len field + Len byte + CRC(2)
                        
                        if len(response) >= expected_len:
                            # We have what looks like a complete packet
                            if debug:
                                print(f"  RX: {response[:expected_len].hex().upper()}")
                            
                            # Optional CRC check - some readers may have issues
                            try:
                                received_crc = struct.unpack('<H', response[expected_len-2:expected_len])[0]
                                calculated_crc = self.calculate_crc16(response[:expected_len-2])
                                
                                if received_crc != calculated_crc:
                                    if debug:
                                        print(f"  Warning: CRC mismatch (calc: {calculated_crc:04X}, recv: {received_crc:04X})")
                                    # Continue anyway - return the packet
                            except:
                                pass
                            
                            return response[:expected_len]
            else:
                # No data waiting - check if we've been idle too long after receiving some data
                if response and (time.time() - last_data_time > 0.2):
                    # We got some data but no more coming - assume packet complete
                    if len(response) >= 5:
                        if debug:
                            print(f"  RX (timeout): {response.hex().upper()}")
                        return response
                    break
                
                time.sleep(0.01)
        
        if response and debug:
            print(f"  Partial response: {response.hex().upper()}")
        
        return response if len(response) >= 5 else None
    
    def parse_response(self, response: bytes) -> Tuple[int, int, bytes]:
        """
        Parse response packet
        
        Args:
            response: Response packet
            
        Returns:
            Tuple of (command, status, data)
        """
        if len(response) < 5:
            return (0, 0xFF, b'')
        
        length = response[0]
        # address = response[1]  # Not used
        cmd = response[2]
        status = response[3]
        data = response[4:-2] if length > 5 else b''
        
        return (cmd, status, data)
    
    def get_status_description(self, status: int) -> str:
        """Get human-readable status description"""
        status_descriptions = {
            0x00: "Success",
            0x01: "Inventory complete (returned early)",
            0x02: "Inventory timeout",
            0x03: "More data available",
            0x04: "Reader buffer full",
            0x05: "Access password error",
            0x09: "Kill tag error",
            0x0A: "Kill password cannot be zero",
            0x0B: "Tag does not support command",
            0x0C: "Access password required (cannot be zero)",
            0x0D: "Tag already protected",
            0x0E: "Tag not protected",
            0xF9: "Command execution error",
            0xFA: "Poor communication with tag",
            0xFB: "No tag in field",
            0xFC: "Tag returned error code",
            0xFD: "Command length error",
            0xFE: "Illegal command or CRC error",
            0xFF: "Parameter error"
        }
        return status_descriptions.get(status, f"Unknown status: 0x{status:02X}")
    
    # ==================== Tag Operations ====================
    
    def inventory(self, retry_count: int = 3) -> List[str]:
        """
        Scan for tags in range
        
        Args:
            retry_count: Number of retry attempts
            
        Returns:
            List of EPC values (hex strings)
        """
        print("\n📡 Scanning for tags...")
        
        # Try multiple times
        for attempt in range(retry_count):
            if attempt > 0:
                print(f"  Retry {attempt}...")
                time.sleep(0.2)
            
            response = self.send_command(self.CMD_INVENTORY, timeout=5.0)
            
            if not response or len(response) < 5:
                continue
            
            # Parse response: [Len][Adr][Cmd][Status][Num_tags][tag_data...][CRC]
            status = response[3]
            
            # Status 0x00, 0x01, 0x02 are success variants
            if status in [0x00, 0x01, 0x02]:
                if len(response) < 6:  # Need at least space for num_tags
                    continue
                
                num_tags = response[4]
                
                if num_tags == 0:
                    continue
                
                print(f"✓ Found {num_tags} tag(s)")
                
                # Parse tags
                tags = []
                pos = 5  # Start after num_tags byte
                
                for i in range(num_tags):
                    if pos >= len(response) - 2:  # Don't read into CRC
                        break
                    
                    epc_len = response[pos]
                    pos += 1
                    
                    if pos + epc_len > len(response) - 2:
                        break
                    
                    epc_bytes = response[pos:pos + epc_len]
                    epc_hex = epc_bytes.hex().upper()
                    
                    if epc_hex not in tags:  # Avoid duplicates
                        tags.append(epc_hex)
                        print(f"  Tag {len(tags)}: {epc_hex}")
                    
                    pos += epc_len
                
                if tags:
                    return tags
                    
            elif status == 0xFB:
                # No tag - expected, keep trying
                continue
            else:
                # Other error
                if attempt == 0:  # Only print on first attempt
                    print(f"  Status: {self.get_status_description(status)}")
        
        print("✗ No tags found")
        return []
    
    def read_tid(self, epc: str = "", access_password: str = "00000000") -> Optional[str]:
        """
        Read TID (Tag Identifier) memory
        
        Args:
            epc: EPC hex string (empty for any tag)
            access_password: 8-char hex string (default: 00000000)
            
        Returns:
            TID hex string or None
        """
        print("\n📖 Reading TID...")
        return self._read_memory(MemoryBank.TID, 0x00, 6, epc, access_password)
    
    def read_epc(self, epc: str = "", access_password: str = "00000000") -> Optional[str]:
        """
        Read EPC memory
        
        Args:
            epc: EPC hex string (empty for any tag)
            access_password: 8-char hex string
            
        Returns:
            EPC hex string or None
        """
        print("\n📖 Reading EPC...")
        # Read from word 0x02 (skip CRC and PC)
        return self._read_memory(MemoryBank.EPC, 0x02, 6, epc, access_password)
    
    def read_reserved(self, epc: str = "", access_password: str = "00000000") -> Optional[dict]:
        """
        Read Reserved memory (passwords)
        
        Args:
            epc: EPC hex string (empty for any tag)
            access_password: 8-char hex string
            
        Returns:
            Dict with 'kill_password' and 'access_password' or None
        """
        print("\n📖 Reading Reserved Memory (Passwords)...")
        data = self._read_memory(MemoryBank.RESERVED, 0x00, 4, epc, access_password)
        
        if data:
            return {
                'kill_password': data[:8],
                'access_password': data[8:16]
            }
        else:
            print(f"{Colors.DIM}  Note: Reserved memory may be locked or require correct access password{Colors.RESET}")
            return None
    
    def read_user(self, epc: str = "", access_password: str = "00000000", 
                  word_count: int = 2) -> Optional[str]:
        """
        Read User memory
        
        Args:
            epc: EPC hex string
            access_password: 8-char hex string
            word_count: Number of words to read (default: 2 for 32 bits)
            
        Returns:
            User memory hex string or None
        """
        print("\n📖 Reading User Memory...")
        result = self._read_memory(MemoryBank.USER, 0x00, word_count, epc, access_password)
        
        if not result:
            print(f"{Colors.DIM}  Note: Monza R6-P user memory may require specific memory profile{Colors.RESET}")
            print(f"{Colors.DIM}        or may not be enabled on this tag{Colors.RESET}")
        
        return result
    
    def _read_memory(self, bank: MemoryBank, word_ptr: int, num_words: int,
                     epc: str = "", access_password: str = "00000000", retries: int = 3) -> Optional[str]:
        """
        Internal method to read memory
        
        Args:
            bank: Memory bank to read
            word_ptr: Starting word address
            num_words: Number of words to read
            epc: EPC hex string (empty for no filtering)
            access_password: 8-char hex string
            retries: Number of retry attempts
            
        Returns:
            Data as hex string or None
        """
        # Parse EPC
        epc_bytes = bytes.fromhex(epc) if epc else b''
        epc_len = len(epc_bytes) // 2  # Length in words
        
        # Parse password
        pwd_bytes = bytes.fromhex(access_password)
        
        # Build command data
        data = bytes([epc_len]) + epc_bytes
        data += bytes([bank, word_ptr, num_words])
        data += pwd_bytes
        data += bytes([0x00, 0x00])  # MaskAdr, MaskLen (no mask)
        
        # Retry loop for reliability
        for attempt in range(retries):
            if attempt > 0:
                time.sleep(0.1)  # Small delay between retries
            
            response = self.send_command(self.CMD_READ_DATA, data)
            
            if not response or len(response) < 5:
                continue
            
            status = response[3]
            
            if status == 0x00:
                # Success - extract data (skip header and CRC)
                result_data = response[4:-2]
                hex_data = result_data.hex().upper()
                print(f"✓ Read successful: {hex_data}")
                return hex_data
            elif status == 0xFA and attempt < retries - 1:
                # Poor communication - retry
                continue
            
        # All retries failed - report the last status
        if response and len(response) >= 4:
            status = response[3]
            print(f"✗ {self.get_status_description(status)}")
        
        return None
    
    def write_epc(self, new_epc: str, access_password: str = "00000000", retries: int = 3) -> bool:
        """
        Write new EPC value
        
        Args:
            new_epc: New EPC as hex string (will be padded to 96 bits if shorter)
            access_password: 8-char hex string
            retries: Number of retry attempts
            
        Returns:
            True on success
        """
        print(f"\n✏️ Writing EPC: {new_epc}")
        
        # Remove any spaces or non-hex characters
        new_epc = ''.join(c for c in new_epc if c in '0123456789ABCDEFabcdef')
        
        # Ensure even length
        if len(new_epc) % 2 != 0:
            new_epc = '0' + new_epc
        
        # Standard EPC is 96 bits (24 hex chars / 12 bytes / 6 words)
        # Pad or truncate to 96 bits
        if len(new_epc) < 24:
            new_epc = new_epc.ljust(24, '0')  # Pad with zeros
            print(f"  Padded to 96 bits: {new_epc}")
        elif len(new_epc) > 24:
            if len(new_epc) <= 30:  # 128-bit EPC (max for most tags)
                new_epc = new_epc[:30]
                print(f"  Using 128-bit EPC: {new_epc}")
            else:
                print(f"✗ EPC too long (max 30 hex chars / 128 bits)")
                return False
        
        epc_bytes = bytes.fromhex(new_epc)
        epc_len_words = len(epc_bytes) // 2
        
        if epc_len_words > 15:
            print("✗ EPC too long (max 15 words / 30 bytes)")
            return False
        
        # Parse password
        pwd_bytes = bytes.fromhex(access_password)
        
        # Build command: [ENum][Pwd][WEPC]
        data = bytes([epc_len_words]) + pwd_bytes + epc_bytes
        
        # Retry loop
        for attempt in range(retries):
            if attempt > 0:
                print(f"  Retry {attempt}/{retries-1}...")
                time.sleep(0.2)
            
            response = self.send_command(self.CMD_WRITE_EPC, data, timeout=3.0)
            
            if not response or len(response) < 5:
                continue
            
            status = response[3]
            
            if status == 0x00:
                print("✓ EPC written successfully")
                time.sleep(0.3)  # Give tag time to save
                return True
            elif status == 0xFA and attempt < retries - 1:
                # Poor communication - retry
                continue
            elif status == 0xFB and attempt < retries - 1:
                # No tag - retry
                continue
        
        # All retries failed
        if response and len(response) >= 4:
            status = response[3]
            print(f"✗ {self.get_status_description(status)}")
        else:
            print("✗ Write failed - no response")
        
        return False
    
    def write_password(self, kill_password: str = None, access_password: str = None,
                       current_access_password: str = "00000000", epc: str = "", retries: int = 3) -> bool:
        """
        Write passwords to Reserved memory
        
        Args:
            kill_password: 8-char hex string (None to skip)
            access_password: 8-char hex string (None to skip)
            current_access_password: Current access password
            epc: EPC to target (empty for any tag)
            retries: Number of retry attempts
            
        Returns:
            True on success
        """
        print("\n🔐 Writing passwords...")
        if epc:
            print(f"  Target tag: {epc}")
        
        # Parse EPC
        epc_bytes = bytes.fromhex(epc) if epc else b''
        epc_len = len(epc_bytes) // 2
        
        # Parse current password
        pwd_bytes = bytes.fromhex(current_access_password)
        
        # IMPORTANT: For Monza R6 chips, the Reserved memory might be PermaLocked to zero
        # Check the datasheet - Monza R6 has no programmable passwords
        # Monza R6-P should support passwords, but they might be locked by default
        
        success = True
        
        # Write kill password if provided
        if kill_password:
            # Validate kill password format
            if len(kill_password) != 8:
                print(f"✗ Kill password must be 8 hex characters")
                return False
                
            print(f"  Writing Kill Password: {kill_password}")
            kill_pwd_bytes = bytes.fromhex(kill_password)
            
            data = bytes([2, epc_len]) + epc_bytes  # WNum=2 (2 words), ENum
            data += bytes([MemoryBank.RESERVED, 0x00])  # Bank, WordPtr
            data += kill_pwd_bytes  # Data to write
            data += pwd_bytes  # Access password
            data += bytes([0x00, 0x00])  # MaskAdr, MaskLen
            
            # Retry loop
            write_success = False
            for attempt in range(retries):
                if attempt > 0:
                    print(f"    Retry {attempt}/{retries-1}...")
                    time.sleep(0.2)
                
                response = self.send_command(self.CMD_WRITE_DATA, data, timeout=3.0)
                
                if response and len(response) >= 4:
                    status = response[3]
                    if status == 0x00:
                        write_success = True
                        break
                    elif status in [0xFA, 0xFB] and attempt < retries - 1:
                        continue
                
            if not write_success:
                if response and len(response) >= 4:
                    status = response[3]
                    # If tag returned error code (0xFC), there should be an error byte
                    if status == 0xFC and len(response) >= 6:
                        tag_error = response[4]
                        tag_error_desc = {
                            0x00: "Other error",
                            0x03: "Memory overrun",
                            0x04: "Memory locked",
                            0x0B: "Insufficient power",
                            0x0F: "Non-specific error"
                        }.get(tag_error, f"Unknown (0x{tag_error:02X})")
                        print(f"✗ Kill password write failed: Tag error {tag_error_desc}")
                    else:
                        print(f"✗ Kill password write failed: {self.get_status_description(status)}")
                success = False
        
        # Write access password if provided
        if access_password:
            # Validate access password format
            if len(access_password) != 8:
                print(f"✗ Access password must be 8 hex characters")
                return False
                
            print(f"  Writing Access Password: {access_password}")
            access_pwd_bytes = bytes.fromhex(access_password)
            
            data = bytes([2, epc_len]) + epc_bytes  # WNum=2, ENum
            data += bytes([MemoryBank.RESERVED, 0x02])  # Bank, WordPtr (word 2)
            data += access_pwd_bytes  # Data to write
            data += pwd_bytes  # Current access password
            data += bytes([0x00, 0x00])  # MaskAdr, MaskLen
            
            # Retry loop
            write_success = False
            for attempt in range(retries):
                if attempt > 0:
                    print(f"    Retry {attempt}/{retries-1}...")
                    time.sleep(0.2)
                
                response = self.send_command(self.CMD_WRITE_DATA, data, timeout=3.0)
                
                if response and len(response) >= 4:
                    status = response[3]
                    if status == 0x00:
                        write_success = True
                        break
                    elif status in [0xFA, 0xFB] and attempt < retries - 1:
                        continue
                
            if not write_success:
                if response and len(response) >= 4:
                    status = response[3]
                    # If tag returned error code (0xFC), there should be an error byte
                    if status == 0xFC and len(response) >= 6:
                        tag_error = response[4]
                        tag_error_desc = {
                            0x00: "Other error",
                            0x03: "Memory overrun",
                            0x04: "Memory locked",
                            0x0B: "Insufficient power",
                            0x0F: "Non-specific error"
                        }.get(tag_error, f"Unknown (0x{tag_error:02X})")
                        print(f"✗ Access password write failed: Tag error {tag_error_desc}")
                    else:
                        print(f"✗ Access password write failed: {self.get_status_description(status)}")
                success = False
        
        if success:
            print("✓ Passwords written successfully")
            time.sleep(0.3)  # Give tag time to save
        
        return success
    
    def lock_memory(self, target: LockTarget, action: LockAction,
                    access_password: str, epc: str = "") -> bool:
        """
        Lock/unlock memory regions
        
        Args:
            target: What to lock (password, EPC, TID, User)
            action: Lock action (writable, secured, permanent, never)
            access_password: 8-char hex string (required, cannot be 00000000)
            epc: EPC to target (empty for any tag)
            
        Returns:
            True on success
        """
        print(f"\n🔒 Setting lock: {target.name} -> {action.name}")
        
        if access_password == "00000000":
            print("✗ Access password cannot be 00000000 for lock operations")
            return False
        
        # Parse EPC
        epc_bytes = bytes.fromhex(epc) if epc else b''
        epc_len = len(epc_bytes) // 2
        
        # Parse password
        pwd_bytes = bytes.fromhex(access_password)
        
        # Build command
        data = bytes([epc_len]) + epc_bytes
        data += bytes([target, action])
        data += pwd_bytes
        data += bytes([0x00, 0x00])  # MaskAdr, MaskLen
        
        response = self.send_command(self.CMD_LOCK, data)
        
        if not response:
            return False
        
        cmd, status, _ = self.parse_response(response)
        
        if status == 0x00:
            print("✓ Lock state set successfully")
            return True
        else:
            print(f"✗ {self.get_status_description(status)}")
            return False
    
    def beep(self, active_time: int = 3, silent_time: int = 0, times: int = 1):
        """
        Make reader beep
        
        Args:
            active_time: Beep duration (x 50ms)
            silent_time: Pause between beeps (x 50ms)
            times: Number of beeps
        """
        data = bytes([active_time, silent_time, times])
        self.send_command(self.CMD_ACOUSTO_OPTIC, data)
    
    def kill_tag(self, kill_password: str, epc: str = "", retries: int = 3) -> bool:
        """
        ⚠️ PERMANENT: Kill a tag (makes it PERMANENTLY unresponsive)
        
        Args:
            kill_password: 8-char hex kill password (must match tag's kill password)
            epc: EPC to target (empty for any tag)
            retries: Number of retry attempts
            
        Returns:
            True if kill successful (tag is now dead)
        """
        print(f"\n{Colors.RED}💀 KILL TAG COMMAND{Colors.RESET}")
        print(f"{Colors.YELLOW}⚠️  WARNING: This will PERMANENTLY destroy the tag!{Colors.RESET}")
        
        # Parse EPC
        epc_bytes = bytes.fromhex(epc) if epc else b''
        epc_len = len(epc_bytes) // 2
        
        # Parse kill password
        kill_pwd_bytes = bytes.fromhex(kill_password)
        
        # Build command: [ENum][EPC][Killpwd][MaskAdr][MaskLen]
        data = bytes([epc_len]) + epc_bytes + kill_pwd_bytes + bytes([0x00, 0x00])
        
        print(f"  Kill Password: {kill_password}")
        if epc:
            print(f"  Target EPC: {epc}")
        
        # Retry loop
        for attempt in range(retries):
            if attempt > 0:
                print(f"  Retry {attempt}/{retries-1}...")
                time.sleep(0.2)
            
            response = self.send_command(self.CMD_KILL_TAG, data, timeout=3.0)
            
            if not response or len(response) < 5:
                continue
            
            status = response[3]
            
            if status == 0x00:
                print(f"{Colors.RED}💀 Tag has been KILLED (permanently disabled){Colors.RESET}")
                return True
            elif status == 0x09:
                print(f"{Colors.YELLOW}✗ Kill failed: Wrong password or poor communication{Colors.RESET}")
                if attempt < retries - 1:
                    continue
            elif status == 0x0A:
                print(f"{Colors.RED}✗ Kill password cannot be zero (safety feature){Colors.RESET}")
                return False
            elif status in [0xFA, 0xFB] and attempt < retries - 1:
                continue
        
        # All retries failed
        if response and len(response) >= 4:
            status = response[3]
            
            # Decode tag error if present
            if status == 0xFC and len(response) >= 6:
                tag_error = response[4]
                if tag_error == 0x04:
                    print(f"{Colors.GREEN}✓ Kill BLOCKED: Tag's kill password is locked (tag is protected){Colors.RESET}")
                else:
                    print(f"✗ {self.get_status_description(status)}")
            else:
                print(f"✗ {self.get_status_description(status)}")
        else:
            print("✗ Kill failed - no response")
        
        return False
    
    def get_reader_info(self) -> Optional[dict]:
        """
        Get reader information
        
        Returns:
            Dict with reader info or None
        """
        print("\n📋 Getting reader information...")
        response = self.send_command(self.CMD_GET_READER_INFO)
        
        if not response:
            return None
        
        cmd, status, data = self.parse_response(response)
        
        if status == 0x00 and len(data) >= 8:
            info = {
                'version': f"{data[0]}.{data[1]}",
                'type': f"0x{data[2]:02X}",
                'protocols': [],
                'power': data[6] if data[6] != 0 else "Unknown",
                'scan_time': f"{data[7] * 100}ms"
            }
            
            # Parse protocol support
            if data[3] & 0x02:
                info['protocols'].append('ISO18000-6C (EPC Gen2)')
            if data[3] & 0x01:
                info['protocols'].append('ISO18000-6B')
            
            for key, value in info.items():
                print(f"  {key}: {value}")
            
            return info
        else:
            print(f"✗ {self.get_status_description(status)}")
            return None
    
    def test_connection(self) -> bool:
        """
        Test connection and diagnose issues
        
        Returns:
            True if reader responds correctly
        """
        print("\n🔍 Testing connection...")
        
        # Test 1: Get reader info
        print("  Test 1: Get reader info...")
        response = self.send_command(self.CMD_GET_READER_INFO, debug=True)
        if not response:
            print("  ✗ No response to info command")
            return False
        
        cmd, status, data = self.parse_response(response)
        if status != 0x00:
            print(f"  ✗ Info command failed: {self.get_status_description(status)}")
            return False
        
        print("  ✓ Reader responds to commands")
        
        # Test 2: Try inventory with debug
        print("  Test 2: Inventory scan (debug mode)...")
        response = self.send_command(self.CMD_INVENTORY, timeout=5.0, debug=True)
        if not response:
            print("  ✗ No response to inventory command")
            print("  💡 Try: Place tag closer, check antenna connection, or adjust power")
            return False
        
        cmd, status, data = self.parse_response(response)
        print(f"  Status: {self.get_status_description(status)} (0x{status:02X})")
        
        if status == 0xFB:
            print("  💡 Reader works but sees no tags")
            print("     - Tag might be too far away")
            print("     - Tag might not be compatible (needs EPC Gen2)")
            print("     - Reader power might be too low")
            return True
        elif status in [0x00, 0x01, 0x02]:
            print("  ✓ Reader found tags!")
            return True
        
        return True


def main():
    """Demo application"""
    print("=" * 60)
    print("UHF RFID Reader/Writer Tool")
    print("UR-2000 Reader with Impinj Monza R6-P Support")
    print("=" * 60)
    
    # Configuration
    PORT = "COM3"  # Change to your COM port
    READER_ADDRESS = 0x00
    
    # Create reader instance
    reader = URFIDReader(PORT, address=READER_ADDRESS)
    
    try:
        # Connect
        if not reader.connect():
            return
        
        # Test connection and diagnose
        print("\n" + "=" * 60)
        reader.test_connection()
        print("=" * 60)
        
        # Get reader info
        info = reader.get_reader_info()
        
        # Inventory tags with retries
        tags = reader.inventory(retry_count=5)
        
        if not tags:
            print(f"\n{Colors.YELLOW}⚠️  No tags found.{Colors.RESET}")
            print(f"\n{Colors.CYAN}💡 Troubleshooting:{Colors.RESET}")
            print("   1. Place tag within 1-5cm of reader antenna")
            print("   2. Ensure tag is EPC Gen2 / ISO18000-6C compatible")
            print("   3. Check reader power level")
            print("   4. Try different tag orientations")
            print("   5. Verify tag works with other software")
            
            if info and info['power'] != 'Unknown' and int(info['power']) < 25:
                print(f"\n   Current power: {info['power']} dBm (low)")
                print("   Consider increasing power if available")
            
            return
        
        # Use first tag
        target_epc = tags[0]
        print(f"\n{Colors.BOLD}{Colors.GREEN}🎯 Working with tag: {target_epc}{Colors.RESET}")
        
        # Track what we successfully read
        success_count = 0
        
        # Small delay after inventory
        time.sleep(0.2)
        
        # Read TID (always readable)
        tid = reader.read_tid()
        if tid:
            success_count += 1
            print(f"\n{Colors.BOLD}📌 TID Breakdown:{Colors.RESET}")
            print(f"   Full TID: {Colors.CYAN}{tid}{Colors.RESET}")
            if len(tid) >= 24:
                mdid = tid[4:8]
                print(f"   Manufacturer ID: {Colors.GREEN}0x{mdid}{Colors.RESET} (Impinj: E280)")
                print(f"   Tag Model: {Colors.YELLOW}0x{tid[8:12]}{Colors.RESET}")
                print(f"   Serial: {Colors.MAGENTA}{tid[12:]}{Colors.RESET}")
        
        time.sleep(0.1)
        
        # Read EPC
        epc = reader.read_epc()
        if epc:
            success_count += 1
        
        time.sleep(0.1)
        
        # Try to read Reserved (may fail if locked)
        reserved = reader.read_reserved()
        if reserved:
            success_count += 1
            print(f"   {Colors.YELLOW}Kill Password: {reserved['kill_password']}{Colors.RESET}")
            print(f"   {Colors.YELLOW}Access Password: {reserved['access_password']}{Colors.RESET}")
        
        time.sleep(0.1)
        
        # Try to read User memory (may not exist or be enabled)
        user = reader.read_user(word_count=2)
        if user:
            success_count += 1
        
        # Summary
        print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ Successfully read {success_count}/4 memory areas{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        
        # Instructions for write operations
        print(f"\n{Colors.CYAN}💡 To write data, uncomment the example code in main():{Colors.RESET}")
        print(f"{Colors.DIM}   - Write EPC: reader.write_epc('E280689400005000000CAFE'){Colors.RESET}")
        print(f"{Colors.DIM}   - Set passwords: reader.write_password(kill_password='...', access_password='...'){Colors.RESET}")
        print(f"{Colors.DIM}   - Lock memory: reader.lock_memory(LockTarget.EPC_MEMORY, LockAction.WRITABLE_SECURED, '12345678'){Colors.RESET}")
        
        # Success beep
        reader.beep(times=1)
        
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠️  Interrupted by user{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}✗ Error: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
    finally:
        reader.disconnect()


if __name__ == "__main__":
    main()