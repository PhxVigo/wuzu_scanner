#!/usr/bin/env python3
"""
WUZU SCANNER - Database-Integrated Version (2025)
"""

import sys, time, shutil, os, platform
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


class UHFReader:
    def __init__(self, port=None, baud=57600):
        self.ser = None
        if not SERIAL_AVAILABLE:
            print("[UHF] Serial support unavailable — demo mode.")
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
                       ORDER BY points DESC, name ASC
                       LIMIT %s""",
                    (limit,)
                )
                return cur.fetchall()
        except Exception as e:
            print(f"[DB] Error fetching hunters: {e}")
            return []
    
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
    def add_wuzu(self, epc, points_value=10):
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
    
    def get_wuzu_points(self, epc):
        """Get points value for a wuzu"""
        if not self.conn:
            return 10  # Default
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT points_value FROM wuzus WHERE epc = %s", (epc,))
                result = cur.fetchone()
                return result[0] if result else 10
        except:
            return 10
    
    # === SCAN EVENTS ===
    def log_event(self, event_type, hunter_uid=None, wuzu_epc=None, details="", points=0):
        """Log a scan event"""
        if not self.conn:
            return False
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO scan_events 
                       (event_type, hunter_uid, wuzu_epc, details, points_awarded)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (event_type, hunter_uid, wuzu_epc, details, points)
                )
            return True
        except Exception as e:
            print(f"[DB] Error logging event: {e}")
            return False
    
    def get_recent_events(self, limit=50):
        """Get recent scan events for display"""
        if not self.conn:
            return []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT timestamp, event_type, hunter_uid, wuzu_epc, 
                              details, points_awarded
                       FROM scan_events
                       ORDER BY timestamp DESC
                       LIMIT %s""",
                    (limit,)
                )
                return cur.fetchall()
        except Exception as e:
            print(f"[DB] Error fetching events: {e}")
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
# TUI ENGINE
# =============================================================================
class TUIEngine:
    def __init__(self):
        self.panels = {"header": True, "hunters": True, "log": True, "footer": True}

    def mark_dirty(self, panel):
        self.panels[panel] = True

    def force_full_redraw(self):
        for p in self.panels:
            self.panels[p] = True

    def render(self, screen, terminal, app_state):
        cols, rows = terminal.size()

        HEADER_H = 2  # status bar + title bar
        HUNTERS_H = 15
        FOOTER_H = 5
        LOG_H = rows - (HEADER_H + HUNTERS_H + FOOTER_H) - 1

        layout = {
            "header": 0,
            "hunters": HEADER_H,
            "log": HEADER_H + HUNTERS_H,
            "footer": rows - FOOTER_H,
        }

        for panel, dirty in self.panels.items():
            if not dirty:
                continue
            terminal.move_to(layout[panel], 0)
            render_fn = getattr(screen, f"render_{panel}", None)
            if callable(render_fn):
                render_fn(terminal, app_state, cols, rows)
            self.panels[panel] = False

        sys.stdout.flush()


# =============================================================================
# SCREEN BASE CLASS (Refactored)
# =============================================================================
class Screen:
    """Base screen with shared helpers."""
    header_title = ""  # subclasses only set this string

    def __init__(self, app):
        self.app = app

    # -------------------------------------------------------------------------
    # Universal Status Bar (first line)
    # -------------------------------------------------------------------------
    def render_status_bar(self, terminal, app_state, cols):
        uptime = format_uptime(time.time() - app_state["start"])
        now = time.strftime("%H:%M:%S")
        
        # Get last scan from DB
        recent = self.app.db.get_recent_events(1)
        last_scan = recent[0]['timestamp'].strftime("%H:%M:%S") if recent else "--:--:--"
        
        # Get database status from app
        db_status = self.app.db_status

        status = f" DB:{db_status} | UPTIME:{uptime} | LAST-SCAN:{last_scan} | TIME:{now} "
        terminal.print_row(0, "┌" + status.ljust(cols - 2, "─") + "┐")

    # -------------------------------------------------------------------------
    # Title Header (second line)
    # -------------------------------------------------------------------------
    def render_header(self, terminal, app_state, cols, rows):
        self.render_status_bar(terminal, app_state, cols)
        title = f" {self.header_title} "
        terminal.print_row(1, "├" + title.ljust(cols - 2, "─") + "┤")

    # -------------------------------------------------------------------------
    # Panel fillers
    # -------------------------------------------------------------------------
    def render_empty_panel(self, terminal, top, height, cols):
        for i in range(height):
            terminal.print_row(top + i, "│" + " "*(cols - 2) + "│")

    # -------------------------------------------------------------------------
    # Footer builder
    # -------------------------------------------------------------------------
    def draw_footer(self, terminal, cols, rows, title, lines):
        start = rows - 5
        title_text = f"{COLORS['title']}[ {title} ]{COLORS['default']}"
        title_len = len(COLORS['title']) + len(COLORS['default'])
        terminal.print_row(start,
            "├" + title_text.center(cols - 2 + title_len, "─") + "┤"
        )

        for i, txt in enumerate(lines):
            terminal.print_row(
                start + 1 + i,
                "│ " + txt.ljust(cols - 4) + " │"
            )

        terminal.print_row(start + 1 + len(lines),
            "└" + "─"*(cols - 2) + "┘"
        )

    # Default no-op
    def handle(self, key, uid):
        pass


# =============================================================================
# START SCREEN
# =============================================================================
class StartScreen(Screen):
    header_title = "TOP HUNTERS"

    def handle(self, key, uid):
        if key == "a":
            self.app.switch_screen(AddHunterScreen(self.app))
        elif key == "w":
            self.app.switch_screen(AddWuzuScreen(self.app))
        elif key == "q":
            sys.exit()
        elif key == "r":
            self.app.tui.force_full_redraw()
        elif uid:
            if self.app.db.hunter_exists(uid):
                self.app.beep("hunter_id")
                self.app.switch_screen(ScanWuzuScreen(self.app, uid))
            else:
                self.app.log_event("UNKNOWN", details=f"Unregistered badge {uid}")

    def render_hunters(self, terminal, app_state, cols, rows):
        header = f"{'RANK':<5} {'NAME':<20} {'PTS':<6} {'UID':<14} {'LAST SEEN':<10}"
        terminal.print_row(2, "│ " + header.ljust(cols - 4) + " │")
        terminal.print_row(3, "│ " + ("-" * (cols - 4)) + " │")

        # Query DB for top hunters
        hunters = self.app.db.get_top_hunters(10)

        for i, hunter in enumerate(hunters, start=1):
            last = hunter.get("last_seen")
            age = format_ago(last.timestamp()) if last else "--"
            row = f"{i:02} {hunter['name']:<20} {hunter['points']:<6} {hunter['uid']:<14} {age:<10}"
            terminal.print_row(3 + i, "│ " + row.ljust(cols - 4) + " │")

        # Empty lines fill
        for i in range(len(hunters), 10):
            terminal.print_row(4 + i, "│" + " "*(cols-2) + "│")

    def render_log(self, terminal, app_state, cols, rows):
        start = 2 + 15
        title_text = f"{COLORS['title']}[ SCAN EVENT LOG ]{COLORS['default']}"
        color_len = len(COLORS['title']) + len(COLORS['default'])
        terminal.print_row(start, "├" +
                           title_text.center(cols - 2 + color_len, "─") + "┤")

        max_lines = rows - start - 6
        
        # Query recent events from DB
        events = self.app.db.get_recent_events(max_lines)

        for i, evt in enumerate(events, start=1):
            ts = evt['timestamp'].strftime("%H:%M:%S")
            line = f"{ts} {evt['event_type']:<8} {evt['details']}"
            terminal.print_row(start + i, "│ " + line.ljust(cols - 4) + " │")

        # Fill blank
        for i in range(len(events), max_lines):
            terminal.print_row(start + 1 + i, "│" + " "*(cols-2) + "│")

    def render_footer(self, terminal, app_state, cols, rows):
        lines = [
            "[A] Add Hunter  [W] Add Wuzu  [Q] Quit  [R] Redraw Screen",
            "Scan hunter badge to begin scoring...",
        ]
        self.draw_footer(terminal, cols, rows, "OPERATOR PANEL", lines)


# =============================================================================
# ADD HUNTER SCREEN
# =============================================================================
class AddHunterScreen(Screen):
    header_title = "ADD NEW HUNTER"

    # States
    STATE_SCAN = "scan"
    STATE_NAME = "name"
    STATE_CONFIRM = "confirm"
    STATE_ERROR = "error"

    def __init__(self, app):
        super().__init__(app)
        self.state = self.STATE_SCAN
        self.uid = None
        self.name_input = ""
        self.error_msg = ""

    def handle(self, key, uid):
        if self.state == self.STATE_SCAN:
            if key == "x":
                self.app.log_event("CANCEL", details="Add-Hunter cancelled")
                self.app.switch_screen(StartScreen(self.app))
                return            
            if uid:
                # Check if UID already exists
                if self.app.db.hunter_exists(uid):
                    self.app.log_event("DUPLICATE", details=f"Hunter {uid} already registered")
                    self.error_msg = f"UID {uid} already registered!"
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
            elif key == "\x7f" or key == "\x08":  # Backspace
                self.name_input = self.name_input[:-1]
                self.app.tui.mark_dirty("footer")
            elif key and len(key) == 1 and (key.isalnum() or key in ' -'):
                self.name_input += key
                self.app.tui.mark_dirty("footer")

        elif self.state == self.STATE_CONFIRM:
            if key == "x":
                self.app.log_event("CANCEL", details="Add-Hunter cancelled")
                self.app.switch_screen(StartScreen(self.app))
                return
            if key in ["y", "\n", "\r"]:
                # Check name uniqueness
                name = self.name_input.strip()
                if self.app.db.hunter_name_exists(name):
                    self.error_msg = f"Name '{name}' already taken!"
                    self.state = self.STATE_ERROR
                else:
                    # Commit to database
                    self.app.register_hunter(self.uid, name)
                    self.app.switch_screen(StartScreen(self.app))
                    return
                self.app.tui.force_full_redraw()
            elif key == "n":
                # Go back to name entry
                self.state = self.STATE_NAME
                self.app.tui.force_full_redraw()

        elif self.state == self.STATE_ERROR:
            # Any key returns to start
            if key:
                self.app.switch_screen(StartScreen(self.app))

    def render_hunters(self, terminal, app_state, cols, rows):
        self.render_empty_panel(terminal, 2, 14, cols)

    def render_log(self, terminal, app_state, cols, rows):
        start = 2 + 15
        h = rows - start - 6
        self.render_empty_panel(terminal, start, h, cols)

    def render_footer(self, terminal, app_state, cols, rows):
        if self.state == self.STATE_SCAN:
            lines = [
                "Scan new hunter badge...",
                "[X] Cancel"
            ]
        elif self.state == self.STATE_NAME:
            lines = [
                f"UID: {self.uid}",
                f"Name: {self.name_input}_",
                "Enter name and press ENTER"
            ]
        elif self.state == self.STATE_CONFIRM:
            lines = [
                f"UID: {self.uid}",
                f"Name: {self.name_input.strip()}",
                "Confirm? [Y/n]  [X] Cancel"
            ]
        elif self.state == self.STATE_ERROR:
            lines = [
                self.error_msg,
                "Press any key to continue..."
            ]
        else:
            lines = ["", ""]

        self.draw_footer(terminal, cols, rows, "ADD HUNTER", lines)


# =============================================================================
# ADD WUZU SCREEN
# =============================================================================
class AddWuzuScreen(Screen):
    header_title = "ADD NEW WUZU"

    def __init__(self, app):
        super().__init__(app)
        self.timeout = app.config.get('timing', {}).get('scan_timeout', 10)
        self.start_time = time.time()

    def handle(self, key, uid):
        if time.time() - self.start_time > self.timeout:
            self.app.log_event("TIMEOUT", details="Add-Wuzu: no scan")
            self.app.switch_screen(StartScreen(self.app))
            return

        if key == "x":
            self.app.log_event("CANCEL", details="Add-Wuzu cancelled")
            self.app.switch_screen(StartScreen(self.app))
            return

        tags = self.app.uhf.inventory()
        if tags:
            for t in tags:
                epc = t["epc"]
                if not self.app.db.wuzu_exists(epc):
                    self.app.register_wuzu(epc)
                else:
                    self.app.log_event("DUPLICATE", details=f"Wuzu {epc} already registered")
                self.app.switch_screen(StartScreen(self.app))
                return

        self.app.tui.mark_dirty("footer")

    def render_hunters(self, terminal, app_state, cols, rows):
        self.render_empty_panel(terminal, 2, 14, cols)

    def render_log(self, terminal, app_state, cols, rows):
        start = 2 + 15
        h = rows - start - 6
        self.render_empty_panel(terminal, start, h, cols)

    def render_footer(self, terminal, app_state, cols, rows):
        left = max(0, int(self.timeout - (time.time() - self.start_time)))
        lines = [
            "Scan new Wuzu tag with UHF reader...",
            f"Timeout in {left}s  [X] Cancel",
        ]
        self.draw_footer(terminal, cols, rows, "ADD WUZU", lines)


# =============================================================================
# SCAN WUZU SCREEN
# =============================================================================
class ScanWuzuScreen(Screen):
    header_title = "SCANNING WUZUS"

    def __init__(self, app, hunter_uid):
        super().__init__(app)
        self.hunter_uid = hunter_uid
        self.found = set()
        self.last_time = time.time()
        self.timeout = app.config.get('timing', {}).get('scan_timeout', 5)

    def handle(self, key, uid):
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
            if epc not in self.found:
                self.found.add(epc)
                self.last_time = time.time()
                
                hunter = self.app.db.get_hunter(self.hunter_uid)
                if hunter:
                    points = self.app.db.get_wuzu_points(epc)
                    self.app.record_wuzu_scan(self.hunter_uid, epc, points)
                    self.app.beep("new_wuzu")
                    self.app.tui.mark_dirty("footer")
                    self.app.tui.mark_dirty("hunters")

        if time.time() - self.last_time > self.timeout:
            self.app.beep("complete")
            self.app.switch_screen(ResultsScreen(self.app, self.hunter_uid, self.found))

    def render_hunters(self, terminal, app_state, cols, rows):
        self.render_empty_panel(terminal, 2, 14, cols)

    def render_log(self, terminal, app_state, cols, rows):
        start = 2 + 15
        h = rows - start - 6
        self.render_empty_panel(terminal, start, h, cols)

    def render_footer(self, terminal, app_state, cols, rows):
        hunter = self.app.db.get_hunter(self.hunter_uid)
        name = hunter['name'] if hunter else "Unknown"
        left = max(0, int(self.timeout - (time.time() - self.last_time)))

        lines = [
            f"{name} is hunting! Scan Wuzus to score points.",
            f"Wuzus found: {len(self.found)}  Time remaining: {left}s  [X] Exit",
        ]
        self.draw_footer(terminal, cols, rows, "SCORING MODE", lines)


# =============================================================================
# RESULTS SCREEN
# =============================================================================
class ResultsScreen(Screen):
    header_title = "SCAN COMPLETE"

    def __init__(self, app, hunter_uid, wuzus):
        super().__init__(app)
        self.hunter_uid = hunter_uid
        self.wuzus = list(wuzus)
        self.timer = app.config.get('timing', {}).get('results_display', 10)

    def handle(self, key, uid):
        self.timer -= 0.05
        self.app.tui.mark_dirty("footer")
        if key == "x" or self.timer <= 0:
            self.app.switch_screen(StartScreen(self.app))

    def render_hunters(self, terminal, app_state, cols, rows):
        self.render_empty_panel(terminal, 2, 14, cols)

    def render_log(self, terminal, app_state, cols, rows):
        start = 2 + 15
        h = rows - start - 6
        self.render_empty_panel(terminal, start, h, cols)

    def render_footer(self, terminal, app_state, cols, rows):
        hunter = self.app.db.get_hunter(self.hunter_uid)
        name = hunter['name'] if hunter else "Unknown"
        lines = [
            f"Hunter: {name} | Wuzus found: {len(self.wuzus)}",
            f"Returning in {int(self.timer)}s...  [X] Return now",
        ]
        self.draw_footer(terminal, cols, rows, "RESULTS", lines)


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
        self.uhf = UHFReader(
            port=config.get('hardware', {}).get('uhf_port'),
            baud=config.get('hardware', {}).get('uhf_baudrate', 57600),
        )
        
        # Database connection
        self.db = DatabaseManager(config)
        
        # Test database connection and store status
        db_status = self.db.test_connection()
        self.db_status = db_status['status']
        
        if db_status['status'] != 'OFFLINE':
            if db_status['version']:
                # Extract just the PostgreSQL version number
                version_parts = db_status['version'].split()
                if len(version_parts) > 1:
                    print(f"[DB] PostgreSQL {version_parts[1]}")
            print(f"[DB] Status: {db_status['status']}")
        else:
            print(f"[DB] WARNING: Database offline - running in demo mode")

        self.data = {
            "start": time.time(),
        }

        self.screen = StartScreen(self)
        self.last_time_update = 0
        self.last_data_refresh = 0
        self.last_db_health_check = 0
        # Configurable leaderboard refresh interval (default 60 seconds)
        self.data_refresh_interval = config.get('timing', {}).get('leaderboard_refresh', 60)
        # Check database health every 30 seconds
        self.db_health_check_interval = 30

    def beep(self, beep_type):
        if not self.config.get('audio', {}).get('beep_enabled', True):
            return

        beep_cfg = self.config.get('audio', {}).get('beeps', {}).get(beep_type)
        if beep_cfg is None:
            return

        if self.uhf.ser:
            active, silent, times = beep_cfg
            self.uhf.beep(active, silent, times)

    def switch_screen(self, screen):
        self.screen = screen
        self.tui.force_full_redraw()

    def register_hunter(self, uid, name):
        if self.db.add_hunter(uid, name):
            self.log_event("NEW", hunter_uid=uid, details=f"Hunter '{name}' UID {uid}")
            self.beep("hunter_id")
            self.tui.force_full_redraw()

    def register_wuzu(self, epc):
        if self.db.add_wuzu(epc):
            self.log_event("NEW", wuzu_epc=epc, details=f"Wuzu EPC {epc}")
            self.beep("new_wuzu")
            self.tui.force_full_redraw()

    def log_event(self, event_type, hunter_uid=None, wuzu_epc=None, details="", points=0):
        self.db.log_event(event_type, hunter_uid, wuzu_epc, details, points)
        self.tui.mark_dirty("log")
    
    def record_wuzu_scan(self, hunter_uid, wuzu_epc, points=10):
        """Record a wuzu scan and update scores"""
        hunter = self.db.get_hunter(hunter_uid)
        if hunter:
            self.db.update_hunter_score(hunter_uid, points)
            self.db.increment_wuzu_found(wuzu_epc)
            self.log_event("SCORE", hunter_uid, wuzu_epc, 
                          f"{hunter['name']} caught Wuzu {wuzu_epc} (+{points}pts)", 
                          points)

    def run(self):
        print("Starting application...")
        time.sleep(2)
        self.terminal.clear()

        try:
            while True:
                key = read_key()
                uid = self.nfc.poll_for_card()
                self.screen.handle(key, uid)

                now = time.time()
                
                # Update time display every second
                if now - self.last_time_update >= 1:
                    self.tui.mark_dirty("header")
                    self.last_time_update = now
                
                # Refresh leaderboard data periodically
                if now - self.last_data_refresh >= self.data_refresh_interval:
                    self.tui.mark_dirty("hunters")
                    self.last_data_refresh = now
                
                # Check database health periodically
                if now - self.last_db_health_check >= self.db_health_check_interval:
                    db_status = self.db.test_connection()
                    if db_status['status'] != self.db_status:
                        old_status = self.db_status
                        self.db_status = db_status['status']
                        print(f"[DB] Status changed: {old_status} -> {self.db_status}")
                        self.tui.mark_dirty("header")
                    self.last_db_health_check = now

                self.tui.render(self.screen, self.terminal, self.data)

        except KeyboardInterrupt:
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
            'password': '',  # Must be set in config.toml
        },
        'hardware': {
            'uhf_port': None,
            'uhf_baudrate': 57600,
            'uhf_power': 20,
        },
        'timing': {
            'scan_timeout': 5,
            'results_display': 10,
            'scan_interval': 0.2,
            'nfc_poll_interval': 0.05,
            'leaderboard_refresh': 60,
        },
        'audio': {
            'beep_enabled': True,
            'beeps': {
                'new_wuzu': [1, 0, 1],
                'hunter_id': [0, 0, 0],
                'complete': [0, 0, 0],
            }
        },
        'display': {
            'border_char': '─',
            'title': 'WUZU SCANNER',
        }
    }


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    config = load_config()
    WuzuApp(config).run()
