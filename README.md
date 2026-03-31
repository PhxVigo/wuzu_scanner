# Wuzu Scanner - Cyberpunk RFID Hunt Game

A terminal-based RFID hunting game using NFC badges for player identification and UHF RFID tags for collectible "wuzus".

## Features

- **NFC Badge Authentication**: Players scan their badge to start hunting
- **UHF RFID Scanning**: Hunt for tagged objects in the environment (serial or keyboard wedge)
- **Real-time Leaderboard**: PostgreSQL-backed scoreboard
- **Admin Mode**: Score management, wuzu editing, event auditing via admin badge
- **Event Logging**: Complete history of all scans and scores with soft-delete
- **Database Status Monitoring**: Real-time connection status display
  - `LOCAL` - Connected to localhost database
  - `REMOTE` - Connected to remote database
  - `OFFLINE` - Database unavailable (demo mode)
- **Screen Saver**: Auto-activates after idle timeout
- **Configurable**: Extensive TOML-based configuration

## Hardware Requirements

- **NFC Reader**: PC/SC compatible reader (e.g., ACR122U) for player badges
- **UHF RFID Reader**: Either:
  - Serial-connected UHF reader (e.g., GeeNFC UHF reader, UR-2000)
  - USB keyboard-wedge UHF scanner
- **NFC Tags**: ISO14443A tags for player badges
- **UHF Tags**: EPC Gen2 tags for wuzus

## Software Requirements

- Python 3.8+
- PostgreSQL 12+
- PostgreSQL client tools (`pg_dump`) - needed for database backup during initialization
- Python packages:
  - `psycopg2-binary` - PostgreSQL adapter
  - `pyserial` - Serial communication for UHF reader
  - `pyscard` - Smart card/NFC reader support
  - `tomli` (Python < 3.11) - TOML configuration parser

## Installation

### 0. Download Repo

  ```bash
  wget https://github.com/PhxVigo/wuzu_scanner/archive/refs/heads/main.zip
  unzip main.zip
  mv wuzu_scanner-main wuzu_scanner
  cd wuzu_scanner
  ```

### 1. Install System Dependencies

**Windows:**
- Install [PostgreSQL](https://www.postgresql.org/download/windows/) (includes client tools and `pg_dump`)
- Alternatively, install just the command line tools if you only need `pg_dump` for backups

**Linux (Debian/Ubuntu):**
```bash
sudo apt update
sudo apt install python3 python3-pip postgresql postgresql-contrib postgresql-client pcscd libpcsclite-dev
sudo systemctl start postgresql
sudo systemctl enable postgresql
sudo systemctl start pcscd
sudo systemctl enable pcscd
```

We may need to make sure kernel service doesn;t grab our NFC reader.
```bash
sudo bash -c 'echo "blacklist pn533_usb
blacklist pn533
blacklist nfc" > /etc/modprobe.d/blacklist-nfc.conf'
sudo modprobe -r pn533_usb pn533 nfc 2>/dev/null
sudo systemctl start pcscd
```

Make sure your user has acccess to the serial ports (replace <your_user> with your login)
```bash
sudo usermod -aG dialout <your_user>
newgrp dialout
```

### 2. Install Python Dependencies

```bash
pip install psycopg2-binary pyserial pyscard --break-system-packages

# For Python < 3.11, also install tomli
pip install tomli --break-system-packages
```

### 3. Set Up Database

```bash
# Create database and user
sudo -u postgres createdb wuzu-1
sudo -u postgres createuser wuzu_user -P
# (Enter password when prompted)

# Grant privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE \"wuzu-1\" TO wuzu_user;"
```

### 4. Configure Application

```bash
# Copy the example config and edit with your settings
cp example-config.toml config.toml
nano config.toml
```

> **Note:** `config.toml` is gitignored because it contains your database credentials. Never commit it. Always start from `example-config.toml`.

**Important config items to set:**
- `database.host` - Database server address (Try "localhost")
- `database.database` - Your database name (Try "wuzu-1")
- `database.user` - Your database user (Try "wuzu_user")
- `database.password` - Your database user password

### 4. Connect Hardware

- Plug in NFC reader
- Plug in UHF reader

### 5. Detect Hardware

```bash
python3 detect_scanners.py
```

Auto-detects NFC readers, serial UHF readers, and keyboard wedge scanners. Offers to update `config.toml` with detected hardware settings.
If it can not autodetect, troubleshoot and manually enter settings in config.toml
- `hardware.uhf_type` - `"serial"` or `"keyboard"` for your UHF reader type
- `hardware.uhf_port` - Your UHF reader's serial port (if using serial)
- `hardware.uhf_baudrate` - Your UHF reader's serial speed (if using serial)

### 6. Initialize System

```bash
python3 wuzu_init.py
```

Interactive setup that:
1. Scans your admin NFC badge (or enter UID manually)
2. Sets admin name and password
3. Backs up existing database (using `pg_dump`)
4. Recreates the database schema from `schema.sql`
5. Imports wuzu tags from `wuzu_tags.csv`, assigning random names from `names.csv` and facts from `facts.csv`

## CSV Data Files

These files are used during system initialization (`wuzu_init.py`):

| File | Description |
|------|-------------|
| `wuzu_tags.csv` | UHF tag inventory with EPC codes. Each row contains an EPC, batch ID, sequence number, and timestamp. Imported into the `wuzus` database table. |
| `names.csv` | Pool of wuzu names (one per line). Randomly assigned to wuzus during import so each tag gets a unique name. |
| `facts.csv` | Pool of cyberpunk fun facts (one per line). Randomly assigned to wuzus during import so each tag gets a unique fact. |

## Running the Application

```bash
python3 wuzu_scanner.py
```

On startup, you should see:
```
[NFC] Using: ACS ACR122U PICC Interface 00 00
[UHF] Opened COM9
[DB] Connected to wuzu-1 at localhost:5432
[DB] Connection test successful
[DB] Status: LOCAL
[DB] PostgreSQL 14.5
Starting application...
```

The status bar at the top shows:
- **DB:LOCAL** / **DB:REMOTE** / **DB:OFFLINE** - Database connection status
- **UPTIME** - How long the application has been running
- **LAST-SCAN** - Time of most recent scan event
- **TIME** - Current system time

## Usage

### Main Screen
- **[A]** - Add new hunter (register a new player badge)
- **[R]** - Redraw screen
- **Scan hunter badge** - Starts a hunting session
- **Scan admin badge** - Enters admin mode

If an unregistered badge is scanned, you are prompted to register it as a new hunter (**Y/N**).

### Adding Hunters
1. Press **A**
2. Scan the player's NFC badge
3. Type their name and press Enter

### Hunting
1. Hunter scans their badge on main screen
2. Hunt for wuzus with the UHF reader
3. Each new wuzu found adds points
4. Session ends after 5 seconds of no new finds (configurable)

### Admin Mode
1. Scan an admin NFC badge on the main screen
2. Enter admin password when prompted
3. Admin commands:
   - **[W]** - Add new wuzu (register UHF tag)
   - **[E]** - Edit wuzu (name, points, fact, or delete)
   - **[A]** - Add new admin
   - **[Q]** - Quit application
   - **[X]** - Exit admin mode
   - **Scan hunter badge** - View and manage their event history

## Configuration Reference

### Database Settings
```toml
[database]
host = "localhost"          # Database server (determines LOCAL vs REMOTE status)
port = 5432                 # PostgreSQL port
database = "wuzu-1"         # Database name
user = "postgres"           # Username
password = "your_password"  # Password
```

### Hardware Settings
```toml
[hardware]
uhf_type = "serial"         # "serial" for UR-2000, "keyboard" for USB keyboard wedge
uhf_port = "COM9"           # Serial port for UHF reader
uhf_baudrate = 57600        # Usually 57600 or 115200
uhf_power = 20              # RF power 0-30 dBm
```

### Timing Settings
```toml
[timing]
scan_timeout = 5            # Inactivity timeout before hunt ends (seconds)
results_display = 10        # Results screen duration (seconds)
scan_interval = 0.2         # UHF inventory scan interval (seconds)
nfc_poll_interval = 0.05    # NFC poll interval (seconds)
leaderboard_refresh = 60    # Leaderboard refresh rate (seconds)
idle_timeout = 30           # Seconds before screen saver activates
screensaver_interval = 5    # Screen saver text movement interval (seconds)
admin_timeout = 30          # Admin screen idle timeout (seconds)
unknown_tag_timeout = 10    # Unknown tag prompt auto-cancel (seconds)
```

### Audio Settings
```toml
[audio]
beep_enabled = true

[audio.beeps]
# Format: [duration, pause, times]
# Duration/pause in 100ms units
new_wuzu = [1, 0, 1]        # Quick beep on wuzu found
hunter_id = [2, 1, 2]       # Double beep on badge scan
complete = [3, 2, 3]        # Triple beep on session end
```

### Scoring Settings
```toml
[scoring]
default_points = 10         # Points assigned to new wuzus
```

### Display Settings
```toml
[display]
border_char = "─"                    # Character used for borders
main_title = "WUZUScan-76 v1.09b"   # Title displayed in various screens
```

## Troubleshooting

### NFC Reader Not Found
```bash
# Check if PC/SC daemon is running
sudo systemctl status pcscd

# List connected readers
pcsc_scan
```

### UHF Reader Not Connecting
```bash
# List serial ports (Linux)
ls -l /dev/ttyUSB*

# List serial ports (Windows)
# Check Device Manager > Ports (COM & LPT)

# Test serial connection
python3 -c "import serial; print(serial.tools.list_ports.comports())"
```

### Database Connection Failed
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection manually
psql -h localhost -U postgres -d wuzu-1

# Check credentials in config.toml match database
```

### Permission Denied on Serial Port
```bash
# Add user to dialout group (Linux)
sudo usermod -a -G dialout $USER
# Log out and back in for changes to take effect
```

## Database Schema

### Tables
- **hunters** - Player profiles and scores
- **wuzus** - Tagged objects, names, facts, and point values
- **admins** - Admin accounts with password authentication
- **scan_events** - Complete event log with soft-delete and audit trail

### Useful Queries

```sql
-- View leaderboard
SELECT name, points, last_seen 
FROM hunters 
ORDER BY points DESC;

-- Recent activity
SELECT timestamp, event_type, details 
FROM scan_events 
WHERE NOT deleted AND NOT private
ORDER BY timestamp DESC 
LIMIT 20;

-- Most popular wuzus
SELECT name, epc, times_found 
FROM wuzus 
WHERE NOT deleted
ORDER BY times_found DESC;
```

## Development

### Project Structure
```
wuzu_scanner/
├── wuzu_scanner.py             # Main application
├── wuzu_init.py                # System initialization script
├── detect_scanners.py          # Hardware auto-detection tool
├── schema.sql                  # Database schema (4 tables)
├── example-config.toml         # Example configuration (copy to config.toml)
├── wuzu_tags.csv               # UHF tag inventory for import
├── names.csv                   # Wuzu names for random assignment
├── facts.csv                   # Cyberpunk fun facts for wuzus
├── GUIDE.md                    # Usage guide and quick reference
├── README.md                   # This file
├── CHANGELOG.md                # Change history
├── CHANGELOG_keyboard_wedge.md # Keyboard wedge feature changelog
└── backups/                    # Database backups (created by wuzu_init.py)
```

### Screen Architecture
The application uses a screen-based architecture:
- `Screen` - Base class for all screens
- `StartScreen` - Main leaderboard view
- `ScreenSaverScreen` - Idle screen saver animation
- `AddHunterScreen` - Register new players
- `AdminScreen` - Admin mode (history, wuzu editing, admin management)
- `AddWuzuScreen` - Register new tags
- `ScanWuzuScreen` - Active hunting session
- `ResultsScreen` - Post-hunt summary

## License

MIT License - Feel free to modify and distribute

## Support

For issues and questions:
1. Check the `GUIDE.md` for keyboard commands and quick reference
2. Check the troubleshooting section above
3. Verify hardware connections
4. Test database connectivity
5. Review logs for error messages
