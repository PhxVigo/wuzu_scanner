# Wuzu Scanner

A terminal-based RFID hunting game using NFC badges for player identification and UHF RFID tags for collectible "wuzus".

## Features

- **NFC Badge Authentication**: Players scan their badge to start hunting
- **UHF RFID Scanning**: Hunt for tagged objects in the environment
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
- **UHF RFID Reader**: One of:
  - GeeNFC UR-2000 (serial/COM port)
  - Yanzeo SR3308 (USB HID — auto-detected, no serial port needed)
- **NFC Tags**: ISO14443A tags for player badges
- **UHF Tags**: EPC Gen2 tags for wuzus

## Software Requirements

- Python 3.8+
- PostgreSQL 12+
- PostgreSQL client tools (`pg_dump`) - needed for database backup during initialization
- Python packages:
  - `psycopg2-binary` - PostgreSQL adapter
  - `pyserial` - Serial communication for UHF reader (UR-2000)
  - `hidapi` - USB HID communication for UHF reader (SR3308)
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
sudo apt install python3 python3-pip postgresql postgresql-contrib postgresql-client pcscd libpcsclite-dev libhidapi-dev
sudo systemctl start postgresql
sudo systemctl enable postgresql
sudo systemctl start pcscd
sudo systemctl enable pcscd
```

We may need to make sure kernel service doesn't grab our NFC reader.
```bash
sudo bash -c 'echo "blacklist pn533_usb
blacklist pn533
blacklist nfc" > /etc/modprobe.d/blacklist-nfc.conf'
sudo modprobe -r pn533_usb pn533 nfc 2>/dev/null
sudo systemctl start pcscd
```

Make sure your user has access to serial ports and HID devices (replace <your_user> with your login)
```bash
sudo usermod -aG dialout,input <your_user>
newgrp dialout
```

If using a **Yanzeo SR3308** UHF reader, set up udev rules so it works without sudo:
```bash
cat <<'EOF' | sudo tee /etc/udev/rules.d/99-sr3308.rules
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="04d8", ATTRS{idProduct}=="033f", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="04d8", ATTRS{idProduct}=="033f", MODE="0666"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 2. Install Python Dependencies

```bash
pip install psycopg2-binary pyserial pyscard hidapi --break-system-packages

# For Python < 3.11, also install tomli
pip install tomli --break-system-packages
```

### 3. Set Up Database

```bash
# Create database and user
sudo -u postgres createdb wuzu
sudo -u postgres createuser wuzu -P
# (Enter password when prompted)

# Grant privileges
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE \"wuzu\" TO wuzu;"
sudo -u postgres psql "wuzu" -c "GRANT ALL ON SCHEMA public TO wuzu;"
```

### 4. Configure Application

```bash
# Copy the example config and edit with your settings
cp example-config.toml config.toml
nano config.toml
```

> **Note:** `config.toml` is gitignored because it contains your database credentials. Never commit it. Always start from `example-config.toml`.

**Important config items to set:**
- `database.host` - Database server address ("localhost" probably)
- `database.database` - Your database name ("wuzu" default)
- `database.user` - Your database username ("wuzu" default)
- `database.password` - Your database uer's password (You set this in step 3)

### 4. Connect Hardware

- Plug in NFC reader
- Plug in UHF reader

### 5. Detect Hardware

```bash
python3 detect_scanners.py
```

Auto-detects NFC readers and UHF readers (both serial UR-2000 and USB HID SR3308). If an SR3308 is found with its keyboard interface active, offers to disable it. Updates `config.toml` with detected hardware settings.

### 7. Initialize System

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

These files are used during system initialization (`wuzu_init.py`).
They are not actually comma seperated, but one entry per line.

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
[DB] Connected to wuzu at localhost:5432
[DB] Connection test successful
[DB] Status: LOCAL
[DB] PostgreSQL 14.5
Starting application...
```

The status bar at the bottom shows:
- **DB:LOCAL** / **DB:REMOTE** / **DB:OFFLINE** - Database connection status
- **UPTIME** - How long the application has been running
- **TIME** - Current system time

## Troubleshooting

### NFC Reader Not Found
```bash
# Check if PC/SC daemon is running
sudo systemctl status pcscd

# List connected readers
pcsc_scan
```

### UHF Reader Not Connecting (UR-2000, serial)
```bash
# List serial ports (Linux)
ls -l /dev/ttyUSB*

# List serial ports (Windows)
# Check Device Manager > Ports (COM & LPT)

# Test serial connection
python3 -c "import serial; print(serial.tools.list_ports.comports())"
```

### UHF Reader Not Connecting (SR3308, USB HID)
```bash
# Check if the device is visible on USB
lsusb | grep 04d8:033f

# Check HID devices
ls /dev/hidraw*

# Run the diagnostic test
sudo python3 test_sr3308.py

# If the reader is typing characters into your terminal,
# run detect_scanners.py and choose to disable the keyboard interface
```

### Database Connection Failed
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection manually
psql -h localhost -U wuzu -d wuzu

# Check credentials in config.toml match database
```

### Permission Denied on Serial Port
```bash
# Add user to dialout group (Linux)
sudo usermod -a -G dialout $USER
# Log out and back in for changes to take effect
```
