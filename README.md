# Wuzu Scanner - Cyberpunk RFID Hunt Game

A terminal-based RFID hunting game using NFC badges for player identification and UHF RFID tags for collectible "wuzus".

## Features

- **NFC Badge Authentication**: Players scan their badge to start hunting
- **UHF RFID Scanning**: Hunt for tagged objects in the environment
- **Real-time Leaderboard**: PostgreSQL-backed scoreboard
- **Event Logging**: Complete history of all scans and scores
- **Database Status Monitoring**: Real-time connection status display
  - `LOCAL` - Connected to localhost database
  - `REMOTE` - Connected to remote database
  - `OFFLINE` - Database unavailable (demo mode)
- **Configurable**: Extensive TOML-based configuration

## Hardware Requirements

- **NFC Reader**: PC/SC compatible reader (e.g., ACR122U) for player badges
- **UHF RFID Reader**: Serial-connected UHF reader (e.g., GeeNFC UHF reader)
- **NFC Tags**: ISO14443A tags for player badges
- **UHF Tags**: EPC Gen2 tags for wuzus

## Software Requirements

- Python 3.8+
- PostgreSQL 12+
- Python packages:
  - `psycopg2-binary` - PostgreSQL adapter
  - `pyserial` - Serial communication for UHF reader
  - `pyscard` - Smart card/NFC reader support
  - `tomli` (Python < 3.11) - TOML configuration parser

## Installation

### 1. Install System Dependencies

**Linux (Debian/Ubuntu):**
```bash
sudo apt update
sudo apt install python3 python3-pip postgresql postgresql-contrib pcscd libpcsclite-dev
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Raspberry Pi:**
```bash
sudo apt install python3-pip postgresql pcscd libpcsclite-dev
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
sudo -u postgres createdb wuzu_game
sudo -u postgres createuser wuzu_user -P
# (Enter password when prompted)

# Grant privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE wuzu_game TO wuzu_user;"

# Load schema
sudo -u postgres psql wuzu_game < schema.sql

# Verify tables were created
sudo -u postgres psql wuzu_game -c "\dt"
```

### 4. Configure Application

```bash
# Copy example config
cp config.toml.example config.toml

# Edit config with your settings
nano config.toml
```

**Important config items to set:**
- `database.password` - Your PostgreSQL password
- `hardware.uhf_port` - Your UHF reader's serial port

### 5. Connect Hardware

- Plug in NFC reader (should auto-detect via PC/SC)
- Plug in UHF reader (note the serial port)
- Update `uhf_port` in config.toml

## Running the Application

```bash
python3 wuzu_scanner_db.py
```

On startup, you should see:
```
[NFC] Using: ACS ACR122U PICC Interface 00 00
[UHF] Opened COM9
[DB] Connected to wuzu_game at localhost:5432
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
- **[W]** - Add new wuzu (register a new UHF tag)
- **[Q]** - Quit application
- **[R]** - Redraw screen
- **Scan Badge** - Hunter badge starts a hunting session

### Adding Hunters
1. Press **A**
2. Scan the player's NFC badge
3. Type their name and press Enter

### Adding Wuzus
1. Press **W**
2. Hold a UHF tag near the reader
3. Tag is automatically registered

### Hunting
1. Hunter scans their badge on main screen
2. Hunt for wuzus with the UHF reader
3. Each new wuzu found adds points
4. Session ends after 5 seconds of no new finds (configurable)

## Configuration Reference

### Database Settings
```toml
[database]
host = "localhost"          # Database server
port = 5432                 # PostgreSQL port
database = "wuzu_game"      # Database name
user = "wuzu_user"          # Username
password = "your_password"  # Password
```

### Hardware Settings
```toml
[hardware]
uhf_port = "COM9"           # Serial port for UHF reader
uhf_baudrate = 57600        # Usually 57600 or 115200
uhf_power = 20              # RF power 0-30 dBm
```

### Timing Settings
```toml
[timing]
scan_timeout = 5            # Inactivity timeout (seconds)
results_display = 10        # Results screen duration (seconds)
leaderboard_refresh = 60    # Leaderboard refresh rate (seconds)
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
psql -h localhost -U wuzu_user -d wuzu_game

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
- **wuzus** - Tagged objects and their values
- **scan_events** - Complete event log

### Useful Queries

```sql
-- View leaderboard
SELECT name, points, last_seen 
FROM hunters 
ORDER BY points DESC;

-- Recent activity
SELECT timestamp, event_type, details 
FROM scan_events 
ORDER BY timestamp DESC 
LIMIT 20;

-- Most popular wuzus
SELECT epc, times_found 
FROM wuzus 
ORDER BY times_found DESC;
```

## Development

### Project Structure
```
wuzu_scanner/
├── wuzu_scanner_db.py      # Main application
├── schema.sql              # Database schema
├── config.toml             # Your configuration
├── config.toml.example     # Example configuration
└── README.md               # This file
```

### Adding Features
The application uses a screen-based architecture:
- `Screen` - Base class for all screens
- `StartScreen` - Main leaderboard view
- `AddHunterScreen` - Register new players
- `AddWuzuScreen` - Register new tags
- `ScanWuzuScreen` - Active hunting session
- `ResultsScreen` - Post-hunt summary

## License

MIT License - Feel free to modify and distribute

## Support

For issues and questions:
1. Check the troubleshooting section
2. Verify hardware connections
3. Test database connectivity
4. Review logs for error messages
