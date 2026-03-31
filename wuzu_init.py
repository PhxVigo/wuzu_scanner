# wuzu_init.py
"""
WUZU SCANNER - System Initialization Script
Sets up a fresh system: admin badge, database, and wuzu tag import.
Works on Windows, Linux, and Raspberry Pi.
"""

import sys, os, platform, time, csv, subprocess, shutil, random
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()

# =============================================================================
# ANSI Support (Windows)
# =============================================================================
if platform.system() == "Windows":
    os.system("")

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
except ImportError:
    print("Error: psycopg2 is required for initialization.")
    print("  pip install psycopg2-binary --break-system-packages")
    sys.exit(1)

# =============================================================================
# NFC READER (optional — falls back to manual input)
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
            print("[NFC] PCSC not available — will use manual UID entry.")
            return

        rlist = readers()
        if not rlist:
            print("[NFC] No NFC reader found — will use manual UID entry.")
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
# CONFIG
# =============================================================================
def load_config(path=None):
    if path is None:
        path = str(SCRIPT_DIR / "config.toml")
    if not os.path.exists(path):
        print(f"[INIT] ERROR: Config file not found: {path}")
        sys.exit(1)
    with open(path, 'rb') as f:
        return tomllib.load(f)


# =============================================================================
# HELPERS
# =============================================================================
def find_pg_dump():
    """Find pg_dump executable cross-platform."""
    # Check PATH first
    found = shutil.which("pg_dump")
    if found:
        return found

    system = platform.system()

    if system == "Windows":
        # Check common Windows PostgreSQL install paths
        pg_base = Path("C:/Program Files/PostgreSQL")
        if pg_base.exists():
            # Find all version directories, pick the latest
            versions = sorted(pg_base.iterdir(), reverse=True)
            for v in versions:
                candidate = v / "bin" / "pg_dump.exe"
                if candidate.exists():
                    return str(candidate)
    else:
        # Linux / Raspberry Pi
        for search_path in ["/usr/bin/pg_dump", "/usr/local/bin/pg_dump"]:
            if os.path.exists(search_path):
                return search_path
        # Check versioned paths
        pg_lib = Path("/usr/lib/postgresql")
        if pg_lib.exists():
            versions = sorted(pg_lib.iterdir(), reverse=True)
            for v in versions:
                candidate = v / "bin" / "pg_dump"
                if candidate.exists():
                    return str(candidate)

    return None


def parse_schema_ddl(sql_text):
    """Extract only DDL statements from schema.sql, stripping INSERT sample data."""
    lines = sql_text.splitlines(keepends=True)
    ddl_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("INSERT INTO"):
            break
        ddl_lines.append(line)
    return ''.join(ddl_lines)


def get_db_connection(db_cfg):
    """Connect to PostgreSQL and return connection."""
    try:
        conn = psycopg2.connect(
            host=db_cfg.get('host', 'localhost'),
            port=db_cfg.get('port', 5432),
            database=db_cfg.get('database'),
            user=db_cfg.get('user'),
            password=db_cfg.get('password')
        )
        conn.autocommit = False
        return conn
    except psycopg2.OperationalError as e:
        error_msg = str(e)
        if "does not exist" in error_msg:
            print(f"[DB] ERROR: Database '{db_cfg.get('database')}' does not exist.")
            print(f"[DB] Create it first with:")
            print(f"       createdb {db_cfg.get('database')}")
        else:
            print(f"[DB] ERROR: Connection failed: {e}")
            print(f"[DB] Check that PostgreSQL is running and config.toml has correct credentials.")
        sys.exit(1)


# =============================================================================
# INITIALIZATION STEPS
# =============================================================================
def step1_scan_admin_badge(nfc):
    """Step 1: Scan or enter the initial admin NFC badge UID."""
    print()
    print("[INIT] Step 1/7: Scan Initial Admin NFC badge")
    print("─" * 50)

    if nfc.connection:
        print("  Place your NFC badge on the reader...")
        print("  (Press Ctrl+C to cancel)")
        try:
            while True:
                uid = nfc.poll_for_card()
                if uid:
                    print(f"  Badge detected!")
                    print(f"[INIT] Admin badge UID: {uid}")
                    return uid
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\n  Scan cancelled.")
            sys.exit(0)
    else:
        print("  No NFC reader available — manual entry mode.")
        while True:
            uid = input("  Enter admin badge UID (hex): ").strip().lower()
            if uid and all(c in '0123456789abcdef' for c in uid):
                print(f"[INIT] Admin badge UID: {uid}")
                return uid
            print("  Invalid UID. Please enter a hex string (e.g., 0a2312c2).")


def step2_get_admin_credentials():
    """Step 2: Prompt for admin name and password."""
    print()
    print("[INIT] Step 2/7: Set admin name and password")
    print("─" * 50)

    while True:
        name = input("  Admin name: ").strip()
        if name:
            break
        print("  Name cannot be empty.")

    while True:
        password = input("  Admin password: ").strip()
        if password:
            break
        print("  Password cannot be empty.")

    print(f"[INIT] Admin name: {name}")
    return name, password


def step3_backup_database(db_cfg):
    """Step 3: Back up the existing database using pg_dump."""
    print()
    print("[BACKUP] Step 3/7: Backing up existing database")
    print("─" * 50)

    backup_dir = SCRIPT_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    print(f"  Backup directory: {backup_dir}")

    pg_dump = find_pg_dump()
    if not pg_dump:
        print("[BACKUP] WARNING: pg_dump not found — skipping backup.")
        print("  Install PostgreSQL client tools to enable backups.")
        return True

    print(f"  Using pg_dump: {pg_dump}")

    db_name = db_cfg.get('database')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"{db_name}_{timestamp}.sql"

    cmd = [
        pg_dump,
        "-h", db_cfg.get('host', 'localhost'),
        "-p", str(db_cfg.get('port', 5432)),
        "-U", db_cfg.get('user'),
        "-d", db_name,
        "-f", str(backup_file),
    ]

    env = {**os.environ, "PGPASSWORD": db_cfg.get('password', '')}

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "does not exist" in stderr:
                print(f"[BACKUP] Database '{db_name}' does not exist yet — no backup needed.")
            else:
                print()
                print("!" * 60)
                print("  WARNING: DATABASE EXISTS BUT BACKUP FAILED!")
                print(f"  pg_dump error: {stderr}")
                print("  Proceeding will DESTROY existing data with NO backup!")
                print("!" * 60)
                print()
            # Clean up empty backup file if created
            if backup_file.exists() and backup_file.stat().st_size == 0:
                backup_file.unlink()
            return True

        size = backup_file.stat().st_size
        size_str = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} bytes"
        print(f"[BACKUP] Backup saved: {backup_file}")
        print(f"  Size: {size_str}")
        return True

    except subprocess.TimeoutExpired:
        print()
        print("!" * 60)
        print("  WARNING: DATABASE EXISTS BUT BACKUP FAILED!")
        print("  pg_dump timed out after 60 seconds.")
        print("  Proceeding will DESTROY existing data with NO backup!")
        print("!" * 60)
        print()
        return True
    except Exception as e:
        print()
        print("!" * 60)
        print("  WARNING: DATABASE EXISTS BUT BACKUP FAILED!")
        print(f"  Error: {e}")
        print("  Proceeding will DESTROY existing data with NO backup!")
        print("!" * 60)
        print()
        return True


def step4_recreate_schema(conn, schema_path):
    """Step 4: Drop all tables and recreate from schema.sql (DDL only)."""
    print()
    print("[DB] Step 4/7: Recreating database schema")
    print("─" * 50)
    print(f"  Schema file: {schema_path}")

    if not schema_path.exists():
        print(f"[DB] ERROR: Schema file not found: {schema_path}")
        return False

    confirm = input("  This will DROP all existing tables and data. Type YES in upper case to confirm: ").strip()
    if confirm != "YES":
        print("[DB] Aborted — user did not confirm.")
        sys.exit(0)

    try:
        sql_text = schema_path.read_text(encoding='utf-8')
        ddl_sql = parse_schema_ddl(sql_text)

        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(ddl_sql)
        conn.autocommit = False

        print("[DB] Schema created successfully.")
        print("  Tables: hunters, wuzus, admins, scan_events")
        return True
    except Exception as e:
        print(f"[DB] ERROR: Schema creation failed: {e}")
        try:
            conn.rollback()
        except:
            pass
        return False


def step5_log_init_event(conn):
    """Step 5: Log a SYSTEM_INIT event in scan_events."""
    print()
    print("[DB] Step 5/7: Logging SYSTEM_INIT event")
    print("─" * 50)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO scan_events (event_type, details, private)
                   VALUES ('SYSTEM_INIT', %s, TRUE)""",
                (f"System initialized via wuzu_init.py at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",)
            )
        conn.commit()
        print("[DB] SYSTEM_INIT event logged.")
        return True
    except Exception as e:
        print(f"[DB] ERROR: Failed to log init event: {e}")
        conn.rollback()
        return False


def step6_insert_admin(conn, uid, name, password):
    """Step 6: Insert the initial admin into the admins table."""
    print()
    print("[ADMIN] Step 6/7: Creating initial admin account")
    print("─" * 50)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO admins (uid, name, password, created_by)
                   VALUES (%s, %s, %s, NULL)""",
                (uid, name, password)
            )
        conn.commit()
        print(f"[ADMIN] Admin '{name}' created (UID: {uid})")
        return True
    except Exception as e:
        print(f"[ADMIN] ERROR: Failed to create admin: {e}")
        conn.rollback()
        return False


def step7_import_wuzu_tags(conn, csv_path, default_points=10):
    """Step 7: Import wuzu tags from wuzu_tags.csv with random unique names and facts."""
    print()
    print("[IMPORT] Step 7/7: Importing wuzu tags from wuzu_tags.csv")
    print("─" * 50)
    print(f"  CSV file: {csv_path}")

    if not csv_path.exists():
        print(f"[IMPORT] ERROR: CSV file not found: {csv_path}")
        return 0

    # Read all EPCs first (need count for sampling)
    epcs = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            epcs.append(row['epc'].strip())

    # Read name and fact pools
    names_path = SCRIPT_DIR / "names.csv"
    facts_path = SCRIPT_DIR / "facts.csv"

    if not names_path.exists():
        print(f"[IMPORT] ERROR: Names file not found: {names_path}")
        return 0
    if not facts_path.exists():
        print(f"[IMPORT] ERROR: Facts file not found: {facts_path}")
        return 0

    with open(names_path, 'r', encoding='utf-8') as f:
        names_pool = [line.strip() for line in f if line.strip()]
    with open(facts_path, 'r', encoding='utf-8') as f:
        facts_pool = [line.strip() for line in f if line.strip()]

    print(f"  Tags: {len(epcs)}, Names available: {len(names_pool)}, Facts available: {len(facts_pool)}")

    if len(names_pool) < len(epcs):
        print(f"[IMPORT] ERROR: Not enough names ({len(names_pool)}) for {len(epcs)} tags")
        return 0
    if len(facts_pool) < len(epcs):
        print(f"[IMPORT] ERROR: Not enough facts ({len(facts_pool)}) for {len(epcs)} tags")
        return 0

    # Sample without replacement — no duplicates
    chosen_names = random.sample(names_pool, len(epcs))
    chosen_facts = random.sample(facts_pool, len(epcs))

    count = 0
    try:
        with conn.cursor() as cur:
            for epc, name, fact in zip(epcs, chosen_names, chosen_facts):
                cur.execute(
                    """INSERT INTO wuzus (epc, name, fact, points_value)
                       VALUES (%s, %s, %s, %s)""",
                    (epc, name, fact, default_points)
                )
                count += 1
        conn.commit()
        print(f"[IMPORT] Imported {count} wuzu tags with unique names and facts")
        return count
    except Exception as e:
        print(f"[IMPORT] ERROR: Failed to import tags: {e}")
        conn.rollback()
        return 0


# =============================================================================
# MAIN
# =============================================================================
def main():
    print()
    print("=" * 60)
    print("  WUZU SCANNER — System Initialization")
    print("=" * 60)

    # Load config
    config_path = SCRIPT_DIR / "config.toml"
    print(f"\n[INIT] Config: {config_path}")
    config = load_config(str(config_path))
    db_cfg = config['database']
    print(f"[INIT] Database: {db_cfg['database']} @ {db_cfg['host']}:{db_cfg.get('port', 5432)}")

    # Step 1: Scan admin badge
    nfc = NFCReader()
    uid = step1_scan_admin_badge(nfc)

    # Step 2: Admin credentials
    name, password = step2_get_admin_credentials()

    # Step 3: Backup existing database
    step3_backup_database(db_cfg)

    # Step 4: Recreate schema (requires confirmation)
    conn = get_db_connection(db_cfg)
    schema_path = SCRIPT_DIR / "schema.sql"
    if not step4_recreate_schema(conn, schema_path):
        print("\n[INIT] FATAL: Schema creation failed. Aborting.")
        conn.close()
        sys.exit(1)

    # Step 5: Log init event
    if not step5_log_init_event(conn):
        print("\n[INIT] WARNING: Could not log init event. Continuing...")

    # Step 6: Insert admin
    if not step6_insert_admin(conn, uid, name, password):
        print("\n[INIT] FATAL: Could not create admin. Aborting.")
        conn.close()
        sys.exit(1)

    # Step 7: Import wuzu tags
    csv_path = SCRIPT_DIR / "wuzu_tags.csv"
    default_points = config.get('scoring', {}).get('default_points', 10)
    count = step7_import_wuzu_tags(conn, csv_path, default_points)

    # Done
    conn.close()
    print()
    print("=" * 60)
    print("  INITIALIZATION COMPLETE")
    print(f"  Admin: {name} (UID: {uid})")
    print(f"  Wuzus: {count} tags imported")
    print(f"  Database: {db_cfg['database']}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INIT] Aborted by user.")
        sys.exit(0)
