#!/usr/bin/env python3
"""
WUZU SCANNER - Database-Integrated Version (2025)
With Bounded Terminal Panel System and Dynamic Panel Sizing
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
                 draw_borders=True, top_border="├", bottom_border=None):
        self.terminal = terminal
        self.start_row = start_row
        self.end_row = end_row
        self.start_col = start_col
        
        term_cols, _ = terminal.size()
        self.end_col = end_col if end_col is not None else term_cols
        
        self.draw_borders = draw_borders
        self.top_border = top_border
        self.bottom_border = bottom_border
        
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
        
        # Top border
        if self.top_border:
            right_corner = "┤" if self.top_border == "├" else "┐"
            self.terminal.print_row(self.start_row, 
                self.top_border + "─" * (cols - 2) + right_corner)
        
        # Side borders for all content rows
        for row in range(self.start_row + 1, self.end_row - (1 if self.bottom_border else 0)):
            self.terminal.move_to(row, self.start_col)
            print("│", end="")
            self.terminal.move_to(row, self.end_col - 1)
            print("│", end="")
        
        # Bottom border
        if self.bottom_border:
            self.terminal.print_row(self.end_row - 1,
                self.bottom_border + "─" * (cols - 2) + "┘")
    
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
        
        if self.start_row < abs_row < self.end_row - (1 if self.bottom_border else 0):
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
        for row in range(self.start_row + 1, self.end_row - (1 if self.bottom_border else 0)):
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
# TUI ENGINE WITH DYNAMIC PANEL SIZING
# =============================================================================
class TUIEngine:
    def __init__(self):
        self.panels = {"status": True, "main": True, "secondary": True, "footer": True}

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
        STATUS_H = 1
        FOOTER_H = 5
        available = rows - (STATUS_H + FOOTER_H)
        
        # Ask the screen how it wants to divide the available space
        sizes = screen.get_panel_sizes(available)
        
        main_h = sizes.get('main', 16)
        sec_h = sizes.get('secondary', available - main_h)
        
        # Ensure sizes fit within available space
        if main_h + sec_h > available:
            # Proportionally scale down if too large
            total = main_h + sec_h
            main_h = int(available * (main_h / total))
            sec_h = available - main_h
        
        layout = {
            "status": (0, STATUS_H),
            "main": (STATUS_H, STATUS_H + main_h),
        }
        
        # Only add secondary if it has height
        if sec_h > 0:
            layout["secondary"] = (STATUS_H + main_h, STATUS_H + main_h + sec_h)
        
        layout["footer"] = (rows - FOOTER_H, rows)
        
        return layout

    def render(self, screen, terminal, app_state):
        """Render all dirty panels"""
        cols, rows = terminal.size()
        layout = self.get_layout(cols, rows, screen)

        for panel_name, dirty in self.panels.items():
            if not dirty:
                continue
            
            # Skip panels not in layout (e.g., secondary with 0 height)
            if panel_name not in layout:
                continue
                
            # Get panel bounds
            start_row, end_row = layout[panel_name]
            
            # Create bounded terminal with appropriate borders
            if panel_name == "status":
                # Status bar: no borders, just content
                bounded = BoundedTerminal(terminal, start_row, end_row, 0, cols,
                                        draw_borders=False)
            elif panel_name == "main":
                # Main: top border (┌) since it's first bordered panel after status
                bounded = BoundedTerminal(terminal, start_row, end_row, 0, cols,
                                        draw_borders=True, top_border="┌", bottom_border=None)
            elif panel_name == "footer":
                # Footer: bottom border (└)
                bounded = BoundedTerminal(terminal, start_row, end_row, 0, cols,
                                        draw_borders=True, top_border="├", bottom_border="└")
            else:
                # Secondary: middle border (├)
                bounded = BoundedTerminal(terminal, start_row, end_row, 0, cols,
                                        draw_borders=True, top_border="├", bottom_border=None)
            
            # Call screen's render method for this panel
            render_fn = getattr(screen, f"render_{panel_name}", None)
            if callable(render_fn):
                render_fn(bounded, app_state)
            
            self.panels[panel_name] = False

        sys.stdout.flush()


# =============================================================================
# SCREEN BASE CLASS
# =============================================================================
class Screen:
    """Base screen with panel rendering methods."""

    def __init__(self, app):
        self.app = app

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
    # STATUS BAR (never changes, always in base class)
    # -------------------------------------------------------------------------
    def render_status(self, bounded, app_state):
        """Render the status bar - same for all screens"""
        cols, _ = bounded.size()
        
        uptime = format_uptime(time.time() - app_state["start"])
        now = time.strftime("%H:%M:%S")
        
        recent = self.app.db.get_recent_events(1)
        last_scan = recent[0]['timestamp'].strftime("%H:%M:%S") if recent else "--:--:--"
        
        db_status = self.app.db_status
        status = f" DB:{db_status} | UPTIME:{uptime} | LAST-SCAN:{last_scan} | TIME:{now} "
        
        # Just print the status text, no borders
        bounded.print_row(0, status.ljust(cols))

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
        bounded.set_title("FOOTER")

    # Default no-op handler
    def handle(self, key, uid):
        pass


# =============================================================================
# START SCREEN
# =============================================================================
class StartScreen(Screen):
    def get_panel_sizes(self, available_rows):
        """Default layout: 16 rows for leaderboard, rest for event log"""
        return {
            'main': 16,
            'secondary': available_rows - 16
        }

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

    def render_main(self, bounded, app_state):
        """Render top hunters leaderboard"""
        bounded.set_title("TOP HUNTERS")
        
        # Header row
        header = f"{'RANK':<5} {'NAME':<20} {'PTS':<6} {'UID':<14} {'LAST SEEN':<10}"
        bounded.print_content(1, header)
        bounded.print_content(2, "-" * 60)

        # Query hunters
        hunters = self.app.db.get_top_hunters(10)

        for i, hunter in enumerate(hunters, start=1):
            last = hunter.get("last_seen")
            age = format_ago(last.timestamp()) if last else "--"
            row = f"{i:02} {hunter['name']:<20} {hunter['points']:<6} {hunter['uid']:<14} {age:<10}"
            bounded.print_content(2 + i, row)

    def render_secondary(self, bounded, app_state):
        """Render scan event log"""
        bounded.set_title("SCAN EVENT LOG")

        # Query recent events
        content_cols, content_rows = bounded.content_size()
        events = self.app.db.get_recent_events(content_rows - 1)

        for i, evt in enumerate(events, start=1):
            ts = evt['timestamp'].strftime("%H:%M:%S")
            line = f"{ts} {evt['event_type']:<8} {evt['details']}"
            bounded.print_content(i, line[:content_cols])

    def render_footer(self, bounded, app_state):
        """Render operator controls"""
        bounded.set_title("OPERATOR PANEL")
        bounded.print_content(1, "[A] Add Hunter  [W] Add Wuzu  [Q] Quit  [R] Redraw Screen")
        bounded.print_content(2, "Scan hunter badge to begin scoring...")


# =============================================================================
# ADD HUNTER SCREEN
# =============================================================================
class AddHunterScreen(Screen):
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

    def get_panel_sizes(self, available_rows):
        """This screen wants all space for the form, no secondary panel"""
        return {
            'main': available_rows,
            'secondary': 0
        }

    def handle(self, key, uid):
        if self.state == self.STATE_SCAN:
            if key == "x":
                self.app.log_event("CANCEL", details="Add-Hunter cancelled")
                self.app.switch_screen(StartScreen(self.app))
                return            
            if uid:
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
            elif key == "\x7f" or key == "\x08":
                self.name_input = self.name_input[:-1]
                self.app.tui.mark_dirty("main")
            elif key and len(key) == 1 and (key.isalnum() or key in ' -'):
                self.name_input += key
                self.app.tui.mark_dirty("main")

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
# ADD WUZU SCREEN
# =============================================================================
class AddWuzuScreen(Screen):
    STATE_SCAN = "scan"
    STATE_ERROR = "error"
    
    def __init__(self, app):
        super().__init__(app)
        self.state = self.STATE_SCAN
        self.timeout = app.config.get('timing', {}).get('scan_timeout', 10)
        self.start_time = time.time()
        self.error_msg = ""

    def get_panel_sizes(self, available_rows):
        """This screen wants all space for scanning status"""
        return {
            'main': available_rows,
            'secondary': 0
        }

    def handle(self, key, uid):
        if self.state == self.STATE_SCAN:
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
                    self.app.beep("new_wuzu")
                    if not self.app.db.wuzu_exists(epc):
                        self.app.register_wuzu(epc)
                        self.app.switch_screen(StartScreen(self.app))
                        return
                    else:
                        self.app.log_event("DUPLICATE", details=f"Wuzu {epc} already registered")
                        self.error_msg = f"Wuzu {epc} already registered!"
                        self.state = self.STATE_ERROR
                        self.app.tui.force_full_redraw()
                        return

            self.app.tui.mark_dirty("footer")
        
        elif self.state == self.STATE_ERROR:
            # Any key returns to start
            if key:
                self.app.switch_screen(StartScreen(self.app))

    def render_main(self, bounded, app_state):
        """Show scanning status or error"""
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 8) // 2 + 1
        
        if self.state == self.STATE_SCAN:
            bounded.set_title("ADD NEW WUZU")
            left = max(0, int(self.timeout - (time.time() - self.start_time)))
            
            bounded.print_centered(start_row + 1, "Scanning for UHF tags...")
            bounded.print_centered(start_row + 3, f"Timeout in {left} seconds")
        
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
        else:
            bounded.print_content(1, "[X] Return to main screen")


# =============================================================================
# SCAN WUZU SCREEN
# =============================================================================
class ScanWuzuScreen(Screen):
    def __init__(self, app, hunter_uid):
        super().__init__(app)
        self.hunter_uid = hunter_uid
        self.found = set()
        self.last_time = time.time()
        self.timeout = app.config.get('timing', {}).get('scan_timeout', 5)

    def get_panel_sizes(self, available_rows):
        """This screen wants all space for scanning display"""
        return {
            'main': available_rows,
            'secondary': 0
        }

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
                    self.app.tui.mark_dirty("main")
                    self.app.tui.mark_dirty("footer")
        
        # Mark footer dirty every loop to update countdown timer
        self.app.tui.mark_dirty("footer")

        if time.time() - self.last_time > self.timeout:
            self.app.beep("complete")
            self.app.switch_screen(ResultsScreen(self.app, self.hunter_uid, self.found))

    def render_main(self, bounded, app_state):
        """Show scanning progress"""
        bounded.set_title("SCANNING WUZUS")
        
        hunter = self.app.db.get_hunter(self.hunter_uid)
        name = hunter['name'] if hunter else "Unknown"
        
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1
        
        bounded.print_centered(start_row + 1, f"Hunter: {name}")
        bounded.print_centered(start_row + 3, "SCANNING FOR WUZUS...")
        bounded.print_centered(start_row + 5, f"Found: {len(self.found)} wuzus")

    def render_footer(self, bounded, app_state):
        left = max(0, int(self.timeout - (time.time() - self.last_time)))
        
        bounded.set_title("SCORING MODE")
        bounded.print_content(1, "Scan Wuzus to score points!")
        bounded.print_content(2, f"Time remaining: {left}s  [X] Exit")


# =============================================================================
# RESULTS SCREEN
# =============================================================================
class ResultsScreen(Screen):
    def __init__(self, app, hunter_uid, wuzus):
        super().__init__(app)
        self.hunter_uid = hunter_uid
        self.wuzus = list(wuzus)
        self.timeout = app.config.get('timing', {}).get('results_display', 10)
        self.start_time = time.time()  # Track when we started

    def get_panel_sizes(self, available_rows):
        """This screen wants all space for results display"""
        return {
            'main': available_rows,
            'secondary': 0
        }

    def handle(self, key, uid):
        # Calculate remaining time based on actual elapsed time
        elapsed = time.time() - self.start_time
        remaining = max(0, self.timeout - elapsed)
        
        # Always update footer to show countdown
        self.app.tui.mark_dirty("footer")
        
        if key == "x" or remaining <= 0:
            self.app.switch_screen(StartScreen(self.app))

    def render_main(self, bounded, app_state):
        """Show results summary"""
        bounded.set_title("SCAN COMPLETE")
        
        hunter = self.app.db.get_hunter(self.hunter_uid)
        name = hunter['name'] if hunter else "Unknown"
        points = hunter['points'] if hunter else 0
        
        content_cols, content_rows = bounded.content_size()
        start_row = (content_rows - 6) // 2 + 1
        
        bounded.print_centered(start_row + 1, "SCAN COMPLETE!")
        bounded.print_centered(start_row + 3, f"Hunter: {name}")
        bounded.print_centered(start_row + 4, f"Wuzus Found: {len(self.wuzus)}")
        bounded.print_centered(start_row + 5, f"Total Points: {points}")

    def render_footer(self, bounded, app_state):
        # Calculate remaining time for display
        elapsed = time.time() - self.start_time
        remaining = max(0, int(self.timeout - elapsed))
        
        bounded.set_title("RESULTS")
        bounded.print_content(1, f"Returning to main screen in {remaining}s...")
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
        self.data_refresh_interval = config.get('timing', {}).get('leaderboard_refresh', 60)
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
        self.tui.mark_dirty("secondary")
    
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
                    self.tui.mark_dirty("status")
                    self.last_time_update = now
                
                # Refresh leaderboard data periodically
                if now - self.last_data_refresh >= self.data_refresh_interval:
                    self.tui.mark_dirty("main")
                    self.last_data_refresh = now
                
                # Check database health periodically
                if now - self.last_db_health_check >= self.db_health_check_interval:
                    db_status = self.db.test_connection()
                    if db_status['status'] != self.db_status:
                        old_status = self.db_status
                        self.db_status = db_status['status']
                        print(f"[DB] Status changed: {old_status} -> {self.db_status}")
                        self.tui.mark_dirty("status")
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
            'password': '',
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