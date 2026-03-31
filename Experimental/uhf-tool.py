# uhf-tool.py

import serial
import struct
import time


class GeeNFCReaderPro:
    """
    Full-featured UR-2000 reader API.
    Supports:
    - Inventory (single & multi)
    - Read/Write EPC
    - Read/Write Reserved (passwords)
    - Read TID
    - General read/write memory bank
    - Lock operations
    - Beeper control
    """

    def __init__(self, port="COM3", baudrate=57600, addr=0x00, timeout=1.0):
        self.port = port
        self.baud = baudrate
        self.addr = addr
        self.timeout = timeout

        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            timeout=self.timeout,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
        )

    # -------------------------------------------------------------------------
    # CRC16 (poly 0x8408, preset 0xFFFF)
    # -------------------------------------------------------------------------

    def crc16(self, data: bytes) -> int:
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0x8408
                else:
                    crc >>= 1
        return crc & 0xFFFF

    # -------------------------------------------------------------------------
    # Frame builder + response parser
    # -------------------------------------------------------------------------

    def send_cmd(self, cmd: int, data: bytes = b"") -> bytes:
        length = len(data) + 4  # Adr, Cmd, CRC16(2)
        frame = bytes([length, self.addr, cmd]) + data

        crc = self.crc16(frame)
        frame += struct.pack("<H", crc)

        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()

        # read response header
        hdr = self.ser.read(1)
        if not hdr:
            raise TimeoutError("No response from reader")

        resp_len = hdr[0]
        rest = self.ser.read(resp_len)
        if len(rest) != resp_len:
            raise TimeoutError("Incomplete response frame")

        resp = hdr + rest
        return resp

    def parse_resp(self, resp: bytes):
        """
        Returns: (reCmd, status, data)
        resp format:
        [Len][Addr][reCmd][Status][Data...][CRC_L][CRC_H]
        """
        if len(resp) < 5:
            raise ValueError("Response too short")

        # verify CRC
        payload = resp[:-2]
        crc_recv = int.from_bytes(resp[-2:], "little")
        if self.crc16(payload) != crc_recv:
            raise ValueError("Response CRC mismatch")

        reCmd = resp[2]
        status = resp[3]
        data = resp[4:-2]  # exclude CRC
        return reCmd, status, data

    # -------------------------------------------------------------------------
    # Inventory (multi)
    # -------------------------------------------------------------------------

    def inventory(self):
        resp = self.send_cmd(0x01)
        reCmd, status, data = self.parse_resp(resp)

        if reCmd != 0x01:
            raise RuntimeError(f"Unexpected response reCmd={reCmd:02X}")

        if status not in (0x00, 0x01, 0x02):
            return []

        tags = []
        if len(data) == 0:
            return tags

        num = data[0]
        pos = 1

        for _ in range(num):
            if pos >= len(data):
                break

            epc_len = data[pos]
            pos += 1

            epc_bytes = data[pos:pos + epc_len]
            pos += epc_len

            tags.append(epc_bytes.hex().upper())

        return tags

    # -------------------------------------------------------------------------
    # Inventory single tag
    # -------------------------------------------------------------------------

    def inventory_single(self):
        resp = self.send_cmd(0x0F)
        reCmd, status, data = self.parse_resp(resp)
        if reCmd != 0x0F:
            raise RuntimeError("Bad response for inventory_single")

        if status != 0x00:
            return None

        if len(data) == 0:
            return None

        epc_len = data[0]
        epc = data[1:1 + epc_len].hex().upper()
        return epc

    # -------------------------------------------------------------------------
    # Read memory bank
    # -------------------------------------------------------------------------

    def read_data(self, mem, word_ptr, word_count, pwd=b"\x00\x00\x00\x00"):
        """
        mem: 0x00=reserved, 0x01=EPC, 0x02=TID, 0x03=USER
        """
        data = bytes([
            0x00,     # ENum = 0 (no EPC filter)
            mem,
            word_ptr,
            word_count,
        ]) + pwd + bytes([0x00, 0x00])  # mask

        resp = self.send_cmd(0x02, data)
        reCmd, status, rdata = self.parse_resp(resp)

        if reCmd != 0x02:
            raise RuntimeError("Unexpected read_data response")

        if status != 0x00:
            raise RuntimeError(f"read_data failed, status=0x{status:02X}")

        return rdata  # bytes, MSB-first words

    # -------------------------------------------------------------------------
    # Write memory bank
    # -------------------------------------------------------------------------

    def write_data(self, mem, word_ptr, words, pwd=b"\x00\x00\x00\x00"):
        """
        words: list of 16-bit ints
        """
        wnum = len(words)

        wbytes = b"".join(struct.pack(">H", w) for w in words)

        data = bytes([
            wnum,
            0x00,        # ENum
        ]) + bytes([]) + bytes([mem, word_ptr]) + wbytes + pwd + bytes([0x00, 0x00])

        resp = self.send_cmd(0x03, data)
        reCmd, status, _ = self.parse_resp(resp)

        if reCmd != 0x03:
            raise RuntimeError("Unexpected write_data response")

        if status != 0x00:
            raise RuntimeError(f"write_data failed, status=0x{status:02X}")

    # -------------------------------------------------------------------------
    # EPC helper functions
    # -------------------------------------------------------------------------

    def read_epc(self):
        return self.inventory_single()

    def write_epc(self, new_epc_hex, pwd=b"\x00\x00\x00\x00"):
        epc_bytes = bytes.fromhex(new_epc_hex)
        wlen = len(epc_bytes) // 2  # words

        data = bytes([wlen]) + pwd + epc_bytes

        resp = self.send_cmd(0x04, data)
        reCmd, status, _ = self.parse_resp(resp)

        if status != 0x00:
            raise RuntimeError(f"write_epc failed, status=0x{status:02X}")

    # -------------------------------------------------------------------------
    # Reserved memory helpers (Kill + Access passwords)
    # -------------------------------------------------------------------------

    def read_reserved(self, pwd=b"\x00\x00\x00\x00"):
        """Reads 4 words: KillPwd(2 words) + AccessPwd(2 words)"""
        data = self.read_data(mem=0x00, word_ptr=0x00, word_count=4, pwd=pwd)
        return data  # 8 bytes

    def write_access_password(self, new_pwd: bytes, current_pwd=b"\x00\x00\x00\x00"):
        """
        new_pwd: 4 bytes
        Writes to reserved words 2 & 3.
        """
        if len(new_pwd) != 4:
            raise ValueError("Password must be exactly 4 bytes")

        # two 16-bit words, MSB-first
        w1 = (new_pwd[0] << 8) | new_pwd[1]
        w2 = (new_pwd[2] << 8) | new_pwd[3]

        self.write_data(0x00, 0x02, [w1, w2], pwd=current_pwd)

    # -------------------------------------------------------------------------
    # TID helper
    # -------------------------------------------------------------------------

    def read_tid(self):
        """
        Reads 6 words (12 bytes) of TID (common length for Impinj).
        Adjust length as needed.
        """
        data = self.read_data(mem=0x02, word_ptr=0x00, word_count=6)
        return data.hex().upper()

    # -------------------------------------------------------------------------
    # Lock command (0x06)
    # -------------------------------------------------------------------------

    def lock(self, select, setprotect, pwd: bytes):
        """
        select:
            0x00 = Kill password
            0x01 = Access password
            0x02 = EPC
            0x03 = TID
            0x04 = USER

        setprotect:
            for passwords:
                0x00 = always RW
                0x01 = permanently RW
                0x02 = RW in secured state only (needs access pwd)
                0x03 = never RW
        """
        if len(pwd) != 4:
            raise ValueError("Password must be 4 bytes")

        data = bytes([
            0x00,       # ENum
            select,
            setprotect,
        ]) + pwd + bytes([0x00, 0x00])  # mask

        resp = self.send_cmd(0x06, data)
        reCmd, status, _ = self.parse_resp(resp)
        if status != 0x00:
            raise RuntimeError(f"Lock failed, select={select}, status=0x{status:02X}")

    # -------------------------------------------------------------------------
    # Beep
    # -------------------------------------------------------------------------

    def beep(self, active=3, silent=1, times=2):
        data = bytes([active, silent, times])
        resp = self.send_cmd(0x33, data)
        _, status, _ = self.parse_resp(resp)
        return status == 0x00

    # -------------------------------------------------------------------------
    # Require exactly one tag in field
    # -------------------------------------------------------------------------

    def require_single_tag(self, retries=3, delay=0.15):
        """
        Ensures exactly one tag is present in the field.
        Returns the EPC (hex string).
        
        Raises:
            RuntimeError("No tag detected")
            RuntimeError("Multiple tags detected: [...]")
        """

        for _ in range(retries):
            tags = self.inventory()
            unique_tags = list(set(tags))

            if len(unique_tags) == 1:
                return unique_tags[0]

            if len(unique_tags) > 1:
                raise RuntimeError(
                    f"Multiple tags detected: {unique_tags}. "
                    f"Remove all but one before continuing."
                )

            # len == 0 → retry
            time.sleep(delay)

        raise RuntimeError("No tag detected. Place a single tag on the reader.")

    # -------------------------------------------------------------------------

    def close(self):
        self.ser.close()
