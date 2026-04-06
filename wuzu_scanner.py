# wuzu_scanner.py
"""
WUZU SCANNER - Database-Integrated Version (2025)
With Bounded Terminal Panel System and Dynamic Panel Sizing
"""

import sys, time, shutil, os, platform, random
from datetime import datetime, timedelta
from collections import deque

# =============================================================================
# TOMLI / TOMLLIB
# =============================================================================
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Error: Please install tomli for Python < 3.11")
        print("  pip install tomli --break-system-packages")
        sys.exit(1)

# =============================================================================
# POSTGRESQL
# =============================================================================
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    print("Warning: psycopg2 not available. Install with:")
    print("  pip install psycopg2-binary --break-system-packages")


# =============================================================================
# ANSI Support (Windows)
# =============================================================================
if platform.system() == "Windows":
    os.system("")


# =============================================================================
# COLOR CONFIGURATION
# =============================================================================
COLORS = {
    "default": "\033[37m",
    "title": "\033[97m",
    "reset": "\033[0m",
}


# =============================================================================
# Cross-platform Key Reader
# =============================================================================
if platform.system() == "Windows":
    import msvcrt
    def read_key():
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                return ch.decode("utf-8")
            except:
                return None
        return None
else:
    import termios, tty, select
    def read_key():
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1)
        return None


# =============================================================================
# Terminal helper
# =============================================================================
class Terminal:
    def size(self):
        size = shutil.get_terminal_size(fallback=(80, 24))
        return size.columns, size.lines

    def clear(self):
        if platform.system() == "Windows":
            os.system("cls")
        else:
            print(f"\033[2J\033[H{COLORS['default']}", end="")

    def move_to(self, row, col):
        print(f"\033[{row+1};{col+1}H", end="")

    def clear_to_eol(self):
        print("\033[K", end="")

    def print_row(self, row, text, cols=None):
        if cols is None:
            cols, _ = self.size()
        self.move_to(row, 0)
        print(text.ljust(cols), end="")

    def print_centered_at(self, text, row):
        cols, _ = self.size()
        col = max(0, (cols - len(text)) // 2)
        self.move_to(row, col)
        print(text, end="")


# =============================================================================
# BOUNDED TERMINAL - Panel Rendering Context with Auto-Borders
# =============================================================================
class BoundedTerminal:
    """
    A constrained drawing context for a specific screen region.
    All coordinates are relative to the panel's top-left corner.
    Drawing outside the bounds is clamped/ignored.
    Automatically draws borders and handles panel title bars.
    """
    def __init__(self, terminal, start_row, end_row, start_col=0, end_col=None, 
                 draw_borders=True):
        self.terminal = terminal
        self.start_row = start_row
        self.end_row = end_row
        self.start_col = start_col
        
        term_cols, _ = terminal.size()
        self.end_col = end_col if end_col is not None else term_cols
        
        self.draw_borders = draw_borders
        
        # Clear the entire panel area first
        self._clear_panel()
        
        # Draw borders on creation if requested
        if self.draw_borders:
            self._draw_borders()
    
    def _clear_panel(self):
        """Clear the entire panel area before drawing"""
        cols = self.end_col - self.start_col
        empty_line = " " * cols
        for row in range(self.start_row, self.end_row):
            self.terminal.print_row(row, empty_line)
    
    def _draw_borders(self):
        """Draw the panel borders"""
        cols = self.end_col - self.start_col
        
        # Top border - always use ├─┤
        self.terminal.print_row(self.start_row, 
            "├" + "─" * (cols - 2) + "┤")
        
        # Side borders for all content rows
        border_end = self.end_row
        for row in range(self.start_row + 1, border_end):
            self.terminal.move_to(row, self.start_col)
            print("│", end="")
            self.terminal.move_to(row, self.end_col - 1)
            print("│", end="")
    
    def size(self):
        """Return the bounded panel size (cols, rows)"""
        return (self.end_col - self.start_col, 
                self.end_row - self.start_row)
    
    def content_size(self):
        """Return the content area size (excluding borders)"""
        cols, rows = self.size()
        return (cols - 2, rows)  # -2 for left/right borders
    
    def move_to(self, row, col):
        """Move cursor to panel-relative coordinates"""
        abs_row = self.start_row + row
        abs_col = self.start_col + col
        
        # Clamp to bounds
        if self.start_row <= abs_row < self.end_row:
            if self.start_col <= abs_col < self.end_col:
                self.terminal.move_to(abs_row, abs_col)
    
    def print_content(self, row, text):
        """Print content inside the borders (auto-insets by 1 col on each side)"""
        abs_row = self.start_row + row
        
        if self.start_row < abs_row < self.end_row:
            content_width = self.end_col - self.start_col - 4  # -4 for "│ " and " │"
            truncated = text[:content_width].ljust(content_width)
            self.terminal.move_to(abs_row, self.start_col + 2)  # +2 for "│ "
            print(truncated, end="")
    
    def print_row(self, row, text):
        """Print a full row including borders (for custom formatting)"""
        abs_row = self.start_row + row
        
        if self.start_row <= abs_row < self.end_row:
            width = self.end_col - self.start_col
            truncated = text[:width].ljust(width)
            self.terminal.print_row(abs_row, truncated, self.end_col)
    
    def set_title(self, title):
        """Draw a title bar at the top of the panel"""
        cols = self.end_col - self.start_col
        title_text = f"{COLORS['title']}[ {title} ]{COLORS['default']}"
        title_len = len(COLORS['title']) + len(COLORS['default'])
        self.terminal.print_row(self.start_row, 
            "├" + title_text.center(cols - 2 + title_len, "─") + "┤")
    
    def clear_content(self):
        """Clear all content inside the borders"""
        content_width = self.end_col - self.start_col - 4
        empty = " " * content_width
        for row in range(self.start_row + 1, self.end_row):
            self.terminal.move_to(row, self.start_col + 2)
            print(empty, end="")
    
    def print_centered(self, row, text):
        """Print centered text at panel-relative row (inside borders)"""
        content_width = self.end_col - self.start_col - 4
        if len(text) <= content_width:
            col = (content_width - len(text)) // 2
            self.terminal.move_to(self.start_row + row, self.start_col + 2 + col)
            print(text, end="")
    
    def clear_to_eol(self):
        """Clear to end of line (delegates to terminal)"""
        self.terminal.clear_to_eol()


# =============================================================================
# NFC READER
# =============================================================================
try:
    from smartcard.System import readers
    from smartcard.Exceptions import NoCardException, CardConnectionException
    PCSC_AVAILABLE = True
except ImportError:
    PCSC_AVAILABLE = False

GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]

class NFCReader:
    def __init__(self):
        self.reader = None
        self.connection = None
        self.current_uid = None
        self.card_present = False

        if not PCSC_AVAILABLE:
            print("[NFC] PCSC not available — demo mode.")
            return

        rlist = readers()
        if not rlist:
            print("[NFC] No NFC reader found — demo mode.")
            return

        self.reader = rlist[0]
        self.connection = self.reader.createConnection()
        print(f"[NFC] Using: {self.reader}")

    def poll_for_card(self):
        if not self.connection:
            return None
        try:
            self.connection.connect()
            if not self.card_present:
                data, sw1, sw2 = self.connection.transmit(GET_UID)
                if (sw1, sw2) == (0x90, 0x00):
                    uid = ''.join(f"{b:02x}" for b in data).lower()
                    self.current_uid = uid
                    self.card_present = True
                    return uid
            return None

        except (NoCardException, CardConnectionException):
            self.card_present = False
            self.current_uid = None
        except:
            pass

        return None


# =============================================================================
# UHF READER
# =============================================================================
try:
    import serial
    SERIAL_AVAILABLE = True
except:
    SERIAL_AVAILABLE = False

try:
    import hid as hidapi
    HID_AVAILABLE = True
except:
    HID_AVAILABLE = False


class UHFReader:
    def __init__(self, port=None, baud=57600):
        self.ser = None
        if not SERIAL_AVAILABLE:
            print("[UHF] Serial support unavailable - demo mode.")
            return

        # Auto-detect
        if port is None:
            if platform.system() == "Windows":
                port = "COM3"
            else:
                port = "/dev/ttyUSB0"

        try:
            self.ser = serial.Serial(port, baudrate=baud, timeout=0.1)
            print(f"[UHF] Opened {port}")
            self.set_power(20)
            self.get_reader_info()
        except Exception as e:
            print(f"[UHF] Could not open {port}: {e}")
            try:
                from serial.tools import list_ports
                ports = list(list_ports.comports())
                if ports:
                    print("[UHF] Available ports:",
                          ", ".join([p.device for p in ports]))
                else:
                    print("[UHF] No serial ports detected.")
            except:
                pass
            self.ser = None

    # --- CRC Helper ---------------------------------------------------------
    def calculate_crc16(self, data):
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0x8408 if (crc & 1) else crc >> 1
        return crc

    # --- Serial Command Helpers ---------------------------------------------
    def send_command(self, cmd_byte, data=b''):
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

    def read_response(self, timeout=0.05):
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

    # --- Inventory -----------------------------------------------------------
    def inventory(self):
        if not self.ser:
            return []
        self.send_command(0x01)
        resp = self.read_response(timeout=0.5)
        tags = []
        if len(resp) > 5:
            num = resp[4]
            pos = 5
            for _ in range(num):
                if pos >= len(resp) - 2:
                    break
                epc_len = resp[pos]
                pos += 1
                if pos + epc_len <= len(resp) - 2:
                    epc = resp[pos:pos + epc_len].hex().upper()
                    if not any(t['epc'] == epc for t in tags):
                        tags.append({
                            'epc': epc,
                            'epc_bytes': resp[pos:pos+epc_len],
                            'epc_len': epc_len,
                        })
                    pos += epc_len
        return tags

    def beep(self, active=2, silent=1, times=1):
        if not self.ser:
            return
        data = bytes([active, silent, times])
        self.send_command(0x33, data)
        self.read_response(0.3)

    def set_power(self, power):
        if not self.ser:
            return
        if not 0 <= power <= 30:
            raise ValueError("UHF power must be 0–30 dBm")
        self.send_command(0x2F, bytes([power]))
        self.read_response(0.3)

    def get_reader_info(self):
        if not self.ser:
            return
        print("[UHF] Fetching reader info...")
        self.send_command(0x21)
        resp = self.read_response()
        print(f"[UHF] Response: {resp.hex()}")

    @property
    def connected(self):
        return self.ser is not None


# =============================================================================
# SR3308 UHF READER (USB HID)
# =============================================================================
class SR3308Reader:
    """Yanzeo SR3308 UHF reader via USB HID.

    Same public interface as UHFReader so the app can use either.
    """
    _PREAMBLE_TX = 0x7C
    _PREAMBLE_RX = 0xCC
    _VID = 0x04D8
    _PID = 0x033F
    _CMD_INVENTORY = 0x20
    _CMD_GET_TX_PWR = 0x50
    _CMD_SET_TX_PWR = 0x51
    _CMD_PARA = 0x81
    _CMD_INFO = 0x82
    _CMD_SOUND = 0xBC
    _CMD_USB = 0xBD
    _MSG_CMD = 0x00
    _MSG_SET = 0x31
    _MSG_GET = 0x32

    def __init__(self):
        self.dev = None
        if not HID_AVAILABLE:
            print("[UHF] hidapi not available — SR3308 support disabled.")
            return
        self._connect()

    def _connect(self):
        """Find and connect to an SR3308 via USB HID."""
        try:
            devices = hidapi.enumerate(self._VID, self._PID)
        except Exception as e:
            print(f"[UHF] HID enumeration failed: {e}")
            return

        if not devices:
            return

        path = devices[0].get("path", b"")
        try:
            self.dev = hidapi.device()
            self.dev.open_path(path)
            self.dev.set_nonblocking(True)
            time.sleep(0.1)
        except Exception as e:
            print(f"[UHF] Could not open SR3308: {e}")
            self.dev = None
            return

        # Verify with INFO GET
        frames = self._send_receive(self._CMD_INFO, self._MSG_GET)
        if not frames:
            print("[UHF] SR3308 found but not responding — closing.")
            self.dev.close()
            self.dev = None
            return

        info = bytes(frames[0]["payload"]).decode("ascii", errors="replace").strip()
        print(f"[UHF] SR3308 connected via HID ({info})")

        # Check USB mode — warn if keyboard still active
        usb_frames = self._send_receive(self._CMD_USB, self._MSG_GET)
        if usb_frames and usb_frames[0]["len"] >= 1:
            mode = usb_frames[0]["payload"][0]
            if mode != 2:
                print(f"[UHF] WARNING: keyboard interface active (USB mode={mode}).")
                print("[UHF] Run detect_scanners.py to disable it.")

        # Set command-polled mode
        self._send_receive(self._CMD_PARA, self._MSG_SET, payload=bytes([0x01, 0x01]))

        # Set power
        self.set_power(20)

    @property
    def connected(self):
        return self.dev is not None

    # --- RCP Protocol Helpers ------------------------------------------------
    @staticmethod
    def _checksum(data):
        return (-sum(data)) & 0xFF

    def _build_frame(self, code, msg_type, payload=b""):
        header = bytes([
            self._PREAMBLE_TX, 0xFF, 0xFF,
            code, msg_type, len(payload),
        ])
        body = header + bytes(payload)
        return body + bytes([self._checksum(body)])

    def _extract_frames(self, buf):
        out = []
        while True:
            try:
                idx = buf.index(self._PREAMBLE_RX)
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

    def _send_receive(self, code, msg_type, payload=b"", timeout=0.8):
        if not self.dev:
            return []
        rcp = self._build_frame(code, msg_type, payload)
        report = bytearray(64)
        report[0] = 0x00
        report[1] = len(rcp)
        report[2:2+len(rcp)] = rcp
        try:
            self.dev.write(bytes(report))
        except Exception:
            return []

        buf = bytearray()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data = self.dev.read(64)
            except Exception:
                break
            if data:
                valid_len = data[0]
                if 0 < valid_len < len(data):
                    buf.extend(bytes(data[1:1+valid_len]))
                if self._PREAMBLE_RX in buf:
                    grace = time.time() + 0.15
                    while time.time() < grace:
                        try:
                            more = self.dev.read(64)
                        except Exception:
                            break
                        if more:
                            vl = more[0]
                            if 0 < vl < len(more):
                                buf.extend(bytes(more[1:1+vl]))
                    break
            else:
                time.sleep(0.01)

        return self._extract_frames(buf)

    # --- Public Methods (same interface as UHFReader) ------------------------
    def inventory(self):
        if not self.dev:
            return []
        frames = self._send_receive(self._CMD_INVENTORY, self._MSG_CMD, timeout=0.5)
        tags = []
        for f in frames:
            if f["code"] == self._CMD_INVENTORY and f["type_masked"] == 0x02:
                rec = self._parse_tag(f["payload"])
                if rec and not any(t['epc'] == rec['epc'] for t in tags):
                    tags.append(rec)
        return tags

    def _parse_tag(self, payload):
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
        i += 1  # skip antenna/tag-type byte
        if i < len(p) and p[i] == 0x00:
            i += 2
        if i + 2 > len(p):
            return None
        pc = p[i:i+2]
        epc_len = (pc[0] >> 3) * 2
        if epc_len == 0 or i + 2 + epc_len > len(p):
            return None
        epc_bytes = p[i+2:i+2+epc_len]
        return {
            'epc': bytes(epc_bytes).hex().upper(),
            'epc_bytes': bytes(epc_bytes),
            'epc_len': epc_len,
        }

    def beep(self, active=2, silent=1, times=1):
        if not self.dev:
            return
        self._send_receive(self._CMD_SOUND, self._MSG_CMD,
                           payload=bytes([active, silent, times]), timeout=0.5)

    def set_power(self, power):
        if not self.dev:
            return
        if not 0 <= power <= 30:
            raise ValueError("UHF power must be 0-30 dBm")
        self._send_receive(self._CMD_SET_TX_PWR, self._MSG_SET,
                           payload=bytes([power]))

    def get_reader_info(self):
        if not self.dev:
            return
        frames = self._send_receive(self._CMD_INFO, self._MSG_GET)
        if frames:
            info = bytes(frames[0]["payload"]).decode("ascii", errors="replace").strip()
            print(f"[UHF] SR3308: {info}")


def create_uhf_reader(config):
    """Create the appropriate UHF reader based on config or auto-detection."""
    hw = config.get('hardware', {})
    uhf_type = (hw.get('uhf_type') or '').lower()
    power = hw.get('uhf_power', 20)

    if uhf_type == 'sr3308':
        reader = SR3308Reader()
    elif uhf_type == 'ur2000':
        reader = UHFReader(port=hw.get('uhf_port'),
                           baud=hw.get('uhf_baudrate', 57600))
    else:
        # Auto-detect: try SR3308 HID first, then UR-2000 serial
        reader = SR3308Reader()
        if not reader.connected:
            reader = UHFReader(port=hw.get('uhf_port'),
                               baud=hw.get('uhf_baudrate', 57600))

    if reader.connected and power != 20:
        reader.set_power(power)

    return reader


# =============================================================================
# DATABASE MANAGER
# =============================================================================
class DatabaseManager:
    def __init__(self, config):
        self.conn = None
        if not POSTGRES_AVAILABLE:
            print("[DB] PostgreSQL support not available — demo mode")
            print("[DB] Install with: pip install psycopg2-binary --break-system-packages")
            return
            
        db_cfg = config.get('database', {})
        
        # Validate required config
        required = ['host', 'database', 'user', 'password']
        missing = [k for k in required if not db_cfg.get(k)]
        if missing:
            print(f"[DB] Missing required config keys: {', '.join(missing)}")
            print(f"[DB] Please configure [database] section in config.toml")
            return
            
        try:
            self.conn = psycopg2.connect(
                host=db_cfg.get('host'),
                port=db_cfg.get('port', 5432),
                database=db_cfg.get('database'),
                user=db_cfg.get('user'),
                password=db_cfg.get('password')
            )
            self.conn.autocommit = True  # Immediate writes
            print(f"[DB] Connected to {db_cfg.get('database')} at {db_cfg.get('host')}:{db_cfg.get('port', 5432)}")
        except psycopg2.OperationalError as e:
            print(f"[DB] Connection failed: {e}")
            print(f"[DB] Check that PostgreSQL is running and config.toml has correct credentials")
            self.conn = None
        except Exception as e:
            print(f"[DB] Unexpected error: {e}")
            self.conn = None
    
    # === HUNTERS ===
    def add_hunter(self, uid, name):
        """Add a new hunter"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO hunters (uid, name, points, last_seen)
                       VALUES (%s, %s, 0, NOW())""",
                    (uid, name)
                )
            return True
        except Exception as e:
            print(f"[DB] Error adding hunter: {e}")
            return False
    
    def update_hunter_name(self, uid, name):
        """Update a hunter's name"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE hunters SET name = %s WHERE uid = %s",
                    (name, uid)
                )
            return True
        except Exception as e:
            print(f"[DB] Error updating hunter name: {e}")
            return False

    def update_hunter_score(self, uid, points_to_add):
        """Add points to a hunter and update last_seen"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """UPDATE hunters 
                       SET points = points + %s, last_seen = NOW()
                       WHERE uid = %s""",
                    (points_to_add, uid)
                )
            return True
        except Exception as e:
            print(f"[DB] Error updating hunter score: {e}")
            return False
    
    def get_top_hunters(self, limit=10):
        """Get top hunters ordered by points"""
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT uid, name, points, last_seen
                       FROM hunters
                       ORDER BY points DESC, last_seen ASC, name ASC
                       LIMIT %s""",
                    (limit,)
                )
                return cur.fetchall()
        except Exception as e:
            print(f"[DB] Error fetching hunters: {e}")
            return []
    
    def get_hunter_rank(self, uid):
        """Get a hunter's rank (1-based position on leaderboard)"""
        if not self.conn:
            return None
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*) + 1
                       FROM hunters
                       WHERE points > (SELECT points FROM hunters WHERE uid = %s)
                          OR (points = (SELECT points FROM hunters WHERE uid = %s)
                              AND last_seen < (SELECT last_seen FROM hunters WHERE uid = %s))""",
                    (uid, uid, uid)
                )
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            print(f"[DB] Error fetching hunter rank: {e}")
            return None

    def get_hunter_total_wuzus(self, uid):
        """Get total unique wuzus a hunter has scanned (non-deleted SCORE events)"""
        if not self.conn:
            return 0
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(DISTINCT wuzu_epc)
                       FROM scan_events
                       WHERE hunter_uid = %s AND event_type = 'SCORE' AND deleted = FALSE""",
                    (uid,)
                )
                result = cur.fetchone()
                return result[0] if result else 0
        except:
            return 0

    def get_hunter_total_scans(self, uid):
        """Get total number of wuzu scans for a hunter (including duplicates across sessions)"""
        if not self.conn:
            return 0
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*)
                       FROM scan_events
                       WHERE hunter_uid = %s AND event_type = 'SCORE' AND deleted = FALSE""",
                    (uid,)
                )
                result = cur.fetchone()
                return result[0] if result else 0
        except:
            return 0

    def get_hunter(self, uid):
        """Get a single hunter by UID"""
        if not self.conn:
            return None
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT uid, name, points, last_seen FROM hunters WHERE uid = %s",
                    (uid,)
                )
                return cur.fetchone()
        except Exception as e:
            print(f"[DB] Error fetching hunter: {e}")
            return None
    
    def hunter_exists(self, uid):
        """Check if hunter exists"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM hunters WHERE uid = %s", (uid,))
                return cur.fetchone() is not None
        except:
            return False

    def hunter_name_exists(self, name):
        """Check if hunter name already exists (case-insensitive)"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM hunters WHERE LOWER(name) = LOWER(%s)", (name,))
                return cur.fetchone() is not None
        except:
            return False
    
    # === WUZUS ===
    def add_wuzu(self, epc, points_value=None):
        """Add a new wuzu tag"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO wuzus (epc, points_value)
                       VALUES (%s, %s)""",
                    (epc, points_value)
                )
            return True
        except Exception as e:
            print(f"[DB] Error adding wuzu: {e}")
            return False
    
    def wuzu_exists(self, epc):
        """Check if wuzu exists"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM wuzus WHERE epc = %s", (epc,))
                return cur.fetchone() is not None
        except:
            return False
    
    def increment_wuzu_found(self, epc):
        """Increment the times_found counter for a wuzu"""
        if not self.conn:
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE wuzus SET times_found = times_found + 1 WHERE epc = %s",
                    (epc,)
                )
        except Exception as e:
            print(f"[DB] Error incrementing wuzu count: {e}")
    
    def get_wuzu(self, epc):
        """Get a single wuzu by EPC"""
        if not self.conn:
            return None
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT epc, name, fact, points_value, times_found, deleted FROM wuzus WHERE epc = %s",
                    (epc,)
                )
                return cur.fetchone()
        except Exception as e:
            print(f"[DB] Error fetching wuzu: {e}")
            return None

    def update_wuzu(self, epc, name=None, points_value=None, fact=None):
        """Update wuzu fields (only non-None values)"""
        if not self.conn:
            return False
        try:
            updates = []
            values = []
            if name is not None:
                updates.append("name = %s")
                values.append(name)
            if points_value is not None:
                updates.append("points_value = %s")
                values.append(points_value)
            if fact is not None:
                updates.append("fact = %s")
                values.append(fact)
            if not updates:
                return False
            values.append(epc)
            with self.conn.cursor() as cur:
                cur.execute(
                    f"UPDATE wuzus SET {', '.join(updates)} WHERE epc = %s",
                    values
                )
            return True
        except Exception as e:
            print(f"[DB] Error updating wuzu: {e}")
            return False

    def get_wuzu_points(self, epc):
        """Get points value for a wuzu. Returns 0 for unknown or deleted wuzus."""
        if not self.conn:
            return 0
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT points_value FROM wuzus WHERE epc = %s AND deleted = FALSE", (epc,))
                result = cur.fetchone()
                return result[0] if result else 0
        except:
            return 0
    
    def soft_delete_wuzu(self, epc):
        """Soft-delete a wuzu by marking it as deleted"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("UPDATE wuzus SET deleted = TRUE WHERE epc = %s", (epc,))
            return True
        except Exception as e:
            print(f"[DB] Error deleting wuzu: {e}")
            return False

    def restore_wuzu(self, epc):
        """Restore a soft-deleted wuzu"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("UPDATE wuzus SET deleted = FALSE WHERE epc = %s", (epc,))
            return True
        except Exception as e:
            print(f"[DB] Error restoring wuzu: {e}")
            return False

    def wuzu_is_deleted(self, epc):
        """Check if a wuzu is soft-deleted"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT deleted FROM wuzus WHERE epc = %s", (epc,))
                result = cur.fetchone()
                return result[0] if result else False
        except:
            return False

    # === SCAN EVENTS ===
    def log_event(self, event_type, hunter_uid=None, wuzu_epc=None, details="", points=0, private=False):
        """Log a scan event"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO scan_events
                       (event_type, hunter_uid, wuzu_epc, details, points_awarded, private)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (event_type, hunter_uid, wuzu_epc, details, points, private)
                )
            return True
        except Exception as e:
            print(f"[DB] Error logging event: {e}")
            return False
    
    def get_recent_events(self, limit=50):
        """Get recent public, non-deleted scan events for main screen display"""
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT timestamp, event_type, hunter_uid, wuzu_epc,
                              details, points_awarded
                       FROM scan_events
                       WHERE deleted = FALSE AND private = FALSE
                       ORDER BY timestamp DESC
                       LIMIT %s""",
                    (limit,)
                )
                return cur.fetchall()
        except Exception as e:
            print(f"[DB] Error fetching events: {e}")
            return []
    
    # === ADMINS ===
    def admin_exists(self, uid):
        """Check if UID is an admin"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM admins WHERE uid = %s", (uid,))
                return cur.fetchone() is not None
        except:
            return False

    def add_admin(self, uid, name, password, created_by=None):
        """Add a new admin with password"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO admins (uid, name, password, created_by)
                       VALUES (%s, %s, %s, %s)""",
                    (uid, name, password, created_by)
                )
            return True
        except Exception as e:
            print(f"[DB] Error adding admin: {e}")
            return False

    def verify_admin_password(self, uid, password):
        """Verify admin password. Returns True if correct."""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT password FROM admins WHERE uid = %s", (uid,))
                result = cur.fetchone()
                if result:
                    return result[0] == password
                return False
        except:
            return False

    def get_admin(self, uid):
        """Get admin by UID"""
        if not self.conn:
            return None
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT uid, name, created_at FROM admins WHERE uid = %s", (uid,))
                return cur.fetchone()
        except:
            return None

    def admin_name_exists(self, name):
        """Check if admin name already exists (case-insensitive)"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 FROM admins WHERE LOWER(name) = LOWER(%s)", (name,))
                return cur.fetchone() is not None
        except:
            return False

    # === ADMIN OPERATIONS ===
    def get_hunter_scan_history(self, hunter_uid):
        """Get ALL scan events for a hunter including soft-deleted (for admin view)"""
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, timestamp, event_type, wuzu_epc, details,
                              points_awarded, deleted, deleted_by, admin_uid
                       FROM scan_events
                       WHERE hunter_uid = %s
                       ORDER BY timestamp DESC""",
                    (hunter_uid,)
                )
                return cur.fetchall()
        except Exception as e:
            print(f"[DB] Error fetching hunter history: {e}")
            return []

    def get_wuzu_scan_history(self, epc):
        """Get ALL scan events for a wuzu including soft-deleted (for admin view)"""
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, timestamp, event_type, hunter_uid, details,
                              points_awarded, deleted, deleted_by, admin_uid
                       FROM scan_events
                       WHERE wuzu_epc = %s
                       ORDER BY timestamp DESC""",
                    (epc,)
                )
                return cur.fetchall()
        except Exception as e:
            print(f"[DB] Error fetching wuzu history: {e}")
            return []

    # === SCAN VALIDATION ===
    def get_last_wuzu_event(self, epc, event_type):
        """Get most recent non-deleted event of given type for a wuzu EPC"""
        if not self.conn:
            return None
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, timestamp, hunter_uid, event_type, points_awarded
                       FROM scan_events
                       WHERE wuzu_epc = %s AND event_type = %s AND deleted = FALSE
                       ORDER BY timestamp DESC
                       LIMIT 1""",
                    (epc, event_type)
                )
                return cur.fetchone()
        except Exception as e:
            print(f"[DB] Error fetching last wuzu event: {e}")
            return None

    def get_last_wuzu_score_event(self, epc):
        """Get most recent non-deleted SCORE or OVERRIDE_SCORE event for a wuzu EPC"""
        if not self.conn:
            return None
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, timestamp, hunter_uid, event_type, points_awarded
                       FROM scan_events
                       WHERE wuzu_epc = %s AND event_type IN ('SCORE', 'OVERRIDE_SCORE')
                             AND deleted = FALSE
                       ORDER BY timestamp DESC
                       LIMIT 1""",
                    (epc,)
                )
                return cur.fetchone()
        except Exception as e:
            print(f"[DB] Error fetching last wuzu score event: {e}")
            return None

    def check_wuzu_scan_validity(self, epc, scoring_config):
        """Check if a wuzu scan is valid based on cooldown and scan-out rules.
        Returns (valid: bool, reason: str)"""
        cooldown_minutes = scoring_config.get('cooldown_minutes', 1)
        scan_out_enabled = scoring_config.get('scan_out', False)
        cooldown_overrides = scoring_config.get('cooldown_overrides_scan_out', False)

        last_score = self.get_last_wuzu_score_event(epc)
        last_scan_out = self.get_last_wuzu_event(epc, 'SCAN_OUT')

        # Valid scan-out: exists and is more recent than last score
        has_valid_scan_out = (
            last_scan_out is not None and
            (last_score is None or last_scan_out['timestamp'] > last_score['timestamp'])
        )

        # Cooldown check
        if cooldown_minutes == 0 or last_score is None:
            cooldown_expired = True
        else:
            elapsed = datetime.now() - last_score['timestamp']
            cooldown_expired = elapsed.total_seconds() >= cooldown_minutes * 60

        if scan_out_enabled:
            if has_valid_scan_out:
                return (True, "")
            if cooldown_overrides and cooldown_expired:
                return (True, "")
            return (False, "Scan-out required")
        else:
            if has_valid_scan_out:
                return (True, "")
            if cooldown_expired:
                return (True, "")
            return (False, "Rescan cooldown active")

    def soft_delete_event(self, event_id, admin_uid):
        """Soft delete a scan event and adjust hunter score atomically"""
        if not self.conn:
            return False
        try:
            old_autocommit = self.conn.autocommit
            self.conn.autocommit = False
            try:
                with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Get the event details
                    cur.execute(
                        "SELECT hunter_uid, points_awarded FROM scan_events WHERE id = %s AND deleted = FALSE",
                        (event_id,)
                    )
                    event = cur.fetchone()
                    if not event:
                        self.conn.rollback()
                        return False

                    # Mark event as deleted
                    cur.execute(
                        "UPDATE scan_events SET deleted = TRUE, deleted_by = %s WHERE id = %s",
                        (admin_uid, event_id)
                    )

                    # Subtract points from hunter
                    if event['points_awarded'] > 0 and event['hunter_uid']:
                        cur.execute(
                            """UPDATE hunters
                               SET points = GREATEST(0, points - %s)
                               WHERE uid = %s""",
                            (event['points_awarded'], event['hunter_uid'])
                        )

                    # Log the admin action (private)
                    cur.execute(
                        """INSERT INTO scan_events
                           (event_type, hunter_uid, details, admin_uid, private)
                           VALUES ('ADMIN_DELETE', %s, %s, %s, TRUE)""",
                        (event['hunter_uid'],
                         f"Deleted event #{event_id} ({event['points_awarded']}pts)",
                         admin_uid)
                    )

                    self.conn.commit()
                return True
            except:
                self.conn.rollback()
                raise
            finally:
                self.conn.autocommit = old_autocommit
        except Exception as e:
            print(f"[DB] Error soft-deleting event: {e}")
            return False

    def admin_adjust_score(self, hunter_uid, points, admin_uid, details=""):
        """Add an admin score adjustment"""
        if not self.conn:
            return False
        try:
            old_autocommit = self.conn.autocommit
            self.conn.autocommit = False
            try:
                with self.conn.cursor() as cur:
                    # Update hunter points
                    cur.execute(
                        """UPDATE hunters
                           SET points = GREATEST(0, points + %s), last_seen = NOW()
                           WHERE uid = %s""",
                        (points, hunter_uid)
                    )

                    # Log the adjustment event (private)
                    detail_text = details if details else f"Admin adjustment: {'+' if points >= 0 else ''}{points}pts"
                    cur.execute(
                        """INSERT INTO scan_events
                           (event_type, hunter_uid, details, points_awarded, admin_uid, private)
                           VALUES ('ADMIN_ADJUST', %s, %s, %s, %s, TRUE)""",
                        (hunter_uid, detail_text, points, admin_uid)
                    )

                    self.conn.commit()
                return True
            except:
                self.conn.rollback()
                raise
            finally:
                self.conn.autocommit = old_autocommit
        except Exception as e:
            print(f"[DB] Error adjusting score: {e}")
            return False

    def log_system_event(self, event_type, admin_uid=None, details="", private=False):
        """Log system events (SYSTEM_START, SYSTEM_QUIT, ADMIN_PASSWORD_FAIL, etc.)"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO scan_events
                       (event_type, details, admin_uid, private)
                       VALUES (%s, %s, %s, %s)""",
                    (event_type, details, admin_uid, private)
                )
            return True
        except Exception as e:
            print(f"[DB] Error logging system event: {e}")
            return False

    def get_recent_admin_events(self, limit=20):
        """Get recent admin-related events for admin screen"""
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT timestamp, event_type, hunter_uid, details, admin_uid
                       FROM scan_events
                       WHERE event_type IN ('ADMIN_DELETE', 'ADMIN_ADJUST', 'ADMIN_ADD',
                                            'SYSTEM_START', 'SYSTEM_QUIT', 'ADMIN_PASSWORD_FAIL')
                       ORDER BY timestamp DESC
                       LIMIT %s""",
                    (limit,)
                )
                return cur.fetchall()
        except Exception as e:
            print(f"[DB] Error fetching admin events: {e}")
            return []

    def get_all_recent_events(self, limit=50):
        """Get ALL recent scan events for admin view (including private and deleted)"""
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT timestamp, event_type, hunter_uid, wuzu_epc,
                              details, points_awarded, deleted, private
                       FROM scan_events
                       ORDER BY timestamp DESC
                       LIMIT %s""",
                    (limit,)
                )
                return cur.fetchall()
        except Exception as e:
            print(f"[DB] Error fetching all events: {e}")
            return []

    def test_connection(self):
        """Test database connection and return status info"""
        if not self.conn:
            return {'status': 'OFFLINE', 'version': None, 'host': None}
        
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()[0]
                
                # Get host from connection
                host = self.conn.info.host
                
                # Determine status based on host
                if host in ['localhost', '127.0.0.1', '::1']:
                    status = 'LOCAL'
                else:
                    status = 'REMOTE'
                
                return {
                    'status': status,
                    'version': version,
                    'host': host
                }
        except Exception as e:
            print(f"[DB] Connection test failed: {e}")
            return {'status': 'OFFLINE', 'version': None, 'host': None}
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("[DB] Connection closed")

# =============================================================================
# PANEL NAME CONSTANTS
# =============================================================================
PANEL_TITLE     = "title_bar"
PANEL_STATUS    = "status_bar"
PANEL_MAIN      = "main"
PANEL_SECONDARY = "secondary"
PANEL_FOOTER    = "footer"

ALL_PANELS = [
    PANEL_TITLE,
    PANEL_STATUS,
    PANEL_MAIN,
    PANEL_SECONDARY,
    PANEL_FOOTER,
]

# =============================================================================
# TUI ENGINE WITH DYNAMIC PANEL SIZING
# =============================================================================
class TUIEngine:
    def __init__(self):
        self.panels = {panel: True for panel in ALL_PANELS} # All panels start dirty

    def mark_dirty(self, panel):
        """Mark a panel for re-rendering"""
        if panel in self.panels:
            self.panels[panel] = True

    def force_full_redraw(self):
        """Mark all panels dirty"""
        for p in self.panels:
            self.panels[p] = True

    def get_layout(self, cols, rows, screen):
        """
        Define the physical panel layout based on screen preferences.
        Returns dict of panel_name -> (start_row, end_row)
        """
        TITLE_BAR_H = 1
        STATUS_BAR_H = 1
        FOOTER_H = 4
        available = rows - (STATUS_BAR_H + FOOTER_H + TITLE_BAR_H)
        
        # Ask the screen how it wants to divide the available space
        sizes = screen.get_panel_sizes(available)
        
        main_h = sizes.get('main', 16)
        sec_h = sizes.get('secondary')

        if sec_h is None:
            # Screen explicitly does not want a secondary panel
            sec_h = 0
            main_h = min(main_h, available)
        else:
            # Screen wants a secondary panel — guarantee at least 2 rows
            min_secondary = 2
            sec_h = max(sec_h, min_secondary)
            if main_h + sec_h > available:
                main_h = available - sec_h
            main_h = max(main_h, 1)
        
        #Define panel layout (start_row, end_row)
        layout = {}
        layout[PANEL_TITLE] = (0, TITLE_BAR_H)
        layout[PANEL_MAIN] = (TITLE_BAR_H, TITLE_BAR_H + main_h)        
        # Only add secondary if it has height
        if sec_h > 0:
            layout[PANEL_SECONDARY] = (TITLE_BAR_H + main_h, TITLE_BAR_H + main_h + sec_h)
        layout[PANEL_FOOTER] = (rows - FOOTER_H - 1, rows - 1)
        layout[PANEL_STATUS] = (rows -1, rows)

        return layout

    def render(self, screen, terminal, app_state):
        """Render all dirty panels"""
        cols, rows = terminal.size()
        layout = self.get_layout(cols, rows, screen)
        borders = screen.use_borders()

        for panel_name, dirty in self.panels.items():
            # Skip clean panels
            if not dirty:
                continue

            # Skip panels not in layout (e.g., secondary with 0 height)
            if panel_name not in layout:
                continue

            # Get panel bounds
            start_row, end_row = layout[panel_name]

            # Create bounded terminal
            if panel_name == PANEL_STATUS or not borders:
                # Status bar or borderless screens: no borders
                bounded = BoundedTerminal(terminal, start_row, end_row, 0, cols,
                                        draw_borders=False)
            else:
                # All other panels: standard borders
                bounded = BoundedTerminal(terminal, start_row, end_row, 0, cols,
                                        draw_borders=True)
            
            # Call screen's render method for this panel
            if panel_name == PANEL_STATUS:
                screen.render_status_bar(bounded, app_state)
            elif panel_name == PANEL_MAIN:
                screen.render_main(bounded, app_state)
            elif panel_name == PANEL_SECONDARY:
                screen.render_secondary(bounded, app_state)
            elif panel_name == PANEL_FOOTER:
                screen.render_footer(bounded, app_state)
            elif panel_name == PANEL_TITLE:
                screen.render_title_bar(bounded)                
            else:
                # Optional: catch unknown panels
                print(f"[WARN] No render function for panel '{panel_name}'")

            # Mark panel as clean            
            self.panels[panel_name] = False

        sys.stdout.flush()


# =============================================================================
# SCREEN BASE CLASS
# =============================================================================
class Screen:
    """Base screen with panel rendering methods."""

    def __init__(self, app):
        self.app = app
        self.screen_main_title = app.config.get('display', {}).get('main_title', 'Wuzu Scanner')

    # -------------------------------------------------------------------------
    # BORDER CONTROL (Override in subclasses for borderless screens)
    # -------------------------------------------------------------------------
    def use_borders(self):
        """Return True for bordered panels, False for borderless (e.g. screen saver)"""
        return True

    # -------------------------------------------------------------------------
    # PANEL SIZING (Override in subclasses to customize layout)
    # -------------------------------------------------------------------------
    def get_panel_sizes(self, available_rows):
        """
        Return desired sizes for main and secondary panels.
        Override this in subclasses to customize the layout.
        
        Args:
            available_rows: Total rows available for main + secondary panels
            
        Returns:
            dict with 'main' and 'secondary' keys (values are row counts)
        """
        return {
            'main': 16,
            'secondary': available_rows - 16
        }


    # -------------------------------------------------------------------------
    # TITLE BAR (never changes, always in base class)
    # -------------------------------------------------------------------------
    def render_title_bar(self, bounded):
        """Render the main title bar - same for all screens"""
        cols, _ = bounded.size()
      
        title_bar = f"╒═╡  " + self.screen_main_title + "  ╞═"
        cols = bounded.end_col - bounded.start_col
        title_bar += "═" * (cols - len(title_bar) - 1) + "╕"
        
        # Just print the status text, no borders
        bounded.print_row(0, title_bar.ljust(cols))


    # -------------------------------------------------------------------------
    # STATUS BAR (never changes, always in base class)
    # -------------------------------------------------------------------------
    def render_status_bar(self, bounded, app_state):
        """Render the status bar - same for all screens"""
        cols, _ = bounded.size()

        uptime = format_uptime(time.time() - app_state["start"])
        now = time.strftime("%H:%M:%S")

        db_status = self.app.db_status

        right_part = f"═╡ DB:{db_status} - UPTIME:{uptime} - TIME:{now} ╞═╛"

        timeout_info = self.get_active_timeout()
        if timeout_info:
            label, remaining = timeout_info
            left_part = f"╘═╡ {label}: {remaining}s ╞"
        else:
            left_part = "╘"

        fill_len = max(0, cols - len(left_part) - len(right_part))
        status_bar = left_part + "═" * fill_len + right_part

        bounded.print_row(0, status_bar)

    # -------------------------------------------------------------------------
    # MAIN PANEL (Override in subclasses)
    # -------------------------------------------------------------------------
    def render_main(self, bounded, app_state):
        """Override this to render main content"""
        bounded.set_title("MAIN PANEL")

    # -------------------------------------------------------------------------
    # SECONDARY PANEL (Override in subclasses)
    # -------------------------------------------------------------------------
    def render_secondary(self, bounded, app_state):
        """Override this to render secondary content"""
        bounded.set_title("SECONDARY PANEL")

    # -------------------------------------------------------------------------
    # FOOTER PANEL (Override in subclasses)
    # -------------------------------------------------------------------------
    def render_footer(self, bounded, app_state):
        """Override this to render footer controls"""
        bounded.set_title(PANEL_FOOTER)

    def get_active_timeout(self):
        """Return (label, remaining_seconds) or None if no active timeout."""
        return None

    # Default no-op handler
    def handle(self, key, uid):
        pass


# =============================================================================
# START SCREEN
# =============================================================================
class StartScreen(Screen):
    STATE_NORMAL = "normal"
    STATE_UNKNOWN_PROMPT = "unknown_prompt"

    def __init__(self, app):
        super().__init__(app)
        app.authenticated_admin = None
        self.state = self.STATE_NORMAL
        self.unknown_uid = None
        self.unknown_prompt_time = None
        self.last_activity = time.time()
        self.idle_timeout = app.config.get('timing', {}).get('idle_timeout', 120)
        self.unknown_tag_timeout = app.config.get('timing', {}).get('unknown_tag_timeout', 10)

    def get_panel_sizes(self, available_rows):
        """Default layout: 16 rows for leaderboard, rest for event log"""
        return {
            'main': 16,
            'secondary': available_rows - 16
        }

    def get_active_timeout(self):
        if self.state == self.STATE_UNKNOWN_PROMPT and self.unknown_prompt_time:
            left = max(0, int(self.unknown_tag_timeout - (time.time() - self.unknown_prompt_time)))
            return ("UNKNOWN TAG", left)
        return None

    def handle(self, key, uid):
        if key or uid:
            self.last_activity = time.time()

        # Handle unknown tag prompt state
        if self.state == self.STATE_UNKNOWN_PROMPT:
            if self.unknown_prompt_time and time.time() - self.unknown_prompt_time > self.unknown_tag_timeout:
                self.app.log_event("TIMEOUT", details="Unregistered badge prompt timed out")
                self.state = self.STATE_NORMAL
                self.unknown_uid = None
                self.unknown_prompt_time = None
                self.app.tui.force_full_redraw()
                return
            if uid:
                # A badge scan during prompt — handle normally
                if self.app.db.admin_exists(uid):
                    self.app.switch_screen(AdminScreen(self.app, uid))
                    return
                elif self.app.db.hunter_exists(uid):
                    self.app.beep("hunter_id")
                    self.app.switch_screen(ScanWuzuScreen(self.app, uid))
                    return
            if key in ["y", "\r"]:
                self.app.switch_screen(AddHunterScreen(self.app, uid=self.unknown_uid))
                return
            elif key in ["n", "x"]:
                self.app.log_event("UNKNOWN", details="Unregistered badge scanned")
                self.state = self.STATE_NORMAL
                self.unknown_uid = None
                self.unknown_prompt_time = None
                self.app.tui.force_full_redraw()
                return
            return

        if key == "a":
            self.app.switch_screen(AddHunterScreen(self.app))
        elif key == "r":
            self.app.tui.force_full_redraw()
        elif uid:
            if self.app.db.admin_exists(uid):
                self.app.switch_screen(AdminScreen(self.app, uid))
                return
            elif self.app.db.hunter_exists(uid):
                self.app.beep("hunter_id")
                self.app.switch_screen(ScanWuzuScreen(self.app, uid))
            else:
                self.unknown_uid = uid
                self.unknown_prompt_time = time.time()
                self.state = self.STATE_UNKNOWN_PROMPT
                self.app.tui.force_full_redraw()

        # Check idle timeout for screen saver
        if time.time() - self.last_activity > self.idle_timeout:
            self.app.switch_screen(ScreenSaverScreen(self.app))

    def render_main(self, bounded, app_state):
        """Render top hunters leaderboard"""
        bounded.set_title("TOP HUNTERS")
        
        # Header row
        header = f"{'RANK':<5} {'NAME':<20} {'PTS':<6} {'LAST SEEN':<10}"
        bounded.print_content(1, header)
        bounded.print_content(2, "-" * 45)

        # Query hunters
        hunters = self.app.db.get_top_hunters(10)

        for i, hunter in enumerate(hunters, start=1):
            last = hunter.get("last_seen")
            age = format_ago(last.timestamp()) if last else "--"
            rank = f"{i:02d}"
            row = f"{rank:<5} {hunter['name']:<20} {hunter['points']:<6} {age:<10}"
            bounded.print_content(2 + i, row)

    def render_secondary(self, bounded, app_state):
        """Render scan event log"""
        bounded.set_title("SCAN EVENT LOG")

        # Query recent events
        content_cols, content_rows = bounded.content_size()
        events = self.app.db.get_recent_events(content_rows - 1)

        for i, evt in enumerate(events, start=1):
            ts = evt['timestamp'].strftime("%H:%M:%S")
            line = f"{ts} {evt['event_type']:<10} {evt['details']}"
            bounded.print_content(i, line[:content_cols])

    def render_footer(self, bounded, app_state):
        """Render operator controls"""
        bounded.set_title("OPERATOR PANEL")
        if self.state == self.STATE_UNKNOWN_PROMPT:
            bounded.print_content(1, f"Unregistered tag detected: {self.unknown_uid}")
            bounded.print_content(2, "Add new hunter? [Y/n]")
        else:
            bounded.print_content(1, "[A] Add Hunter  [R] Redraw Screen")
            bounded.print_content(2, "Scan hunter badge to begin scoring...")


# =============================================================================
# SCREEN SAVER SCREEN
# =============================================================================
class ScreenSaverScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.interval = app.config.get('timing', {}).get('screensaver_interval', 5)
        self.last_move = 0  # Force immediate reposition on first render
        self.text_x = 0
        self.text_y = 0
        self.prompt_text = "Scan Hunter Tag To Begin ------>"

    def use_borders(self):
        return False

    def get_panel_sizes(self, available_rows):
        return {'main': available_rows, 'secondary': None}

    def handle(self, key, uid):
        if uid:
            # Check admin first — admins never score
            if self.app.db.admin_exists(uid):
                self.app.switch_screen(AdminScreen(self.app, uid))
                return
            elif self.app.db.hunter_exists(uid):
                self.app.beep("hunter_id")
                self.app.switch_screen(ScanWuzuScreen(self.app, uid))
                return
            else:
                start = StartScreen(self.app)
                start.unknown_uid = uid
                start.state = StartScreen.STATE_UNKNOWN_PROMPT
                self.app.switch_screen(start)
                return

        if key:
            # Any key press returns to main screen
            self.app.switch_screen(StartScreen(self.app))
            return

        # Move text periodically
        now = time.time()
        if now - self.last_move >= self.interval:
            self._reposition()
            self.last_move = now
            self.app.tui.force_full_redraw()

    def _reposition(self):
        cols, rows = self.app.terminal.size()
        text_len = len(self.prompt_text)
        # Bound to middle ~60% of screen
        margin_x = cols // 5
        margin_y = rows // 5
        max_x = cols - margin_x - text_len - 1
        max_y = rows - margin_y
        self.text_x = random.randint(margin_x, max(margin_x, max_x))
        self.text_y = random.randint(margin_y, max(margin_y, max_y))

    def render_title_bar(self, bounded):
        pass

    def render_status_bar(self, bounded, app_state):
        pass

    def render_footer(self, bounded, app_state):
        pass

    def render_main(self, bounded, app_state):
        # Position the floating text directly on the terminal
        self.app.terminal.move_to(self.text_y, self.text_x)
        print(self.prompt_text, end="")


# =============================================================================
# ADD HUNTER SCREEN
# =============================================================================
class AddHunterScreen(Screen):
    STATE_SCAN = "scan"
    STATE_NAME = "name"
    STATE_CONFIRM = "confirm"
    STATE_ERROR = "error"

    def __init__(self, app, uid=None):
        super().__init__(app)
        if uid:
            self.uid = uid
            self.state = self.STATE_NAME
        else:
            self.uid = None
            self.state = self.STATE_SCAN
        self.name_input = ""
        self.error_msg = ""

    def get_panel_sizes(self, available_rows):
        """This screen wants all space for the form, no secondary panel"""
        return {
            'main': available_rows,
            'secondary': None
        }

    def handle(self, key, uid):
        if key == "r" and self.state in (self.STATE_SCAN, self.STATE_CONFIRM):
            self.app.tui.force_full_redraw()
            return

        if self.state == self.STATE_SCAN:
            if key == "x":
                self.app.log_event("CANCEL", details="Add-Hunter cancelled")
                self.app.switch_screen(StartScreen(self.app))
                return
            if uid:
                if self.app.db.admin_exists(uid):
                    self.error_msg = "This badge is registered as an admin!"
                    self.state = self.STATE_ERROR
                elif self.app.db.hunter_exists(uid):
                    self.app.log_event("DUPLICATE", details="Hunter badge already registered")
                    self.error_msg = "This badge is already registered!"
                    self.state = self.STATE_ERROR
                else:
                    self.uid = uid
                    self.state = self.STATE_NAME
                self.app.tui.force_full_redraw()

        elif self.state == self.STATE_NAME:
            if key in ["\n", "\r"]:
                if self.name_input.strip():
                    self.state = self.STATE_CONFIRM
                    self.app.tui.force_full_redraw()
            elif key == "\x7f" or key == "\x08":
                self.name_input = self.name_input[:-1]
                self.app.tui.mark_dirty(PANEL_MAIN)
            elif key and len(key) == 1 and (key.isalnum() or key in ' -'):
                self.name_input += key
                self.app.tui.mark_dirty(PANEL_MAIN)

        elif self.state == self.STATE_CONFIRM:
            if key == "x":
                self.app.log_event("CANCEL", details="Add-Hunter cancelled")
                self.app.switch_screen(StartScreen(self.app))
                return
            if key in ["y", "\n", "\r"]:
                name = self.name_input.strip()
                if self.app.db.hunter_name_exists(name):
                    self.error_msg = f"Name '{name}' already taken!"
                    self.state = self.STATE_ERROR
                else:
                    self.app.register_hunter(self.uid, name)
                    self.app.switch_screen(StartScreen(self.app))
                    return
                self.app.tui.force_full_redraw()
            elif key == "n":
                self.state = self.STATE_NAME
                self.app.tui.force_full_redraw()

        elif self.state == self.STATE_ERROR:
            if key:
                self.app.switch_screen(StartScreen(self.app))

    def render_main(self, bounded, app_state):
        """Render the add hunter form"""
        bounded.set_title("ADD NEW HUNTER")
        
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 8) // 2 + 1
        
        if self.state == self.STATE_SCAN:
            bounded.print_centered(start_row + 1, "Place hunter badge on NFC reader...")
            
        elif self.state == self.STATE_NAME:
            bounded.print_content(start_row + 1, f"UID Scanned: {self.uid}")
            bounded.print_content(start_row + 3, "Enter hunter name:")
            bounded.print_content(start_row + 4, f"> {self.name_input}_")
            bounded.print_centered(start_row + 6, "Press ENTER when done")
            
        elif self.state == self.STATE_CONFIRM:
            bounded.print_content(start_row + 1, f"UID: {self.uid}")
            bounded.print_content(start_row + 2, f"Name: {self.name_input.strip()}")
            bounded.print_centered(start_row + 4, "Register this hunter? [Y/n]")
            
        elif self.state == self.STATE_ERROR:
            bounded.print_centered(start_row + 1, "ERROR")
            bounded.print_centered(start_row + 3, self.error_msg)
            bounded.print_centered(start_row + 5, "Press any key to continue...")

    def render_footer(self, bounded, app_state):
        """Render footer with controls"""
        bounded.set_title("ADD HUNTER")
        
        if self.state == self.STATE_SCAN:
            bounded.print_content(1, "Waiting for NFC scan...")
            bounded.print_content(2, "[X] Cancel")
        else:
            bounded.print_content(1, "[X] Cancel and return to main screen")


# =============================================================================
# ADMIN SCREEN
# =============================================================================
class AdminScreen(Screen):
    STATE_PASSWORD = "password"
    STATE_MENU = "menu"
    STATE_ADJUST_SCORE = "adjust_score"
    STATE_ADD_ADMIN_SCAN = "add_admin_scan"
    STATE_ADD_ADMIN_NAME = "add_admin_name"
    STATE_ADD_ADMIN_PASSWORD = "add_admin_password"
    STATE_EDIT_HUNTER_SCAN = "edit_hunter_scan"
    STATE_EDIT_HUNTER_MENU = "edit_hunter_menu"
    STATE_EDIT_HUNTER_NAME = "edit_hunter_name"
    STATE_EDIT_WUZU_SCAN = "edit_wuzu_scan"
    STATE_EDIT_WUZU_MENU = "edit_wuzu_menu"
    STATE_EDIT_WUZU_NAME = "edit_wuzu_name"
    STATE_EDIT_WUZU_POINTS = "edit_wuzu_points"
    STATE_EDIT_WUZU_FACT = "edit_wuzu_fact"
    STATE_DELETE_WUZU_CONFIRM = "delete_wuzu_confirm"
    STATE_QUIT_CONFIRM = "quit_confirm"
    STATE_OVERRIDE_SCAN_BADGE = "override_scan_badge"
    STATE_SCAN_OUT = "scan_out"

    def __init__(self, app, admin_uid):
        super().__init__(app)
        self.admin_uid = admin_uid
        self.admin = app.db.get_admin(admin_uid)
        if app.authenticated_admin == admin_uid:
            self.state = self.STATE_MENU
        else:
            self.state = self.STATE_PASSWORD
        self.password_input = ""
        # Edit hunter state
        self.edit_hunter = None
        self.edit_hunter_input = ""
        self.edit_hunter_error = ""
        self.edit_hunter_scan_start = 0
        self.history_events = []
        self.selected_index = 0
        self.scroll_offset = 0
        # Adjust score state
        self.adjust_input = ""
        # Add admin state
        self.new_admin_uid = None
        self.new_admin_name = ""
        self.new_admin_password = ""
        self.add_admin_error = ""
        # Edit wuzu state
        self.edit_wuzu = None
        self.edit_wuzu_input = ""
        self.edit_wuzu_error = ""
        self.edit_wuzu_scan_start = 0
        self.edit_wuzu_events = []
        self.edit_wuzu_selected_index = 0
        self.edit_wuzu_scroll_offset = 0
        # Scan out state
        self.scan_out_found = set()
        self.scan_out_invalid = 0
        self.scan_out_last_time = 0
        # Idle timeout
        self.last_activity = time.time()
        self.admin_timeout = app.config.get('timing', {}).get('admin_timeout', 30)

    def get_panel_sizes(self, available_rows):
        return {
            'main': 11,
            'secondary': available_rows - 11
        }

    def get_active_timeout(self):
        if self.state == self.STATE_PASSWORD:
            return None
        if self.state == self.STATE_EDIT_HUNTER_SCAN:
            timeout = self.app.config.get('timing', {}).get('admin_timeout', 30)
            left = max(0, int(timeout - (time.time() - self.edit_hunter_scan_start)))
            return ("EDIT HUNTER SCAN", left)
        elif self.state == self.STATE_EDIT_WUZU_SCAN:
            timeout = self.app.config.get('timing', {}).get('scan_timeout', 10)
            left = max(0, int(timeout - (time.time() - self.edit_wuzu_scan_start)))
            return ("EDIT WUZU SCAN", left)
        elif self.state == self.STATE_SCAN_OUT:
            timeout = self.app.config.get('timing', {}).get('scan_timeout', 5)
            left = max(0, int(timeout - (time.time() - self.scan_out_last_time)))
            return ("SCAN OUT", left)
        left = max(0, int(self.admin_timeout - (time.time() - self.last_activity)))
        return ("ADMIN SESSION", left)

    def handle(self, key, uid):
        if key or uid:
            self.last_activity = time.time()

        # Check idle timeout
        if self.state != self.STATE_PASSWORD and time.time() - self.last_activity > self.admin_timeout:
            self.app.switch_screen(StartScreen(self.app))
            return

        if key == "r" and self.state not in (
            self.STATE_PASSWORD, self.STATE_ADJUST_SCORE,
            self.STATE_ADD_ADMIN_NAME, self.STATE_ADD_ADMIN_PASSWORD,
            self.STATE_EDIT_HUNTER_NAME, self.STATE_EDIT_WUZU_NAME,
            self.STATE_EDIT_WUZU_POINTS, self.STATE_EDIT_WUZU_FACT,
        ):
            self.app.tui.force_full_redraw()
            return

        if self.state == self.STATE_PASSWORD:
            self._handle_password(key)
        elif self.state == self.STATE_MENU:
            self._handle_menu(key, uid)
        elif self.state == self.STATE_ADJUST_SCORE:
            self._handle_adjust_score(key)
        elif self.state == self.STATE_ADD_ADMIN_SCAN:
            self._handle_add_admin_scan(key, uid)
        elif self.state == self.STATE_ADD_ADMIN_NAME:
            self._handle_add_admin_name(key)
        elif self.state == self.STATE_ADD_ADMIN_PASSWORD:
            self._handle_add_admin_password(key)
        elif self.state == self.STATE_EDIT_HUNTER_SCAN:
            self._handle_edit_hunter_scan(key, uid)
        elif self.state == self.STATE_EDIT_HUNTER_MENU:
            self._handle_edit_hunter_menu(key)
        elif self.state == self.STATE_EDIT_HUNTER_NAME:
            self._handle_edit_hunter_name(key)
        elif self.state == self.STATE_EDIT_WUZU_SCAN:
            self._handle_edit_wuzu_scan(key)
        elif self.state == self.STATE_EDIT_WUZU_MENU:
            self._handle_edit_wuzu_menu(key)
        elif self.state == self.STATE_EDIT_WUZU_NAME:
            self._handle_edit_wuzu_input(key, "name")
        elif self.state == self.STATE_EDIT_WUZU_POINTS:
            self._handle_edit_wuzu_input(key, "points")
        elif self.state == self.STATE_EDIT_WUZU_FACT:
            self._handle_edit_wuzu_input(key, "fact")
        elif self.state == self.STATE_DELETE_WUZU_CONFIRM:
            self._handle_delete_wuzu_confirm(key)
        elif self.state == self.STATE_QUIT_CONFIRM:
            self._handle_quit_confirm(key)
        elif self.state == self.STATE_OVERRIDE_SCAN_BADGE:
            self._handle_override_scan_badge(key, uid)
        elif self.state == self.STATE_SCAN_OUT:
            self._handle_scan_out(key)

    def _handle_password(self, key):
        if key == "x":
            self.app.switch_screen(StartScreen(self.app))
        elif key == "\r":
            if self.app.db.verify_admin_password(self.admin_uid, self.password_input):
                self.password_input = ""
                self.state = self.STATE_MENU
                self.app.authenticated_admin = self.admin_uid
                self.app.tui.force_full_redraw()
            else:
                # Log failed password attempt as private event
                admin_name = self.admin.get('name', self.admin_uid) if self.admin else self.admin_uid
                self.app.db.log_system_event("ADMIN_PASSWORD_FAIL",
                    admin_uid=self.admin_uid,
                    details=f"Failed password attempt for admin '{admin_name}'",
                    private=True)
                self.password_input = ""
                self.app.switch_screen(StartScreen(self.app))
        elif key == "\x7f" or key == "\x08":
            self.password_input = self.password_input[:-1]
            self.app.tui.mark_dirty(PANEL_MAIN)
        elif key and len(key) == 1 and key.isprintable():
            self.password_input += key
            self.app.tui.mark_dirty(PANEL_MAIN)

    def _handle_menu(self, key, uid):
        if key == "w":
            self.app.switch_screen(AddWuzuScreen(self.app,
                on_return=lambda: AdminScreen(self.app, self.admin_uid)))
        elif key == "q":
            self.state = self.STATE_QUIT_CONFIRM
            self.app.tui.force_full_redraw()
        elif key == "e":
            self.edit_wuzu = None
            self.edit_wuzu_input = ""
            self.edit_wuzu_error = ""
            self.edit_wuzu_scan_start = time.time()
            self.state = self.STATE_EDIT_WUZU_SCAN
            self.app.tui.force_full_redraw()
        elif key == "h":
            self.edit_hunter = None
            self.edit_hunter_input = ""
            self.edit_hunter_error = ""
            self.edit_hunter_scan_start = time.time()
            self.state = self.STATE_EDIT_HUNTER_SCAN
            self.app.tui.force_full_redraw()
        elif key == "a":
            self.state = self.STATE_ADD_ADMIN_SCAN
            self.new_admin_uid = None
            self.new_admin_name = ""
            self.app.tui.force_full_redraw()
        elif key == "o":
            self.state = self.STATE_OVERRIDE_SCAN_BADGE
            self.app.tui.force_full_redraw()
        elif key == "s":
            self.scan_out_found = set()
            self.scan_out_invalid = 0
            self.scan_out_last_time = time.time()
            self.state = self.STATE_SCAN_OUT
            self.app.tui.force_full_redraw()
        elif key == "x":
            self.app.switch_screen(StartScreen(self.app))

    def _handle_quit_confirm(self, key):
        if key == "y" or key == "\r":
            self.app.db.log_system_event("SYSTEM_QUIT", admin_uid=self.admin_uid,
                details=f"Quit by admin {self.admin.get('name', self.admin_uid) if self.admin else self.admin_uid}")
            self.app.terminal.clear()
            self.app.db.close()
            sys.exit()
        elif key and key != "y":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()

    def _handle_override_scan_badge(self, key, uid):
        if key == "x":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
        elif uid:
            if self.app.db.hunter_exists(uid):
                hunter = self.app.db.get_hunter(uid)
                admin_name = self.admin.get('name', self.admin_uid) if self.admin else self.admin_uid
                self.app.log_event("ADMIN_OVERRIDE", hunter_uid=uid,
                    details=f"Admin {admin_name} started override scan for {hunter['name']}")
                self.app.switch_screen(ScanWuzuScreen(self.app, uid, override=True))

    def _handle_scan_out(self, key):
        if key == "x":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
            return

        timeout = self.app.config.get('timing', {}).get('scan_timeout', 5)
        if time.time() - self.scan_out_last_time > timeout:
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
            return

        tags = self.app.uhf.inventory()
        for tag in tags:
            epc = tag["epc"]
            if epc in self.scan_out_found:
                continue
            wuzu = self.app.db.get_wuzu(epc)
            if wuzu and not wuzu.get('deleted'):
                self.scan_out_found.add(epc)
                self.scan_out_last_time = time.time()
                wuzu_name = wuzu.get('name') or epc
                admin_name = self.admin.get('name', self.admin_uid) if self.admin else self.admin_uid
                self.app.log_event("SCAN_OUT", wuzu_epc=epc,
                    details=f"Admin {admin_name} scanned out {wuzu_name}",
                    private=True)
                self.app.beep("new_wuzu")
                self.app.tui.mark_dirty(PANEL_MAIN)
            else:
                self.scan_out_invalid += 1
                self.scan_out_last_time = time.time()
                self.app.tui.mark_dirty(PANEL_MAIN)

        self.app.tui.mark_dirty(PANEL_FOOTER)

    def _handle_edit_hunter_scan(self, key, uid):
        if key == "x":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
            return

        timeout = self.app.config.get('timing', {}).get('admin_timeout', 30)
        if time.time() - self.edit_hunter_scan_start > timeout:
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
            return

        if uid:
            if self.app.db.hunter_exists(uid):
                self.edit_hunter = self.app.db.get_hunter(uid)
                self.edit_hunter_error = ""
                self.history_events = self.app.db.get_hunter_scan_history(uid)
                self.selected_index = 0
                self.scroll_offset = 0
                self.state = self.STATE_EDIT_HUNTER_MENU
                self.app.tui.force_full_redraw()
            else:
                self.edit_hunter_error = f"Hunter {uid} not found in database!"
                self.app.tui.mark_dirty(PANEL_MAIN)

    def _handle_edit_hunter_menu(self, key):
        if key == "x":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
        elif key == "n":
            self.edit_hunter_input = self.edit_hunter.get('name') or ""
            self.state = self.STATE_EDIT_HUNTER_NAME
            self.app.tui.force_full_redraw()
        elif key == "m":
            self.adjust_input = ""
            self.state = self.STATE_ADJUST_SCORE
            self.app.tui.force_full_redraw()
        elif key in ("j", "2"):
            if self.selected_index < len(self.history_events) - 1:
                self.selected_index += 1
                self.app.tui.mark_dirty(PANEL_SECONDARY)
        elif key in ("k", "8"):
            if self.selected_index > 0:
                self.selected_index -= 1
                self.app.tui.mark_dirty(PANEL_SECONDARY)

    def _handle_edit_hunter_name(self, key):
        if key == "x":
            self.state = self.STATE_EDIT_HUNTER_MENU
            self.app.tui.force_full_redraw()
        elif key == "\r":
            name = self.edit_hunter_input.strip()
            if name and not self.app.db.hunter_name_exists(name):
                uid = self.edit_hunter['uid']
                self.app.db.update_hunter_name(uid, name)
                self.edit_hunter = self.app.db.get_hunter(uid)
            self.state = self.STATE_EDIT_HUNTER_MENU
            self.app.tui.force_full_redraw()
        elif key == "\x7f" or key == "\x08":
            self.edit_hunter_input = self.edit_hunter_input[:-1]
            self.app.tui.mark_dirty(PANEL_MAIN)
        elif key and (key.isalnum() or key in " -"):
            if len(self.edit_hunter_input) < 100:
                self.edit_hunter_input += key
                self.app.tui.mark_dirty(PANEL_MAIN)

    def _handle_adjust_score(self, key):
        if key == "x":
            self.state = self.STATE_EDIT_HUNTER_MENU
            self.app.tui.force_full_redraw()
        elif key == "\r":
            # Enter — apply adjustment
            try:
                points = int(self.adjust_input)
                if points != 0:
                    uid = self.edit_hunter['uid']
                    self.app.db.admin_adjust_score(uid, points, self.admin_uid)
                    # Refresh history and hunter data
                    self.history_events = self.app.db.get_hunter_scan_history(uid)
                    self.edit_hunter = self.app.db.get_hunter(uid)
            except ValueError:
                pass
            self.state = self.STATE_EDIT_HUNTER_MENU
            self.app.tui.force_full_redraw()
        elif key == "\x7f" or key == "\x08":
            # Backspace
            self.adjust_input = self.adjust_input[:-1]
            self.app.tui.mark_dirty(PANEL_MAIN)
        elif key and (key.isdigit() or (key == "-" and len(self.adjust_input) == 0)):
            self.adjust_input += key
            self.app.tui.mark_dirty(PANEL_MAIN)

    def _handle_add_admin_scan(self, key, uid):
        if key == "x":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
        elif uid:
            if self.app.db.admin_exists(uid):
                self.add_admin_error = "UID is already registered as an admin!"
                self.app.tui.mark_dirty(PANEL_MAIN)
                return
            if self.app.db.hunter_exists(uid):
                self.add_admin_error = "UID is registered as a hunter!"
                self.app.tui.mark_dirty(PANEL_MAIN)
                return
            self.add_admin_error = ""
            self.new_admin_uid = uid
            self.new_admin_name = ""
            self.state = self.STATE_ADD_ADMIN_NAME
            self.app.tui.force_full_redraw()

    def _handle_add_admin_name(self, key):
        if key == "x":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
        elif key == "\r":
            # Enter — confirm name, move to password creation
            name = self.new_admin_name.strip()
            if len(name) >= 2 and not self.app.db.admin_name_exists(name):
                self.new_admin_password = ""
                self.state = self.STATE_ADD_ADMIN_PASSWORD
                self.app.tui.force_full_redraw()
            else:
                self.app.tui.mark_dirty(PANEL_MAIN)
        elif key == "\x7f" or key == "\x08":
            # Backspace
            self.new_admin_name = self.new_admin_name[:-1]
            self.app.tui.mark_dirty(PANEL_MAIN)
        elif key and (key.isalnum() or key in " -"):
            if len(self.new_admin_name) < 20:
                self.new_admin_name += key
                self.app.tui.mark_dirty(PANEL_MAIN)

    def _handle_add_admin_password(self, key):
        if key == "x":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
        elif key == "\r":
            # Enter — password can't be blank
            if self.new_admin_password:
                name = self.new_admin_name.strip()
                self.app.db.add_admin(self.new_admin_uid, name,
                    self.new_admin_password, self.admin_uid)
                self.app.db.log_system_event("ADMIN_ADD", admin_uid=self.admin_uid,
                    details=f"Added admin '{name}' UID {self.new_admin_uid}")
                self.new_admin_password = ""
                self.state = self.STATE_MENU
                self.app.tui.force_full_redraw()
            else:
                self.app.tui.mark_dirty(PANEL_MAIN)
        elif key == "\x7f" or key == "\x08":
            self.new_admin_password = self.new_admin_password[:-1]
            self.app.tui.mark_dirty(PANEL_MAIN)
        elif key and len(key) == 1 and key.isprintable():
            self.new_admin_password += key
            self.app.tui.mark_dirty(PANEL_MAIN)

    def _handle_edit_wuzu_scan(self, key):
        if key == "x":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
            return

        timeout = self.app.config.get('timing', {}).get('scan_timeout', 10)
        if time.time() - self.edit_wuzu_scan_start > timeout:
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
            return

        tags = self.app.uhf.inventory()
        if tags:
            epc = tags[0]["epc"]
            self.app.beep("new_wuzu")
            wuzu = self.app.db.get_wuzu(epc)
            if wuzu and not wuzu.get('deleted'):
                self.edit_wuzu = wuzu
                self.edit_wuzu_error = ""
                self.edit_wuzu_events = self.app.db.get_wuzu_scan_history(epc)
                self.edit_wuzu_selected_index = 0
                self.edit_wuzu_scroll_offset = 0
                self.state = self.STATE_EDIT_WUZU_MENU
                self.app.tui.force_full_redraw()
            elif wuzu and wuzu.get('deleted'):
                wuzu_name = wuzu.get('name') or epc
                self.edit_wuzu_error = f"Deleted wuzu '{wuzu_name}' — re-add it first!"
                self.app.tui.mark_dirty(PANEL_MAIN)
            else:
                self.edit_wuzu_error = f"Wuzu {epc} not found in database!"
                self.app.tui.mark_dirty(PANEL_MAIN)
        else:
            self.app.tui.mark_dirty(PANEL_FOOTER)

    def _handle_edit_wuzu_menu(self, key):
        if key == "x":
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
        elif key == "n":
            self.edit_wuzu_input = self.edit_wuzu.get('name') or ""
            self.state = self.STATE_EDIT_WUZU_NAME
            self.app.tui.force_full_redraw()
        elif key == "p":
            default_points = self.app.config.get('scoring', {}).get('default_points', 10)
            self.edit_wuzu_input = str(self.edit_wuzu.get('points_value', default_points))
            self.state = self.STATE_EDIT_WUZU_POINTS
            self.app.tui.force_full_redraw()
        elif key == "f":
            self.edit_wuzu_input = self.edit_wuzu.get('fact') or ""
            self.state = self.STATE_EDIT_WUZU_FACT
            self.app.tui.force_full_redraw()
        elif key == "d":
            self.state = self.STATE_DELETE_WUZU_CONFIRM
            self.app.tui.force_full_redraw()
        elif key in ("j", "2"):
            if self.edit_wuzu_selected_index < len(self.edit_wuzu_events) - 1:
                self.edit_wuzu_selected_index += 1
                self.app.tui.mark_dirty(PANEL_SECONDARY)
        elif key in ("k", "8"):
            if self.edit_wuzu_selected_index > 0:
                self.edit_wuzu_selected_index -= 1
                self.app.tui.mark_dirty(PANEL_SECONDARY)

    def _handle_delete_wuzu_confirm(self, key):
        if key == "y":
            epc = self.edit_wuzu['epc']
            wuzu_name = self.edit_wuzu.get('name') or epc
            self.app.db.soft_delete_wuzu(epc)
            self.app.db.log_system_event("ADMIN_DELETE",
                admin_uid=self.admin_uid,
                details=f"Deleted wuzu '{wuzu_name}' ({epc})",
                private=True)
            self.state = self.STATE_MENU
            self.app.tui.force_full_redraw()
        elif key in ["n", "x"]:
            self.state = self.STATE_EDIT_WUZU_MENU
            self.app.tui.force_full_redraw()

    def _handle_edit_wuzu_input(self, key, field):
        if key == "x":
            self.state = self.STATE_EDIT_WUZU_MENU
            self.app.tui.force_full_redraw()
        elif key == "\r":
            epc = self.edit_wuzu['epc']
            value = self.edit_wuzu_input.strip()
            if field == "name":
                self.app.db.update_wuzu(epc, name=value if value else None)
            elif field == "points":
                try:
                    pts = int(value)
                    if pts > 0:
                        self.app.db.update_wuzu(epc, points_value=pts)
                except ValueError:
                    pass
            elif field == "fact":
                self.app.db.update_wuzu(epc, fact=value if value else None)
            # Refresh wuzu data
            self.edit_wuzu = self.app.db.get_wuzu(epc)
            self.state = self.STATE_EDIT_WUZU_MENU
            self.app.tui.force_full_redraw()
        elif key == "\x7f" or key == "\x08":
            self.edit_wuzu_input = self.edit_wuzu_input[:-1]
            self.app.tui.mark_dirty(PANEL_MAIN)
        elif key and len(key) == 1 and key.isprintable():
            max_len = 200 if field == "fact" else 100 if field == "name" else 10
            if len(self.edit_wuzu_input) < max_len:
                if field == "points":
                    if key.isdigit():
                        self.edit_wuzu_input += key
                        self.app.tui.mark_dirty(PANEL_MAIN)
                else:
                    self.edit_wuzu_input += key
                    self.app.tui.mark_dirty(PANEL_MAIN)

    # === RENDERING ===
    def render_main(self, bounded, app_state):
        if self.state == self.STATE_PASSWORD:
            self._render_password(bounded)
        elif self.state == self.STATE_MENU:
            self._render_menu(bounded)
        elif self.state == self.STATE_ADJUST_SCORE:
            self._render_adjust_score(bounded)
        elif self.state == self.STATE_ADD_ADMIN_SCAN:
            self._render_add_admin_scan(bounded)
        elif self.state == self.STATE_ADD_ADMIN_NAME:
            self._render_add_admin_name(bounded)
        elif self.state == self.STATE_ADD_ADMIN_PASSWORD:
            self._render_add_admin_password(bounded)
        elif self.state == self.STATE_EDIT_HUNTER_SCAN:
            self._render_edit_hunter_scan(bounded)
        elif self.state == self.STATE_EDIT_HUNTER_MENU:
            self._render_edit_hunter_menu(bounded)
        elif self.state == self.STATE_EDIT_HUNTER_NAME:
            self._render_edit_hunter_name(bounded)
        elif self.state == self.STATE_EDIT_WUZU_SCAN:
            self._render_edit_wuzu_scan(bounded)
        elif self.state == self.STATE_EDIT_WUZU_MENU:
            self._render_edit_wuzu_menu(bounded)
        elif self.state in (self.STATE_EDIT_WUZU_NAME, self.STATE_EDIT_WUZU_POINTS, self.STATE_EDIT_WUZU_FACT):
            self._render_edit_wuzu_input(bounded)
        elif self.state == self.STATE_DELETE_WUZU_CONFIRM:
            self._render_delete_wuzu_confirm(bounded)
        elif self.state == self.STATE_QUIT_CONFIRM:
            self._render_quit_confirm(bounded)
        elif self.state == self.STATE_OVERRIDE_SCAN_BADGE:
            self._render_override_scan_badge(bounded)
        elif self.state == self.STATE_SCAN_OUT:
            self._render_scan_out(bounded)

    def _render_password(self, bounded):
        admin_name = self.admin.get('name', self.admin_uid) if self.admin else self.admin_uid
        bounded.set_title("ADMIN LOGIN")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        bounded.print_centered(start_row, f"Admin: {admin_name}")
        bounded.print_centered(start_row + 2, "Enter password:")
        masked = "*" * len(self.password_input)
        bounded.print_centered(start_row + 3, f"> {masked}_")
        bounded.print_centered(start_row + 5, "[Enter] Submit    [X] Cancel")

    def _render_menu(self, bounded):
        admin_name = self.admin.get('name', self.admin_uid) if self.admin else self.admin_uid
        bounded.set_title(f"ADMIN PANEL - {admin_name}")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 10) // 2 + 1

        bounded.print_centered(start_row, "ADMIN FUNCTIONS")
        bounded.print_centered(start_row + 2, "[W] Add Wuzu Tag       [E] Edit Wuzu")
        bounded.print_centered(start_row + 3, "[H] Edit Hunter        [A] Add New Admin")
        bounded.print_centered(start_row + 4, "[O] Override Scan      [S] Scan Out Wuzus")
        bounded.print_centered(start_row + 5, "[Q] Quit Application   [X] Exit Admin Mode")

    def _render_quit_confirm(self, bounded):
        bounded.set_title("QUIT APPLICATION")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 4) // 2 + 1
        bounded.print_centered(start_row, "Quit application, Are you sure?")
        bounded.print_centered(start_row + 2, "[Y/n]")

    def _render_override_scan_badge(self, bounded):
        bounded.set_title("OVERRIDE SCAN")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1
        bounded.print_centered(start_row, "ADMIN OVERRIDE SCAN")
        bounded.print_centered(start_row + 2, "Scan hunter badge to begin...")
        bounded.print_centered(start_row + 4, "All validation will be skipped!")
        bounded.print_centered(start_row + 5, "[X] Cancel")

    def _render_scan_out(self, bounded):
        bounded.set_title("SCAN OUT WUZUS")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1
        bounded.print_centered(start_row, "SCANNING OUT WUZUS")
        bounded.print_centered(start_row + 2, "Scan wuzu tags to release them...")
        wuzu_label = "Wuzu" if len(self.scan_out_found) == 1 else "Wuzus"
        bounded.print_centered(start_row + 4, f"Scanned Out: {len(self.scan_out_found)} {wuzu_label}")
        if self.scan_out_invalid > 0:
            bounded.print_centered(start_row + 5, f"Invalid: {self.scan_out_invalid}")

    def _render_edit_hunter_scan(self, bounded):
        bounded.set_title("EDIT HUNTER")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        bounded.print_centered(start_row, "Scan hunter badge with NFC reader...")
        if self.edit_hunter_error:
            bounded.print_centered(start_row + 4, f"ERROR: {self.edit_hunter_error}")

    def _render_edit_hunter_menu(self, bounded):
        bounded.set_title("EDIT HUNTER")

        hunter = self.edit_hunter
        hunter_name = hunter.get('name', '?') if hunter else '?'
        hunter_pts = hunter.get('points', 0) if hunter else 0
        hunter_uid = hunter.get('uid', '?') if hunter else '?'
        last_seen = hunter.get('last_seen')
        last_seen_str = last_seen.strftime("%Y-%m-%d %H:%M:%S") if last_seen else "(never)"

        bounded.print_content(1, f"UID:       {hunter_uid}")
        bounded.print_content(2, f"Name:      {hunter_name}")
        bounded.print_content(3, f"Points:    {hunter_pts}")
        bounded.print_content(4, f"Last Seen: {last_seen_str}")
        bounded.print_content(6, "[N] Edit Name   [M] Manual Adjust")
        bounded.print_content(7, "[X] Back to Admin Menu")

    def _render_edit_hunter_name(self, bounded):
        bounded.set_title("EDIT HUNTER - NAME")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        hunter_name = self.edit_hunter.get('name', '?') if self.edit_hunter else '?'
        bounded.print_centered(start_row, f"Hunter: {hunter_name}")
        bounded.print_centered(start_row + 2, "Enter new name:")
        bounded.print_centered(start_row + 3, f"> {self.edit_hunter_input}_")
        bounded.print_centered(start_row + 5, "[Enter] Save    [X] Cancel")

    def _render_adjust_score(self, bounded):
        bounded.set_title("MANUAL SCORE ADJUSTMENT")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        hunter_name = self.edit_hunter.get('name', '?') if self.edit_hunter else '?'
        bounded.print_centered(start_row, f"Hunter: {hunter_name}")
        bounded.print_centered(start_row + 2, "Enter point adjustment (e.g. 10 or -5):")
        bounded.print_centered(start_row + 3, f"> {self.adjust_input}_")
        bounded.print_centered(start_row + 5, "[Enter] Apply    [X] Cancel")

    def _render_add_admin_scan(self, bounded):
        bounded.set_title("ADD NEW ADMIN")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        bounded.print_centered(start_row, "Scan NFC badge of new admin...")
        if self.add_admin_error:
            bounded.print_centered(start_row + 2, f"ERROR: {self.add_admin_error}")
        bounded.print_centered(start_row + 4, "[X] Cancel")

    def _render_add_admin_name(self, bounded):
        bounded.set_title("ADD NEW ADMIN")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        bounded.print_centered(start_row, f"Badge UID: {self.new_admin_uid}")
        bounded.print_centered(start_row + 2, "Enter admin name:")
        bounded.print_centered(start_row + 3, f"> {self.new_admin_name}_")
        bounded.print_centered(start_row + 5, "[Enter] Confirm    [X] Cancel")

    def _render_add_admin_password(self, bounded):
        bounded.set_title("ADD NEW ADMIN - SET PASSWORD")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        bounded.print_centered(start_row, f"Admin: {self.new_admin_name.strip()}")
        bounded.print_centered(start_row + 2, "Create a password (cannot be blank):")
        masked = "*" * len(self.new_admin_password) if hasattr(self, 'new_admin_password') else ""
        bounded.print_centered(start_row + 3, f"> {masked}_")
        bounded.print_centered(start_row + 5, "[Enter] Confirm    [X] Cancel")

    def _render_edit_wuzu_scan(self, bounded):
        bounded.set_title("EDIT WUZU")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        bounded.print_centered(start_row, "Scan Wuzu tag with UHF reader...")
        if self.edit_wuzu_error:
            bounded.print_centered(start_row + 4, f"ERROR: {self.edit_wuzu_error}")

    def _render_edit_wuzu_menu(self, bounded):
        bounded.set_title("EDIT WUZU")

        wuzu = self.edit_wuzu
        status = " [DELETED]" if wuzu.get('deleted') else ""
        bounded.print_content(1, f"EPC:    {wuzu['epc']}{status}")
        bounded.print_content(2, f"Name:   {wuzu.get('name') or '(none)'}")
        default_points = self.app.config.get('scoring', {}).get('default_points', 10)
        bounded.print_content(3, f"Points: {wuzu.get('points_value', default_points)}")
        bounded.print_content(4, f"Fact:   {wuzu.get('fact') or '(none)'}")
        bounded.print_content(5, f"Found:  {wuzu.get('times_found', 0)} times")
        bounded.print_content(7, "[N] Edit Name   [P] Edit Points   [F] Edit Fact   [D] Delete")
        bounded.print_content(8, "[X] Back to Admin Menu")

    def _render_delete_wuzu_confirm(self, bounded):
        bounded.set_title("CONFIRM DELETE WUZU")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        wuzu_name = self.edit_wuzu.get('name') or self.edit_wuzu['epc']
        bounded.print_centered(start_row, f"Wuzu: {wuzu_name}")
        bounded.print_centered(start_row + 1, f"EPC: {self.edit_wuzu['epc']}")
        bounded.print_centered(start_row + 3, "Delete this wuzu? It will no longer award points.")
        bounded.print_centered(start_row + 5, "[Y] Yes    [N] No")

    def _render_edit_wuzu_input(self, bounded):
        if self.state == self.STATE_EDIT_WUZU_NAME:
            field_label = "Name"
        elif self.state == self.STATE_EDIT_WUZU_POINTS:
            field_label = "Points"
        else:
            field_label = "Fact"

        bounded.set_title(f"EDIT WUZU - {field_label.upper()}")
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1

        wuzu_name = self.edit_wuzu.get('name') or self.edit_wuzu['epc']
        bounded.print_centered(start_row, f"Wuzu: {wuzu_name}")
        bounded.print_centered(start_row + 2, f"Enter new {field_label.lower()}:")
        bounded.print_centered(start_row + 3, f"> {self.edit_wuzu_input}_")
        bounded.print_centered(start_row + 5, "[Enter] Save    [X] Cancel")

    def render_secondary(self, bounded, app_state):
        if self.state in (self.STATE_EDIT_HUNTER_MENU, self.STATE_EDIT_HUNTER_NAME,
                          self.STATE_ADJUST_SCORE):
            self._render_hunter_history_panel(bounded)
        elif self.state in (self.STATE_EDIT_WUZU_MENU, self.STATE_EDIT_WUZU_NAME,
                            self.STATE_EDIT_WUZU_POINTS, self.STATE_EDIT_WUZU_FACT,
                            self.STATE_DELETE_WUZU_CONFIRM):
            self._render_wuzu_history_panel(bounded)
        else:
            self._render_all_events(bounded)

    def _render_all_events(self, bounded):
        bounded.set_title("ALL EVENTS")
        content_cols, content_rows = bounded.content_size()
        events = self.app.db.get_all_recent_events(content_rows - 1)

        for i, evt in enumerate(events, start=1):
            ts = evt['timestamp'].strftime("%H:%M:%S")
            prefix = "[DEL] " if evt.get('deleted') else ""
            line = f"{ts} {evt['event_type']:<20} {prefix}{evt.get('details', '')}"
            bounded.print_content(i, line[:content_cols])

    def _render_hunter_history_panel(self, bounded):
        hunter_name = self.edit_hunter.get('name', '?') if self.edit_hunter else '?'
        bounded.set_title(f"SCAN HISTORY - {hunter_name}")
        content_cols, content_rows = bounded.content_size()

        # Header
        detail_width = max(content_cols - 34, 10)
        header = f"{'#':<4} {'TIME':<10} {'TYPE':<12} {'PTS':<6} {'DETAILS'}"
        bounded.print_content(1, header[:content_cols])
        bounded.print_content(2, "-" * content_cols)

        # Visible rows
        visible_rows = content_rows - 2
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + visible_rows:
            self.scroll_offset = self.selected_index - visible_rows + 1

        for i, evt in enumerate(self.history_events[self.scroll_offset:self.scroll_offset + visible_rows]):
            actual_idx = self.scroll_offset + i
            ts = evt['timestamp'].strftime("%H:%M:%S")
            pts = evt.get('points_awarded', 0)
            details = (evt.get('details', '') or '')[:detail_width]
            marker = "> " if actual_idx == self.selected_index else "  "
            row = f"{marker}{actual_idx + 1:<2} {ts:<10} {evt['event_type']:<12} {pts:<6} {details}"
            bounded.print_content(3 + i, row[:content_cols])

    def _render_wuzu_history_panel(self, bounded):
        wuzu_name = self.edit_wuzu.get('name') or self.edit_wuzu.get('epc', '?') if self.edit_wuzu else '?'
        bounded.set_title(f"SCAN HISTORY - {wuzu_name}")
        content_cols, content_rows = bounded.content_size()

        # Header
        detail_width = max(content_cols - 34, 10)
        header = f"{'#':<4} {'TIME':<10} {'TYPE':<12} {'PTS':<6} {'DETAILS'}"
        bounded.print_content(1, header[:content_cols])
        bounded.print_content(2, "-" * content_cols)

        # Visible rows
        visible_rows = content_rows - 2
        if self.edit_wuzu_selected_index < self.edit_wuzu_scroll_offset:
            self.edit_wuzu_scroll_offset = self.edit_wuzu_selected_index
        elif self.edit_wuzu_selected_index >= self.edit_wuzu_scroll_offset + visible_rows:
            self.edit_wuzu_scroll_offset = self.edit_wuzu_selected_index - visible_rows + 1

        for i, evt in enumerate(self.edit_wuzu_events[self.edit_wuzu_scroll_offset:self.edit_wuzu_scroll_offset + visible_rows]):
            actual_idx = self.edit_wuzu_scroll_offset + i
            ts = evt['timestamp'].strftime("%H:%M:%S")
            pts = evt.get('points_awarded', 0)
            details = (evt.get('details', '') or '')[:detail_width]
            marker = "> " if actual_idx == self.edit_wuzu_selected_index else "  "
            row = f"{marker}{actual_idx + 1:<2} {ts:<10} {evt['event_type']:<12} {pts:<6} {details}"
            bounded.print_content(3 + i, row[:content_cols])

    def render_footer(self, bounded, app_state):
        bounded.set_title("ADMIN CONTROLS")
        if self.state == self.STATE_PASSWORD:
            bounded.print_content(1, "[Enter] Submit  [X] Cancel")
        elif self.state == self.STATE_MENU:
            bounded.print_content(1, "[W] Wuzu [E] Edit [H] Hunter [A] Admin [O] Override [S] Scan Out [Q] Quit [X] Exit")
        elif self.state == self.STATE_EDIT_HUNTER_SCAN:
            bounded.print_content(1, "[X] Cancel")
        elif self.state == self.STATE_EDIT_HUNTER_MENU:
            bounded.print_content(1, "[N] Edit Name  [M] Manual Adjust  [J/K] Navigate History  [X] Back")
        elif self.state == self.STATE_EDIT_HUNTER_NAME:
            bounded.print_content(1, "[Enter] Save  [X] Cancel")
        elif self.state == self.STATE_ADJUST_SCORE:
            bounded.print_content(1, "[Enter] Apply  [X] Cancel")
        elif self.state in (self.STATE_ADD_ADMIN_SCAN, self.STATE_ADD_ADMIN_NAME,
                            self.STATE_ADD_ADMIN_PASSWORD):
            bounded.print_content(1, "[X] Cancel")
        elif self.state == self.STATE_EDIT_WUZU_SCAN:
            bounded.print_content(1, "[X] Cancel")
        elif self.state == self.STATE_EDIT_WUZU_MENU:
            bounded.print_content(1, "[N] Name  [P] Points  [F] Fact  [D] Delete  [J/K] Navigate History  [X] Back")
        elif self.state in (self.STATE_EDIT_WUZU_NAME, self.STATE_EDIT_WUZU_POINTS,
                            self.STATE_EDIT_WUZU_FACT):
            bounded.print_content(1, "[Enter] Save  [X] Cancel")
        elif self.state == self.STATE_DELETE_WUZU_CONFIRM:
            bounded.print_content(1, "[Y] Confirm Delete  [N] Cancel")
        elif self.state == self.STATE_OVERRIDE_SCAN_BADGE:
            bounded.print_content(1, "Scan hunter badge...  [X] Cancel")
        elif self.state == self.STATE_SCAN_OUT:
            bounded.print_content(1, "Scanning out wuzus...  [X] Exit")


# =============================================================================
# ADD WUZU SCREEN
# =============================================================================
class AddWuzuScreen(Screen):
    STATE_SCAN = "scan"
    STATE_ERROR = "error"
    STATE_READD_CONFIRM = "readd_confirm"

    def __init__(self, app, on_return=None):
        super().__init__(app)
        self.state = self.STATE_SCAN
        self.timeout = app.config.get('timing', {}).get('scan_timeout', 10)
        self.start_time = time.time()
        self.error_msg = ""
        self.readd_epc = None
        self.on_return = on_return or (lambda: StartScreen(app))

    def get_panel_sizes(self, available_rows):
        """This screen wants all space for scanning status"""
        return {
            'main': available_rows,
            'secondary': None
        }

    def get_active_timeout(self):
        if self.state == self.STATE_SCAN:
            left = max(0, int(self.timeout - (time.time() - self.start_time)))
            return ("ADD WUZU SCAN", left)
        return None

    def handle(self, key, uid):
        if key == "r" and self.state in (self.STATE_SCAN, self.STATE_READD_CONFIRM):
            self.app.tui.force_full_redraw()
            return

        if self.state == self.STATE_SCAN:
            if time.time() - self.start_time > self.timeout:
                self.app.log_event("TIMEOUT", details="Add-Wuzu: no scan", private=True)
                self.app.switch_screen(self.on_return())
                return

            if key == "x":
                self.app.log_event("CANCEL", details="Add-Wuzu cancelled")
                self.app.switch_screen(self.on_return())
                return

            tags = self.app.uhf.inventory()
            if tags:
                for t in tags:
                    epc = t["epc"]
                    self.app.beep("new_wuzu")
                    if not self.app.db.wuzu_exists(epc):
                        self.app.register_wuzu(epc)
                        self.app.switch_screen(self.on_return())
                        return
                    elif self.app.db.wuzu_is_deleted(epc):
                        self.readd_epc = epc
                        self.state = self.STATE_READD_CONFIRM
                        self.app.tui.force_full_redraw()
                        return
                    else:
                        self.app.log_event("DUPLICATE", details="Wuzu already registered")
                        self.error_msg = f"Wuzu {epc} already registered!"
                        self.state = self.STATE_ERROR
                        self.app.tui.force_full_redraw()
                        return

            self.app.tui.mark_dirty(PANEL_FOOTER)

        elif self.state == self.STATE_READD_CONFIRM:
            if key in ["y", "\r"]:
                self.app.db.restore_wuzu(self.readd_epc)
                wuzu = self.app.db.get_wuzu(self.readd_epc)
                wuzu_name = wuzu['name'] if wuzu and wuzu.get('name') else self.readd_epc
                self.app.log_event("NEW", details=f"Wuzu '{wuzu_name}' re-added", private=True)
                self.app.switch_screen(self.on_return())
            elif key in ["n", "x"]:
                self.state = self.STATE_SCAN
                self.start_time = time.time()  # Reset timeout
                self.app.tui.force_full_redraw()

        elif self.state == self.STATE_ERROR:
            # Any key returns
            if key:
                self.app.switch_screen(self.on_return())

    def render_main(self, bounded, app_state):
        """Show scanning status or error"""
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 8) // 2 + 1
        
        if self.state == self.STATE_SCAN:
            bounded.set_title("ADD NEW WUZU")
            bounded.print_centered(start_row + 1, "Scanning for UHF tags...")
        
        elif self.state == self.STATE_READD_CONFIRM:
            bounded.set_title("ADD NEW WUZU")
            wuzu = self.app.db.get_wuzu(self.readd_epc)
            wuzu_name = wuzu['name'] if wuzu and wuzu.get('name') else self.readd_epc
            bounded.print_centered(start_row + 1, f"Deleted wuzu detected: {wuzu_name}")
            bounded.print_centered(start_row + 2, f"EPC: {self.readd_epc}")
            bounded.print_centered(start_row + 4, "Re-add this wuzu? [Y/n]")

        elif self.state == self.STATE_ERROR:
            bounded.set_title("ADD NEW WUZU")
            bounded.print_centered(start_row + 1, "ERROR")
            bounded.print_centered(start_row + 3, self.error_msg)
            bounded.print_centered(start_row + 5, "Press any key to continue...")

    def render_footer(self, bounded, app_state):
        bounded.set_title("ADD WUZU")

        if self.state == self.STATE_SCAN:
            bounded.print_content(1, "Scan new Wuzu tag with UHF reader...")
            bounded.print_content(2, "[X] Cancel")
        elif self.state == self.STATE_READD_CONFIRM:
            bounded.print_content(1, "[Y] Re-add  [N] Cancel")
        else:
            bounded.print_content(1, "[X] Return to main screen")


# =============================================================================
# SCAN WUZU SCREEN
# =============================================================================
class ScanWuzuScreen(Screen):
    def __init__(self, app, hunter_uid, override=False):
        super().__init__(app)
        self.hunter_uid = hunter_uid
        self.override = override
        self.found = set()
        self.unknown = set()
        self.rejected = {}  # {epc: reason_string}
        self.session_points = 0
        self.rank_before = app.db.get_hunter_rank(hunter_uid)
        self.last_time = time.time()
        self.timeout = app.config.get('timing', {}).get('scan_timeout', 5)

    def get_panel_sizes(self, available_rows):
        """This screen wants all space for scanning display"""
        return {
            'main': available_rows,
            'secondary': None
        }

    def get_active_timeout(self):
        left = max(0, int(self.timeout - (time.time() - self.last_time)))
        return ("SCORING", left)

    def handle(self, key, uid):
        if key == "r":
            self.app.tui.force_full_redraw()
            return

        if key == "x":
            hunter = self.app.db.get_hunter(self.hunter_uid)
            name = hunter['name'] if hunter else "Unknown"
            self.app.log_event("EXIT", hunter_uid=self.hunter_uid, 
                            details=f"Score mode exited for {name}")
            self.app.switch_screen(StartScreen(self.app))
            return

        tags = self.app.uhf.inventory()
        for tag in tags:
            epc = tag["epc"]
            if epc in self.found or epc in self.unknown or epc in self.rejected:
                continue

            self.last_time = time.time()

            hunter = self.app.db.get_hunter(self.hunter_uid)
            if not hunter:
                continue

            if self.override:
                # Override mode: skip all validation, score everything
                points = self.app.db.get_wuzu_points(epc)
                if points == 0:
                    # Unregistered wuzu: use default points, do NOT register
                    points = self.app.config.get('scoring', {}).get('default_points', 10)
                self.found.add(epc)
                self.session_points += points
                self.app.record_wuzu_scan(self.hunter_uid, epc, points, override=True)
            else:
                points = self.app.db.get_wuzu_points(epc)
                if points > 0:
                    # Validate scan against cooldown/scan-out rules
                    scoring_config = self.app.config.get('scoring', {})
                    valid, reason = self.app.db.check_wuzu_scan_validity(epc, scoring_config)
                    if valid:
                        self.found.add(epc)
                        self.session_points += points
                        self.app.record_wuzu_scan(self.hunter_uid, epc, points)
                    else:
                        self.rejected[epc] = reason
                        wuzu = self.app.db.get_wuzu(epc)
                        wuzu_name = wuzu.get('name') or epc if wuzu else epc
                        self.app.log_event("REJECTED", hunter_uid=self.hunter_uid,
                            wuzu_epc=epc,
                            details=f"{hunter['name']} rejected {wuzu_name}: {reason}",
                            private=True)
                else:
                    self.unknown.add(epc)
                    if self.app.db.wuzu_exists(epc):
                        self.app.log_event("REJECTED", hunter_uid=self.hunter_uid,
                            wuzu_epc=epc,
                            details=f"{hunter['name']} scanned deleted wuzu {epc}",
                            private=True)
                    else:
                        self.app.log_event("REJECTED", hunter_uid=self.hunter_uid,
                            details=f"{hunter['name']} scanned unregistered tag {epc}",
                            private=True)

            self.app.beep("new_wuzu")
            self.app.tui.mark_dirty(PANEL_MAIN)
            self.app.tui.mark_dirty(PANEL_FOOTER)

        # Mark footer dirty every loop to update countdown timer
        self.app.tui.mark_dirty(PANEL_FOOTER)

        if time.time() - self.last_time > self.timeout:
            self.app.beep("complete")
            self.app.switch_screen(ResultsScreen(self.app, self.hunter_uid, self.found,
                self.session_points, self.rank_before, len(self.unknown),
                self.rejected, self.override))

    def render_main(self, bounded, app_state):
        """Show scanning progress"""
        bounded.set_title("SCANNING WUZUS")

        hunter = self.app.db.get_hunter(self.hunter_uid)
        name = hunter['name'] if hunter else "Unknown"

        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 8) // 2 + 1

        if self.override:
            bounded.print_centered(start_row, "*** ADMIN OVERRIDE MODE ***")
        bounded.print_centered(start_row + 1, f"Hunter: {name}")
        bounded.print_centered(start_row + 3, "SCANNING FOR WUZUS...")
        wuzu_label = "Wuzu" if len(self.found) == 1 else "Wuzus"
        bounded.print_centered(start_row + 5, f"Found: {len(self.found)} {wuzu_label}")
        row = 7
        if self.unknown:
            entity_label = "Unknown Entity Detected" if len(self.unknown) == 1 else "Unknown Entities Detected"
            bounded.print_centered(start_row + row, f"{len(self.unknown)} {entity_label}")
            row += 1
        if self.rejected:
            rejected_label = "Wuzu Rejected" if len(self.rejected) == 1 else "Wuzus Rejected"
            bounded.print_centered(start_row + row, f"{len(self.rejected)} {rejected_label}")

    def render_footer(self, bounded, app_state):
        title = "OVERRIDE MODE" if self.override else "SCORING MODE"
        bounded.set_title(title)
        bounded.print_content(1, "Scan Wuzus to score points!")
        bounded.print_content(2, "[X] Exit")


# =============================================================================
# RESULTS SCREEN
# =============================================================================
class ResultsScreen(Screen):
    def __init__(self, app, hunter_uid, wuzus, session_points=0, rank_before=None,
                 unknown_count=0, rejected=None, override=False):
        super().__init__(app)
        self.hunter_uid = hunter_uid
        self.wuzus = list(wuzus)
        self.session_points = session_points
        self.rank_before = rank_before
        self.unknown_count = unknown_count
        self.rejected = rejected or {}
        self.override = override
        self.timeout = app.config.get('timing', {}).get('results_display', 10)
        self.start_time = time.time()  # Track when we started

    def get_panel_sizes(self, available_rows):
        """This screen wants all space for results display"""
        return {
            'main': available_rows,
            'secondary': None
        }

    def get_active_timeout(self):
        elapsed = time.time() - self.start_time
        left = max(0, int(self.timeout - elapsed))
        return ("RESULTS", left)

    def handle(self, key, uid):
        if key == "r":
            self.app.tui.force_full_redraw()
            return

        # Calculate remaining time based on actual elapsed time
        elapsed = time.time() - self.start_time
        remaining = max(0, self.timeout - elapsed)
        
        # Always update footer to show countdown
        self.app.tui.mark_dirty(PANEL_FOOTER)
        
        if key == "x" or remaining <= 0:
            self.app.switch_screen(StartScreen(self.app))

    def render_main(self, bounded, app_state):
        """Show results summary"""
        bounded.set_title("SCAN COMPLETE")

        hunter = self.app.db.get_hunter(self.hunter_uid)
        name = hunter['name'] if hunter else "Unknown"
        total_points = hunter['points'] if hunter else 0
        total_unique = self.app.db.get_hunter_total_wuzus(self.hunter_uid)
        total_scans = self.app.db.get_hunter_total_scans(self.hunter_uid)
        current_rank = self.app.db.get_hunter_rank(self.hunter_uid)

        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 14) // 2 + 1

        if self.override:
            bounded.print_centered(start_row, "OVERRIDE SCAN COMPLETE!")
        else:
            bounded.print_centered(start_row, "SCAN COMPLETE!")
        bounded.print_centered(start_row + 2, f"Hunter: {name}")
        bounded.print_centered(start_row + 4, "--- THIS SESSION ---")
        bounded.print_centered(start_row + 5, f"Wuzus Found: {len(self.wuzus)}    Points Earned: {self.session_points}")
        row = 6
        if self.unknown_count > 0:
            entity_label = "Unknown Entity Detected" if self.unknown_count == 1 else "Unknown Entities Detected"
            bounded.print_centered(start_row + row, f"{self.unknown_count} {entity_label}")
            row += 1
        if self.rejected:
            rejected_label = "Wuzu Rejected" if len(self.rejected) == 1 else "Wuzus Rejected"
            bounded.print_centered(start_row + row, f"{len(self.rejected)} {rejected_label}")
            row += 1
            # Show deduplicated reasons
            unique_reasons = set(self.rejected.values())
            for reason in list(unique_reasons)[:2]:
                count = sum(1 for r in self.rejected.values() if r == reason)
                bounded.print_centered(start_row + row, f"  ({count}x) {reason}")
                row += 1
        bounded.print_centered(start_row + row, "--- ALL TIME ---")
        bounded.print_centered(start_row + row + 1, f"Unique Wuzus: {total_unique}    Total Scans: {total_scans}    Total Points: {total_points}")

        rank_text = f"Rank: #{current_rank}" if current_rank else "Rank: --"
        if self.rank_before and current_rank and current_rank < self.rank_before:
            rank_text += f" (up from #{self.rank_before}!)"
        elif self.rank_before and current_rank and current_rank > self.rank_before:
            rank_text += f" (down from #{self.rank_before})"
        bounded.print_centered(start_row + row + 3, rank_text)

    def render_footer(self, bounded, app_state):
        bounded.set_title("RESULTS")
        bounded.print_content(1, "Returning to main screen...")
        bounded.print_content(2, "[X] Return now")


# =============================================================================
# APP CONTROLLER
# =============================================================================
def format_uptime(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    return f"{h:02}:{m:02}:{s:02}"

def format_ago(ts):
    if ts is None:
        return "--"
    delta = int(time.time() - ts)
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta//60}m"
    return f"{delta//3600}h"


class WuzuApp:
    def __init__(self, config):
        self.config = config
        self.terminal = Terminal()
        self.tui = TUIEngine()
        self.terminal.clear()

        self.nfc = NFCReader()
        self.uhf = create_uhf_reader(config)
        
        # Database connection
        self.db = DatabaseManager(config)
        
        # Test database connection and store status
        db_status = self.db.test_connection()
        self.db_status = db_status['status']
        
        if db_status['status'] != 'OFFLINE':
            if db_status['version']:
                version_parts = db_status['version'].split()
                if len(version_parts) > 1:
                    print(f"[DB] PostgreSQL {version_parts[1]}")
            print(f"[DB] Status: {db_status['status']}")
        else:
            print(f"[DB] WARNING: Database offline - running in demo mode")

        self.data = {
            "start": time.time(),
        }

        self.authenticated_admin = None
        self.screen = StartScreen(self)
        self.db.log_system_event("SYSTEM_START", details="Application started")
        self.last_time_update = 0
        self.last_data_refresh = 0
        self.last_db_health_check = 0
        self.data_refresh_interval = config.get('timing', {}).get('leaderboard_refresh', 60)
        self.db_health_check_interval = 30

    def beep(self, beep_type):
        if not self.config.get('audio', {}).get('beep_enabled', True):
            return

        beep_cfg = self.config.get('audio', {}).get('beeps', {}).get(beep_type)
        if beep_cfg is None:
            return

        if self.uhf.connected:
            active, silent, times = beep_cfg
            self.uhf.beep(active, silent, times)

    def switch_screen(self, screen):
        self.screen = screen
        self.tui.force_full_redraw()

    def register_hunter(self, uid, name):
        if self.db.add_hunter(uid, name):
            self.log_event("NEW", hunter_uid=uid, details=f"Hunter '{name}' registered")
            self.beep("hunter_id")
            self.tui.force_full_redraw()

    def register_wuzu(self, epc):
        default_points = self.config.get('scoring', {}).get('default_points', 10)
        if self.db.add_wuzu(epc, points_value=default_points):
            self.log_event("NEW", wuzu_epc=epc, details="New Wuzu registered")
            self.beep("new_wuzu")
            self.tui.force_full_redraw()

    def log_event(self, event_type, hunter_uid=None, wuzu_epc=None, details="", points=0, private=False):
        self.db.log_event(event_type, hunter_uid, wuzu_epc, details, points, private)
        self.tui.mark_dirty(PANEL_SECONDARY)
    
    def record_wuzu_scan(self, hunter_uid, wuzu_epc, points=10, override=False):
        """Record a wuzu scan and update scores"""
        hunter = self.db.get_hunter(hunter_uid)
        if hunter:
            self.db.update_hunter_score(hunter_uid, points)

            wuzu = self.db.get_wuzu(wuzu_epc)
            if wuzu:
                self.db.increment_wuzu_found(wuzu_epc)
                wuzu_name = wuzu.get('name') or "a Wuzu"
            else:
                wuzu_name = f"Unregistered ({wuzu_epc[:12]}...)"

            event_type = "OVERRIDE_SCORE" if override else "SCORE"
            prefix = "[OVERRIDE] " if override else ""
            # Use None for wuzu_epc if unregistered (FK constraint would reject unknown EPCs)
            epc_for_event = wuzu_epc if wuzu else None
            self.log_event(event_type, hunter_uid, epc_for_event,
                          f"{prefix}{hunter['name']} caught {wuzu_name} (+{points}pts)",
                          points)

    def run(self):
        print("Starting application...")
        time.sleep(2)
        self.terminal.clear()

        # On Linux/RPi, disable terminal echo and canonical mode so keystrokes
        # don't appear at the cursor position (the bottom status bar row).
        # Also disable ICRNL so Enter delivers \r consistently (not \n).
        old_tty_settings = None
        if platform.system() != "Windows":
            old_tty_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin)
            mode = termios.tcgetattr(sys.stdin)
            mode[0] &= ~termios.ICRNL  # Don't translate CR to NL
            termios.tcsetattr(sys.stdin, termios.TCSANOW, mode)
        print("\033[?25l", end="", flush=True)  # Hide cursor

        try:
            while True:
                time.sleep(self.config.get('timing', {}).get('nfc_poll_interval', 0.05))

                key = read_key()

                uid = self.nfc.poll_for_card()
                self.screen.handle(key, uid)

                now = time.time()

                # Update time display every second
                if now - self.last_time_update >= 1:
                    self.tui.mark_dirty(PANEL_STATUS)
                    self.last_time_update = now

                # Refresh leaderboard data periodically
                if now - self.last_data_refresh >= self.data_refresh_interval:
                    self.tui.mark_dirty(PANEL_MAIN)
                    self.last_data_refresh = now

                # Check database health periodically
                if now - self.last_db_health_check >= self.db_health_check_interval:
                    db_status = self.db.test_connection()
                    if db_status['status'] != self.db_status:
                        old_status = self.db_status
                        self.db_status = db_status['status']
                        self.tui.mark_dirty(PANEL_STATUS)
                    self.last_db_health_check = now

                self.tui.render(self.screen, self.terminal, self.data)

        except KeyboardInterrupt:
            pass
        finally:
            print("\033[?25h", end="", flush=True)  # Show cursor
            if old_tty_settings is not None:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty_settings)
            self.terminal.clear()
            self.db.close()
            print("Exiting...")


# =============================================================================
# CONFIG
# =============================================================================
def load_config(path='config.toml'):
    if not os.path.exists(path):
        print("No config.toml found, using defaults")
        return get_default_config()

    with open(path, 'rb') as f:
        return tomllib.load(f)

def get_default_config():
    return {
        'database': {
            'host': 'localhost',
            'port': 5432,
            'database': 'wuzu_game',
            'user': 'wuzu_user',
            'password': '',
        },
        'hardware': {
            'uhf_port': None,
            'uhf_baudrate': 57600,
            'uhf_power': 20,
            'uhf_type': '',
        },
        'timing': {
            'scan_timeout': 5,
            'results_display': 10,
            'scan_interval': 0.2,
            'nfc_poll_interval': 0.05,
            'leaderboard_refresh': 60,
            'idle_timeout': 120,
            'screensaver_interval': 5,
        },
        'audio': {
            'beep_enabled': True,
            'beeps': {
                'new_wuzu': [1, 0, 1],
                'hunter_id': [0, 0, 0],
                'complete': [0, 0, 0],
            }
        },
        'scoring': {
            'default_points': 10,
            'cooldown_minutes': 1,
            'scan_out': False,
            'cooldown_overrides_scan_out': False,
        },
        'display': {
            'border_char': '─',
            'main_title': 'Wuzu Scanner',
        }
    }


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    config = load_config()
    WuzuApp(config).run()