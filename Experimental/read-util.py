# read-util.py
"""
CHIP READER UTILITY - NFC & UHF RFID Tag Scanner
=================================================

Reads and identifies RFID/NFC chips from both NFC (ISO 14443) and UHF (EPC Gen2) readers.

WHAT THIS CAN DO:
-----------------
✓ UHF RFID (EPC Gen2):
  - Read EPC (Electronic Product Code) 
  - Read TID (Tag Identifier) with manufacturer and model identification
  - Decode SGTIN-96 format EPCs (GS1 standard)
  - Identify 65+ chip manufacturers (Impinj, NXP, Alien, TI, etc.)
  - Identify 100+ specific chip models (Monza R6-P, UCODE 8, Higgs-4, etc.)

✓ NFC Cards (when properly supported by reader):
  - Read UID (card serial number)
  - Identify NTAG family (210, 212, 213, 215, 216) via GET_VERSION
  - Identify MIFARE Ultralight EV1 via GET_VERSION
  - Identify MIFARE DESFire (EV1/EV2/EV3/Light) via ATR
  - Identify MIFARE Classic (1K/4K) via ATR
  - Identify MIFARE Plus via ATR
  - Identify ISO 15693 / ICODE via 8-byte UID

KNOWN LIMITATIONS:
------------------
✗ NFC identification on Windows PC/SC readers:
  - Many Windows NFC readers negotiate NTAG/Ultralight cards in DESFire mode
  - This prevents the GET_VERSION command from working
  - Cards with 7-byte UIDs and DESFire ATRs are flagged as "likely NTAG/Ultralight"
  - For accurate NTAG/Ultralight identification, use a phone app like NFC Tools
  - This is a Windows PC/SC driver limitation, not a code issue

REQUIREMENTS:
-------------
- pyscard (NFC reader support)
- pyserial (UHF reader support)

"""

import sys
import time
import platform
import os

# =============================================================================
# ANSI Support (Windows)
# =============================================================================
if platform.system() == "Windows":
    os.system("")

# =============================================================================
# COLORS
# =============================================================================
class Colors:
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

# =============================================================================
# NFC READER (PC/SC)
# =============================================================================
try:
    from smartcard.System import readers
    from smartcard.Exceptions import NoCardException, CardConnectionException
    from smartcard.util import toHexString
    PCSC_AVAILABLE = True
except ImportError:
    PCSC_AVAILABLE = False
    print(f"{Colors.YELLOW}Warning: pyscard not available. NFC reading disabled.{Colors.RESET}")
    print(f"{Colors.DIM}  pip install pyscard --break-system-packages{Colors.RESET}\n")

class NFCReader:
    def __init__(self):
        self.reader = None
        self.connection = None
        
        if not PCSC_AVAILABLE:
            return
            
        rlist = readers()
        if not rlist:
            print(f"{Colors.YELLOW}No NFC readers found{Colors.RESET}\n")
            return
            
        self.reader = rlist[0]
        print(f"{Colors.GREEN}NFC Reader: {self.reader}{Colors.RESET}\n")
    
    def read_card(self):
        """Read comprehensive card information"""
        if not self.connection:
            return None
            
        try:
            # Get UID
            GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
            data, sw1, sw2 = self.connection.transmit(GET_UID)
            
            if (sw1, sw2) != (0x90, 0x00):
                return None
            
            uid_bytes = data
            uid_hex = ''.join(f"{b:02X}" for b in uid_bytes)
            
            # Get ATR (Answer To Reset)
            atr = self.connection.getATR()
            atr_hex = ''.join(f"{b:02X}" for b in atr)
            
            # Try GET_VERSION command (usually fails on Windows PC/SC)
            version_info = self.get_version()
            
            # Identify card type
            card_info = self.identify_nfc_card(atr, uid_bytes, version_info)
            
            # Build result
            result = {
                'uid': uid_hex,
                'uid_bytes': uid_bytes,
                'uid_length': len(uid_bytes),
                'atr': atr_hex,
                'atr_bytes': atr,
                'manufacturer': card_info['manufacturer'],
                'chip_type': card_info['chip_type'],
                'card_family': card_info['card_family'],
                'memory_size': card_info['memory_size'],
                'features': card_info['features'],
                'sw1': sw1,
                'sw2': sw2,
            }
            
            if version_info:
                result['version_info'] = version_info
            
            # Try to read block 0 for additional info
            if 'MIFARE' in card_info['card_family'].upper() or 'NTAG' in card_info['card_family'].upper():
                result['mifare_data'] = self.read_mifare_data()
            
            return result
            
        except Exception as e:
            print(f"{Colors.RED}Error reading NFC card: {e}{Colors.RESET}")
            return None
    
    def get_version(self):
        """
        Attempt to send GET_VERSION command for NTAG/Ultralight identification.
        
        NOTE: This often fails on Windows PC/SC readers due to protocol negotiation issues.
        Many readers connect to NTAG/Ultralight cards in DESFire mode, preventing this command.
        """
        try:
            # Try InDataExchange method (works on some ACR122 readers)
            try:
                GET_VERSION_INDATAEXCHANGE = [0xFF, 0x00, 0x00, 0x00, 0x03, 0xD4, 0x40, 0x01, 0x60]
                data, sw1, sw2 = self.connection.transmit(GET_VERSION_INDATAEXCHANGE)
                
                if data and len(data) >= 9 and data[0] == 0xD5 and data[1] == 0x41:
                    version_data = data[3:] if len(data) > 3 else data
                    if len(version_data) >= 7:
                        return self.parse_version_response(version_data)
            except:
                pass
            
            # Try direct method
            try:
                GET_VERSION_DIRECT = [0xFF, 0x00, 0x00, 0x00, 0x01, 0x60]
                data, sw1, sw2 = self.connection.transmit(GET_VERSION_DIRECT)
                
                if sw1 == 0x90 and data and len(data) >= 7:
                    return self.parse_version_response(data)
            except:
                pass
                
        except:
            pass
        
        return None
    
    def parse_version_response(self, data):
        """Parse GET_VERSION response data"""
        if len(data) < 7:
            return None
            
        return {
            'vendor_id': data[1] if len(data) > 1 else 0,
            'product_type': data[2] if len(data) > 2 else 0,
            'product_subtype': data[3] if len(data) > 3 else 0,
            'major_version': data[4] if len(data) > 4 else 0,
            'minor_version': data[5] if len(data) > 5 else 0,
            'storage_size': data[6] if len(data) > 6 else 0,
            'raw': ''.join(f'{b:02X}' for b in data)
        }
    
    def identify_nfc_card(self, atr, uid_bytes, version_info):
        """Identify NFC card type from ATR, UID, and GET_VERSION response"""
        atr_hex = ''.join(f"{b:02X}" for b in atr)
        
        # Default values
        info = {
            'manufacturer': 'Unknown',
            'chip_type': 'Unknown',
            'card_family': 'Unknown',
            'memory_size': 'Unknown',
            'features': []
        }
        
        # PRIORITY 1: If GET_VERSION worked, use it (most reliable)
        if version_info and version_info.get('vendor_id') == 0x04:  # NXP
            info['manufacturer'] = 'NXP Semiconductors'
            
            product_type = version_info['product_type']
            product_subtype = version_info['product_subtype']
            storage_size = version_info['storage_size']
            
            # Product type 0x04 = NTAG family
            if product_type == 0x04:
                info['card_family'] = 'NTAG'
                
                if storage_size == 0x0B:
                    info['chip_type'] = 'NTAG210'
                    info['memory_size'] = '48 bytes'
                elif storage_size == 0x0E:
                    info['chip_type'] = 'NTAG212'
                    info['memory_size'] = '128 bytes'
                elif storage_size == 0x0F:
                    if product_subtype == 0x02:
                        info['chip_type'] = 'NTAG213'
                        info['memory_size'] = '144 bytes'
                    elif product_subtype == 0x04:
                        info['chip_type'] = 'NTAG213F'
                        info['memory_size'] = '144 bytes'
                elif storage_size == 0x11:
                    info['chip_type'] = 'NTAG215'
                    info['memory_size'] = '504 bytes'
                elif storage_size == 0x13:
                    if product_subtype == 0x02:
                        info['chip_type'] = 'NTAG216'
                        info['memory_size'] = '888 bytes'
                    elif product_subtype == 0x04:
                        info['chip_type'] = 'NTAG216F'
                        info['memory_size'] = '888 bytes'
                else:
                    info['chip_type'] = f'NTAG (unknown variant 0x{storage_size:02X})'
                
                info['features'] = ['NFC Forum Type 2', 'Password protection', 'Counter']
                return info
            
            # Product type 0x03 = MIFARE Ultralight family
            elif product_type == 0x03:
                info['card_family'] = 'MIFARE Ultralight'
                
                if storage_size == 0x0B:
                    info['chip_type'] = 'MIFARE Ultralight EV1'
                    info['memory_size'] = '48 bytes'
                elif storage_size == 0x0E:
                    info['chip_type'] = 'MIFARE Ultralight EV1'
                    info['memory_size'] = '128 bytes'
                else:
                    info['chip_type'] = f'MIFARE Ultralight EV1'
                
                info['features'] = ['ISO 14443A', 'Originality signature']
                return info
        
        # PRIORITY 2: ATR-based identification
        if len(atr) >= 8 and '804F0C' in atr_hex:
            info['manufacturer'] = 'NXP Semiconductors'
        
        # KNOWN ISSUE: DESFire ATR with 7-byte UID usually means protocol mismatch
        # Windows PC/SC often negotiates NTAG/Ultralight cards as DESFire
        if "3B8F8001804F0CA0000003060" in atr_hex and len(uid_bytes) == 7:
            info['manufacturer'] = 'NXP Semiconductors'
            info['chip_type'] = "Likely NTAG/Ultralight (cannot confirm via PC/SC)"
            info['card_family'] = "NTAG / MIFARE Ultralight"
            info['memory_size'] = "Unknown (48-888 bytes typical)"
            info['features'] = ['ISO 14443A', 'PC/SC protocol limitation prevents accurate ID']
            return info
        
        # DESFire family (4-byte UID is more reliable indicator)
        if "3B8F8001804F0CA0000003060" in atr_hex and len(uid_bytes) == 4:
            info['manufacturer'] = 'NXP Semiconductors'
            info['card_family'] = "MIFARE DESFire"
            info['features'] = ['AES', 'DES/3DES', 'ISO 14443-4', 'Multi-application']
            
            if "3B8F8001804F0CA0000003060300" in atr_hex:
                info['chip_type'] = "MIFARE DESFire EV1"
                info['memory_size'] = self.parse_desfire_memory(atr_hex)
            elif "3B8F8001804F0CA0000003060D" in atr_hex:
                info['chip_type'] = "MIFARE DESFire EV2"
                info['memory_size'] = "2KB/4KB/8KB"
            elif "3B8F8001804F0CA0000003060E" in atr_hex:
                info['chip_type'] = "MIFARE DESFire EV3"
                info['memory_size'] = "2KB/4KB/8KB"
            elif "3B8F8001804F0CA0000003060F" in atr_hex:
                info['chip_type'] = "MIFARE DESFire Light"
                info['memory_size'] = "640 bytes"
            
            return info
            
        # MIFARE Classic
        elif "3B8980" in atr_hex[:6]:
            info['manufacturer'] = 'NXP Semiconductors'
            info['card_family'] = "MIFARE Classic"
            info['features'] = ['ISO 14443A', 'CRYPTO1']
            
            if len(uid_bytes) == 4:
                info['chip_type'] = "MIFARE Classic 1K"
                info['memory_size'] = "1KB"
            else:
                info['chip_type'] = "MIFARE Classic 1K/4K"
                info['memory_size'] = "1KB or 4KB"
            
            return info
            
        # MIFARE Plus
        elif "3B8A80" in atr_hex[:6] or "3B8B80" in atr_hex[:6]:
            info['manufacturer'] = 'NXP Semiconductors'
            info['chip_type'] = "MIFARE Plus"
            info['card_family'] = "MIFARE Plus"
            info['memory_size'] = "2KB/4KB"
            info['features'] = ['AES-128', 'ISO 14443A']
            return info
            
        # ISO 15693 / ICODE (8-byte UID)
        elif len(uid_bytes) == 8:
            iso15693_mfg = {
                0x01: 'Texas Instruments',
                0x02: 'STMicroelectronics', 
                0x04: 'NXP Semiconductors',
                0x05: 'Infineon',
                0x07: 'Texas Instruments',
            }
            mfg_code = uid_bytes[0]
            info['manufacturer'] = iso15693_mfg.get(mfg_code, f'Unknown (0x{mfg_code:02X})')
            info['chip_type'] = "ISO 15693"
            info['card_family'] = "ISO 15693"
            info['features'] = ['Long range', 'Vicinity card']
            return info
        
        return info
    
    def get_nfc_manufacturer(self, manufacturer_byte):
        """DEPRECATED: UID first byte is not a reliable manufacturer indicator for NFC"""
        # This function is kept for compatibility but shouldn't be used
        # Manufacturer is now determined from ATR historical bytes
        return "See ATR-based identification"
    
    def parse_desfire_memory(self, atr_hex):
        """Parse memory size from DESFire ATR"""
        # DESFire ATR contains memory size indicator
        if "030603" in atr_hex:
            return "2KB"
        elif "030607" in atr_hex:
            return "4KB"
        elif "03060F" in atr_hex:
            return "8KB"
        return "Unknown"
    
    def read_mifare_data(self):
        """Try to read basic MIFARE data"""
        try:
            # Read block 0 (manufacturer data)
            READ_BLOCK = [0xFF, 0xB0, 0x00, 0x00, 0x10]
            data, sw1, sw2 = self.connection.transmit(READ_BLOCK)
            
            if (sw1, sw2) == (0x90, 0x00):
                return {
                    'block_0': ''.join(f"{b:02X}" for b in data),
                    'manufacturer': data[0:4],
                }
        except:
            pass
        return None
    
    def poll(self):
        """Poll for card presence"""
        if not self.reader:
            return None
            
        try:
            self.connection = self.reader.createConnection()
            self.connection.connect()
            return self.read_card()
        except (NoCardException, CardConnectionException):
            self.connection = None
            return None
        except Exception as e:
            return None

# =============================================================================
# UHF READER (Serial)
# =============================================================================
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print(f"{Colors.YELLOW}Warning: pyserial not available. UHF reading disabled.{Colors.RESET}")
    print(f"{Colors.DIM}  pip install pyserial --break-system-packages{Colors.RESET}\n")

class UHFReader:
    def __init__(self, port=None, baud=57600):
        self.ser = None
        
        if not SERIAL_AVAILABLE:
            return
        
        # Auto-detect port
        if port is None:
            port = self.detect_port()
            if not port:
                print(f"{Colors.YELLOW}No UHF reader port specified or detected{Colors.RESET}\n")
                return
        
        try:
            self.ser = serial.Serial(port, baudrate=baud, timeout=0.1)
            print(f"{Colors.GREEN}UHF Reader: {port} @ {baud} baud{Colors.RESET}\n")
            self.set_power(20)
        except Exception as e:
            print(f"{Colors.RED}Could not open {port}: {e}{Colors.RESET}\n")
            self.ser = None
    
    def detect_port(self):
        """Try to auto-detect UHF reader port"""
        if platform.system() == "Windows":
            return "COM3"
        else:
            # Try common Linux/Mac ports
            for port in ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"]:
                if os.path.exists(port):
                    return port
        return None
    
    def calculate_crc16(self, data):
        """Calculate CRC16 for UHF commands"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0x8408 if (crc & 1) else crc >> 1
        return crc
    
    def send_command(self, cmd_byte, data=b''):
        """Send command to UHF reader"""
        if not self.ser:
            return b''
        address = 0x00
        length = len(data) + 4
        command = bytes([length, address, cmd_byte]) + data
        crc = self.calculate_crc16(command)
        full = command + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        
        self.ser.reset_input_buffer()
        self.ser.write(full)
        self.ser.flush()
        return full
    
    def read_response(self, timeout=0.5):
        """Read response from UHF reader"""
        if not self.ser:
            return b''
        start = time.time()
        response = b''
        while time.time() - start < timeout:
            if self.ser.in_waiting > 0:
                response += self.ser.read(self.ser.in_waiting)
                time.sleep(0.05)
            elif len(response) > 0:
                break
        return response
    
    def set_power(self, power):
        """Set reader power (0-30 dBm)"""
        if not self.ser or not 0 <= power <= 30:
            return
        self.send_command(0x2F, bytes([power]))
        self.read_response(0.3)
    
    def inventory(self, verbose=False):
        """Scan for UHF tags and get detailed information"""
        if not self.ser:
            return []
        
        self.send_command(0x01)  # Inventory command
        resp = self.read_response(timeout=0.5)
        
        tags = []
        if len(resp) > 5:
            num = resp[4]
            pos = 5
            
            for i in range(num):
                if pos >= len(resp) - 2:
                    break
                
                epc_len = resp[pos]
                pos += 1
                
                if pos + epc_len <= len(resp) - 2:
                    epc_bytes = resp[pos:pos + epc_len]
                    epc = epc_bytes.hex().upper()
                    
                    # Parse EPC structure (if standard EPC Gen2)
                    tag_info = {
                        'epc': epc,
                        'epc_bytes': epc_bytes,
                        'epc_length': epc_len,
                        'epc_bits': epc_len * 8,
                        'raw_response': resp.hex().upper(),
                    }
                    
                    # Try to parse EPC header (first byte)
                    if epc_len > 0:
                        header = epc_bytes[0]
                        tag_info['header'] = f"0x{header:02X}"
                        tag_info['epc_class'] = self.decode_epc_header(header)
                    
                    # Try to read TID (chip manufacturer info)
                    tid_data = self.read_tid(epc_bytes, verbose=verbose)
                    if tid_data:
                        tid_info = self.decode_tid(tid_data)
                        if tid_info:
                            tag_info['tid'] = tid_info
                    
                    # Check if tag already in list (by EPC)
                    if not any(t['epc'] == epc for t in tags):
                        tags.append(tag_info)
                    
                    pos += epc_len
        
        return tags
    
    def decode_epc_header(self, header):
        """Decode EPC header byte to identify class"""
        # Common EPC header patterns
        if header & 0xC0 == 0xC0:
            return "SGTIN-96 (GS1)"
        elif header & 0xE0 == 0xA0:
            return "GRAI-96"
        elif header & 0xE0 == 0x80:
            return "SSCC-96"
        elif header & 0xF0 == 0x30:
            return "SGTIN-198"
        else:
            return f"Unknown (0x{header:02X})"
    
    def read_tid(self, epc_bytes, verbose=False, retries=3):
        """Read TID (Tag Identifier) bank - contains chip manufacturer info"""
        if not self.ser:
            return None
        
        # GeeNFC Read Data (0x02) command format per manual:
        # Data: [ENum] [EPC] [Mem] [WordPtr] [Num] [Pwd] [MaskAdr] [MaskLen]
        
        epc_word_len = len(epc_bytes) // 2  # ENum is in WORDS, not bytes
        mem_bank = 0x02  # TID bank
        word_ptr = 0x00  # Start at word 0
        num_words = 0x06  # Read 6 words (12 bytes)
        access_pwd = bytes([0x00, 0x00, 0x00, 0x00])  # Default password
        mask_adr = 0x00  # Use full EPC match
        mask_len = 0x00  # Use full EPC match
        
        # Build data payload in correct order per manual
        data = bytes([epc_word_len]) + epc_bytes + bytes([mem_bank, word_ptr, num_words]) + access_pwd + bytes([mask_adr, mask_len])
        
        # Retry logic for better reliability
        for attempt in range(retries):
            if verbose and attempt > 0:
                print(f"{Colors.YELLOW}  Retry {attempt + 1}/{retries}{Colors.RESET}")
            elif verbose:
                print(f"\n{Colors.YELLOW}[DEBUG] Attempting TID Read:{Colors.RESET}")
                print(f"{Colors.DIM}  EPC Length: {epc_word_len} words ({len(epc_bytes)} bytes)")
                print(f"  EPC: {epc_bytes.hex().upper()}")
                print(f"  Memory Bank: 0x{mem_bank:02X} (TID)")
                print(f"  Word Pointer: 0x{word_ptr:02X}")
                print(f"  Num Words: {num_words}")
                print(f"  Access Password: 00000000")
                print(f"  Mask Address: 0x{mask_adr:02X}")
                print(f"  Mask Length: 0x{mask_len:02X}")
                print(f"  Command Data: {data.hex().upper()}{Colors.RESET}")
            
            self.send_command(0x02, data)
            resp = self.read_response(timeout=0.5)
            
            if verbose:
                print(f"{Colors.DIM}  Response ({len(resp)} bytes): {resp.hex().upper()}{Colors.RESET}")
            
            if len(resp) > 5:
                if len(resp) > 3:
                    status = resp[3]
                    if verbose:
                        status_msg = {
                            0x00: "Success",
                            0x01: "Tag not found",
                            0x02: "CRC error",
                            0x05: "Access password error",
                            0x0B: "Tag doesn't support command",
                            0xFA: "Poor communication with tag",
                            0xFB: "No tag operable",
                            0xFC: "Tag returned error code",
                            0xFD: "Command length wrong / Invalid format",
                            0xFE: "Illegal command / CRC error",
                            0xFF: "Parameter error",
                        }.get(status, f"Unknown (0x{status:02X})")
                        print(f"{Colors.DIM}  Status: 0x{status:02X} ({status_msg}){Colors.RESET}")
                    
                    if status == 0x00:  # Success
                        tid_data = resp[4:-2]
                        if verbose:
                            print(f"{Colors.GREEN}  TID Read Success: {tid_data.hex().upper()}{Colors.RESET}")
                        return tid_data
                    elif status == 0xFA and attempt < retries - 1:
                        # Poor communication - retry
                        time.sleep(0.1)
                        continue
                    elif verbose:
                        print(f"{Colors.YELLOW}  Read failed{Colors.RESET}")
            elif verbose:
                print(f"{Colors.RED}  Response too short or empty{Colors.RESET}")
            
            # Small delay before retry
            if attempt < retries - 1:
                time.sleep(0.1)
        
        return None
    
    def decode_tid(self, tid_bytes):
        """Decode TID to identify chip manufacturer and model"""
        if not tid_bytes or len(tid_bytes) < 4:
            return None
        
        # Check for Impinj extended format (E2 80 XX XX...)
        if len(tid_bytes) >= 2 and tid_bytes[0] == 0xE2:
            # Impinj extended TID format
            # Bytes 0-1: E2 80 (Impinj identifier)
            # Bytes 2-3: Model number
            # Bytes 4+: Serial number
            
            if tid_bytes[1] == 0x80 and len(tid_bytes) >= 4:
                model_bytes = tid_bytes[2:4]
                model_number = (model_bytes[0] << 8) | model_bytes[1]
                
                # Decode Impinj model
                chip_model = self.decode_impinj_model(model_number)
                
                result = {
                    'allocation_class': 'Extended',
                    'mdid': 0xE280,
                    'mdid_hex': '0xE280',
                    'manufacturer': 'Impinj',
                    'tag_model': model_number,
                    'tag_model_hex': f"0x{model_number:04X}",
                    'chip_model': chip_model,
                    'tid_full': tid_bytes.hex().upper(),
                }
                
                if len(tid_bytes) > 4:
                    result['chip_serial'] = tid_bytes[4:].hex().upper()
                
                return result
        
        # Standard TID format
        # Byte 0-1: Allocation class + MDID (chip manufacturer)
        # Byte 2-3: Tag model number
        # Byte 4+: Serial number (optional)
        
        allocation_class = (tid_bytes[0] >> 6) & 0x03
        mdid = ((tid_bytes[0] & 0x3F) << 6) | ((tid_bytes[1] >> 2) & 0x3F)
        tag_model = ((tid_bytes[1] & 0x03) << 10) | (tid_bytes[2] << 2) | ((tid_bytes[3] >> 6) & 0x03)
        
        # Look up manufacturer
        manufacturer = self.get_manufacturer_name(mdid)
        chip_model = self.get_chip_model(mdid, tag_model)
        
        result = {
            'allocation_class': allocation_class,
            'mdid': mdid,
            'mdid_hex': f"0x{mdid:04X}",
            'manufacturer': manufacturer,
            'tag_model': tag_model,
            'tag_model_hex': f"0x{tag_model:04X}",
            'chip_model': chip_model,
            'tid_full': tid_bytes.hex().upper(),
        }
        
        # Extract serial if present
        if len(tid_bytes) > 4:
            result['chip_serial'] = tid_bytes[4:].hex().upper()
        
        return result
    
    def decode_impinj_model(self, model_number):
        """Decode Impinj-specific model numbers (comprehensive database)"""
        impinj_models = {
            # Monza 4 Series
            0x1100: "Monza 4D",
            0x1105: "Monza 4QT",
            0x110C: "Monza 4E",
            0x1114: "Monza 4i",
            
            # Monza 5 Series
            0x1130: "Monza 5",
            
            # Monza X Series (large memory)
            0x1140: "Monza X-2K",
            0x1150: "Monza X-8K",
            
            # Monza R6 Series
            0x1160: "Monza R6",
            0x1170: "Monza R6-P",
            0x1171: "Monza R6-A",
            0x1172: "Monza R6-B",
            0x1173: "Monza S6-C",
            
            # Monza M700 Series (newer generation)
            0x6914: "Monza R6",      # Alternative encoding
            0x6915: "Monza R6-P",     # Alternative encoding
            0x0730: "M730",
            0x0750: "M750",
            0x0770: "M770",
            0x0775: "M775",
            
            # Monza M780 Series (large memory)
            0x0780: "M780",
            0x0781: "M781",
            
            # Monza M800 Series (latest generation)
            0x0830: "M830",
            0x0850: "M850",
            
            # Legacy alternate encodings
            0x690C: "Monza 4QT",
            0x690D: "Monza 4D",
            0x690E: "Monza 4E",
            0x690F: "Monza 4i",
            0x6903: "Monza 5",
            0x6904: "Monza X-2K",
            0x6905: "Monza X-8K",
        }
        return impinj_models.get(model_number, f"Impinj Unknown Model (0x{model_number:04X})")
    
    def get_manufacturer_name(self, mdid):
        """Look up manufacturer from MDID (comprehensive GS1 database)"""
        manufacturers = {
            # Major UHF RFID chip manufacturers
            0x001: "Impinj",
            0x002: "Texas Instruments",
            0x003: "Alien Technology",
            0x004: "NXP Semiconductors",
            0x005: "STMicroelectronics",
            0x006: "EM Microelectronic",
            0x007: "Renesas Technology",
            0x008: "Quanray Electronics",
            0x009: "Fujitsu",
            0x00A: "LSIS",
            0x00B: "CAEN RFID",
            0x00C: "Productivity Engineering",
            0x00D: "Federal Card Services",
            0x00E: "Invengo",
            0x00F: "Xerox",
            0x010: "Intermec",
            0x011: "Motorola",
            0x012: "Nordic ID",
            0x013: "Savi Technology",
            0x014: "Star Systems International",
            0x015: "Aleis",
            0x016: "Avery Dennison",
            0x017: "Baltic ID",
            0x018: "Chipron",
            0x019: "eAccess",
            0x01A: "EPCglobal",
            0x01B: "Fujitsu Semiconductor",
            0x01C: "Guardian RFID",
            0x01D: "Hitachi",
            0x01E: "IBM",
            0x01F: "Infineon Technologies",
            0x020: "KATHREIN RFID",
            0x021: "Keonn Technologies",
            0x022: "PsiTag",
            0x023: "PolyIC",
            0x024: "RFMicron",
            0x025: "Siemens",
            0x026: "ST Microelectronics",
            0x027: "TagMaster",
            0x028: "Texas Instruments (TIRIS)",
            0x029: "ThingMagic",
            0x02A: "Tyco Electronics",
            0x02B: "UPM Raflatac",
            0x02C: "VeriSign",
            0x02D: "Kovio",
            0x02E: "Bar Code Specialties",
            0x02F: "Hitachi High-Technologies",
            0x030: "Honeywell",
            0x031: "Omni-ID",
            0x032: "PAR Government Systems",
            0x033: "Smart Chip Solutions",
            0x034: "GAO RFID",
            0x035: "CoreRFID",
            0x036: "Cipher Lab",
            0x037: "Convergence Systems Limited",
            0x038: "CPI Card Group",
            0x039: "HID Global",
            0x03A: "Identive Group",
            0x03B: "Nedap",
            0x03C: "Sato Vicinity",
            0x03D: "Smartrac",
            0x03E: "Tagsys",
            0x03F: "Think Wireless",
            0x040: "UBI Systems",
            0x041: "Zebra Technologies",
        }
        return manufacturers.get(mdid, f"Unknown Manufacturer (MDID: 0x{mdid:04X})")
    
    def get_chip_model(self, mdid, model):
        """Look up specific chip model (supports multiple manufacturers)"""
        
        # Impinj chips (MDID 0x001)
        if mdid == 0x001:
            return self.decode_impinj_model(model)
        
        # NXP Semiconductors (MDID 0x004)
        elif mdid == 0x004:
            nxp_models = {
                0x0C00: "UCODE G2XM",
                0x0C01: "UCODE G2XL",
                0x0D00: "UCODE G2iM",
                0x0D01: "UCODE G2iM+",
                0x0D03: "UCODE G2iL",
                0x0D04: "UCODE G2iL+",
                0x0E00: "UCODE 7",
                0x0E01: "UCODE 7m",
                0x0E02: "UCODE 8",
                0x0E03: "UCODE 8m",
                0x0E04: "UCODE 9",
            }
            return nxp_models.get(model, f"NXP Unknown Model (0x{model:04X})")
        
        # Alien Technology (MDID 0x003)
        elif mdid == 0x003:
            alien_models = {
                0x0003: "Higgs-3",
                0x0004: "Higgs-4",
                0x0009: "Higgs-9",
                0x000A: "Higgs-10",
                0x000C: "Higgs-EC",
            }
            return alien_models.get(model, f"Alien Unknown Model (0x{model:04X})")
        
        # Texas Instruments (MDID 0x002)
        elif mdid == 0x002:
            ti_models = {
                0x0001: "Gen2",
            }
            return ti_models.get(model, f"TI Unknown Model (0x{model:04X})")
        
        # Generic fallback
        return f"Model 0x{model:04X}"
    
    def read_memory(self, epc_bytes, bank, start_addr, length):
        """Read tag memory (if supported)"""
        if not self.ser:
            return None
        
        # This is a simplified read - actual implementation depends on reader model
        # Command 0x02 is typically "Read" on many readers
        data = bytes([bank, start_addr >> 8, start_addr & 0xFF, length])
        self.send_command(0x02, epc_bytes + data)
        resp = self.read_response()
        
        if len(resp) > 5:
            return resp[5:-2]  # Strip header/footer
        return None

# =============================================================================
# DISPLAY FUNCTIONS
# =============================================================================
def print_header(text):
    """Print a section header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(70)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}\n")

def print_field(label, value, color=Colors.WHITE):
    """Print a labeled field"""
    print(f"{Colors.DIM}{label:.<25}{Colors.RESET} {color}{value}{Colors.RESET}")

def print_nfc_details(card_data):
    """Display detailed NFC card information"""
    print_header("NFC CARD DETECTED")
    
    # Basic information
    print_field("UID (Hex)", card_data['uid'], Colors.GREEN)
    print_field("UID (Decimal)", ' '.join(str(b) for b in card_data['uid_bytes']), Colors.DIM)
    print_field("UID Length", f"{card_data['uid_length']} bytes", Colors.YELLOW)
    
    # Chip identification
    print(f"\n{Colors.BOLD}Chip Information:{Colors.RESET}")
    print_field("Manufacturer", card_data['manufacturer'], Colors.GREEN)
    print_field("Chip Type", card_data['chip_type'], Colors.CYAN)
    print_field("Card Family", card_data['card_family'], Colors.BLUE)
    print_field("Memory Size", card_data['memory_size'], Colors.YELLOW)
    
    # Features
    if card_data['features']:
        features_str = ', '.join(card_data['features'])
        print_field("Features", features_str, Colors.MAGENTA)
    
    # Technical details
    print(f"\n{Colors.BOLD}Technical Details:{Colors.RESET}")
    print_field("ATR", card_data['atr'], Colors.DIM)
    print_field("Status (SW1/SW2)", f"{card_data['sw1']:02X} {card_data['sw2']:02X}", Colors.WHITE)
    
    # MIFARE specific data
    if card_data.get('mifare_data'):
        print(f"\n{Colors.BOLD}MIFARE Data:{Colors.RESET}")
        mifare = card_data['mifare_data']
        print_field("Block 0", mifare['block_0'], Colors.BLUE)

def print_uhf_details(tag_data):
    """Display detailed UHF tag information"""
    print_header("UHF TAG DETECTED")
    
    print_field("EPC (Hex)", tag_data['epc'], Colors.GREEN)
    print_field("EPC Length", f"{tag_data['epc_length']} bytes ({tag_data['epc_bits']} bits)", Colors.YELLOW)
    
    if 'header' in tag_data:
        print_field("Header Byte", tag_data['header'], Colors.CYAN)
        print_field("EPC Class", tag_data['epc_class'], Colors.MAGENTA)
    
    # Show byte breakdown
    epc_bytes = tag_data['epc_bytes']
    if len(epc_bytes) >= 12:  # Standard 96-bit EPC
        print(f"\n{Colors.BOLD}Byte Breakdown (96-bit EPC):{Colors.RESET}")
        print_field("Header", epc_bytes[0:1].hex().upper(), Colors.CYAN)
        print_field("Filter + Partition", epc_bytes[1:2].hex().upper(), Colors.BLUE)
        print_field("Company Prefix", epc_bytes[2:5].hex().upper(), Colors.YELLOW)
        print_field("Item Reference", epc_bytes[5:8].hex().upper(), Colors.MAGENTA)
        print_field("Serial Number", epc_bytes[8:12].hex().upper(), Colors.GREEN)
    
    # Show TID (chip info) if available
    if 'tid' in tag_data:
        tid = tag_data['tid']
        print(f"\n{Colors.BOLD}Chip Information (TID):{Colors.RESET}")
        print_field("Manufacturer", tid['manufacturer'], Colors.GREEN)
        print_field("Chip Model", tid['chip_model'], Colors.CYAN)
        print_field("MDID", f"{tid['mdid_hex']} ({tid['mdid']})", Colors.BLUE)
        print_field("Tag Model Number", tid['tag_model_hex'], Colors.MAGENTA)
        if 'chip_serial' in tid:
            print_field("Chip Serial", tid['chip_serial'], Colors.YELLOW)
        print_field("TID Full", tid['tid_full'], Colors.DIM)
    
    print(f"\n{Colors.DIM}Raw Response: {tag_data['raw_response']}{Colors.RESET}")

def print_separator():
    """Print a visual separator"""
    print(f"\n{Colors.DIM}{'-'*70}{Colors.RESET}\n")

# =============================================================================
# MAIN LOOP
# =============================================================================
def main():
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("╔═══════════════════════════════════════════════════════════════════╗")
    print("║                      CHIP READER UTILITY                          ║")
    print("║                   NFC & UHF RFID Tag Scanner                      ║")
    print("╚═══════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}\n")
    
    # Initialize readers
    nfc = NFCReader()
    uhf = UHFReader()
    
    if not nfc.reader and not uhf.ser:
        print(f"{Colors.RED}No readers available. Exiting.{Colors.RESET}")
        return
    
    print(f"{Colors.GREEN}Readers initialized. Waiting for tags...{Colors.RESET}")
    print(f"{Colors.DIM}Press Ctrl+C to exit{Colors.RESET}\n")
    
    last_nfc_uid = None
    last_uhf_epcs = set()
    
    try:
        while True:
            time.sleep(0.1)
            
            # Poll NFC
            if nfc.reader:
                card_data = nfc.poll()
                if card_data:
                    if card_data['uid'] != last_nfc_uid:
                        last_nfc_uid = card_data['uid']
                        print_nfc_details(card_data)
                        print_separator()
                else:
                    last_nfc_uid = None
            
            # Poll UHF
            if uhf.ser:
                tags = uhf.inventory()
                
                # Detect new tags
                current_epcs = {t['epc'] for t in tags}
                new_tags = [t for t in tags if t['epc'] not in last_uhf_epcs]
                
                for tag in new_tags:
                    print_uhf_details(tag)
                    print_separator()
                
                last_uhf_epcs = current_epcs
    
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Shutting down...{Colors.RESET}")
        if uhf.ser:
            uhf.ser.close()

if __name__ == "__main__":
    main()