# Wuzu Scanner - Guide

## Status Bar Indicators

```
┌ DB:LOCAL | UPTIME:00:05:23 | LAST-SCAN:14:23:45 | TIME:14:30:12 ───┐
   ↑            ↑                  ↑                     ↑
   │            │                  │                     │
   │            │                  │                     └─ Current time
   │            │                  └─────────────────────── Last scan event
   │            └────────────────────────────────────────── System uptime
   └─────────────────────────────────────────────────────── Database status
```

### Database Status

| Status | Meaning | What to Do |
|--------|---------|------------|
| **DB:LOCAL** | Connected to local database (127.0.0.1) | Everything working normally |
| **DB:REMOTE** | Connected to remote database server | Everything working, using remote DB |
| **DB:OFFLINE** | Database unavailable | Limited functionality - check database |

## Keyboard Commands

### Main Screen
| Key | Action |
|-----|--------|
| **A** | Add new hunter (register player badge) |
| **R** | Redraw/refresh screen |
| **Scan hunter badge** | Start hunting session |
| **Scan admin badge** | Enter admin mode (password required) |

If an unregistered badge is scanned, you are prompted to add a new hunter:
- **Y** or **Enter** - Register the badge as a new hunter
- **N** or **X** - Dismiss (auto-cancels after 10 seconds)

### During Hunt
| Key | Action |
|-----|--------|
| **X** | Exit hunting session early |

### Results Screen
| Key | Action |
|-----|--------|
| **X** | Return to main screen immediately |

### Admin Screen
Scan an admin NFC badge on the main screen to enter. Password is required on first access per session.

| Key | Action |
|-----|--------|
| **W** | Add new wuzu (register UHF tag) |
| **E** | Edit wuzu (scan tag to select) |
| **A** | Add new admin (scan badge, set name & password) |
| **Q** | Quit application (with confirmation) |
| **X** | Exit admin mode (return to main screen) |
| **Scan hunter badge** | View hunter's event history |

### Hunter History (within Admin)
| Key | Action |
|-----|--------|
| **J** or **2** | Move selection down |
| **K** or **8** | Move selection up |
| **D** | Delete selected SCORE event (with confirmation) |
| **M** | Adjust hunter score (enter positive or negative number) |
| **X** | Back to admin menu |

### Edit Wuzu (within Admin)
| Key | Action |
|-----|--------|
| **N** | Edit name |
| **P** | Edit points value |
| **F** | Edit fact |
| **D** | Delete wuzu (soft delete, with confirmation) |
| **X** | Back to admin menu |

## Screen Saver

Activates after `idle_timeout` seconds of inactivity on the main screen (default: 30 seconds). Any badge scan or keypress returns to the main screen.

## Admin Timeout

The admin screen automatically returns to the main screen after `admin_timeout` seconds of inactivity (default: 30 seconds).

## Startup Checklist

1. Copy `example-config.toml` to `config.toml` if you haven't already
2. Hardware connected (NFC reader + UHF reader)
3. PostgreSQL running (`sudo systemctl status postgresql`)
4. Database credentials set in `config.toml`
5. Serial UHF: correct port in `config.toml` (`COM9`, `/dev/ttyUSB0`, etc.)

**Expected startup output:**
```
[NFC] Using: ACS ACR122U PICC Interface 00 00
[UHF] Opened COM9
[DB] Connected to wuzu-1 at localhost:5432
[DB] Connection test successful
[DB] Status: LOCAL
[DB] PostgreSQL 14.5
Starting application...
```

## Troubleshooting

### DB:OFFLINE appears
1. Check PostgreSQL is running
2. Verify credentials in `config.toml`
3. Test manually: `psql -h localhost -U postgres wuzu-1`

### NFC reader not found
1. Check USB connection
2. Verify PC/SC daemon: `sudo systemctl status pcscd`
3. List readers: `pcsc_scan`

### UHF reader not connecting
1. Check USB/serial connection
2. Verify port in `config.toml` matches device
3. Linux: check permissions `sudo usermod -a -G dialout $USER`

## Points System

- Each unique wuzu found awards points (default: 10, set via `default_points` in `[scoring]`)
- Points per wuzu can be individually changed via admin Edit Wuzu
- Hunting session ends after `scan_timeout` seconds of no new finds (default: 5)
- Results display for `results_display` seconds (default: 10)

## Game Flow

```
Main Screen ──[Scan Hunter Badge]──> Hunting Mode ──> Results ──> Main Screen
     │                                    │
     ├── [A] Add Hunter                   └── Find Wuzus!
     ├── [Scan Admin Badge] ──> Admin Screen
     └── (idle) ──> Screen Saver ──(any input)──> Main Screen
```

## Database Schema

| Table | Description |
|-------|-------------|
| **hunters** | Player profiles (uid, name, points, created_at, last_seen) |
| **wuzus** | Tagged objects (epc, name, fact, points_value, times_found, deleted) |
| **admins** | Admin accounts (uid, name, password, created_at, created_by) |
| **scan_events** | Event log (timestamp, event_type, hunter_uid, wuzu_epc, details, points_awarded, deleted, deleted_by, admin_uid, private) |

## Utility Scripts

| Script | Purpose |
|--------|---------|
| `detect_scanners.py` | Auto-detects NFC readers and serial UHF readers. Offers to update `config.toml`. |
| `wuzu_init.py` | System initialization: sets up admin badge, backs up & recreates database, imports wuzu tags from CSV with random names and facts. |

## CSV Data Files

| File | Contents |
|------|----------|
| `wuzu_tags.csv` | UHF tag inventory (EPCs to import during initialization) |
| `names.csv` | Pool of wuzu names, randomly assigned during initialization |
| `facts.csv` | Pool of cyberpunk fun facts, randomly assigned during initialization |

## Configuration Quick Reference

Copy `example-config.toml` to `config.toml` and edit with your settings. `config.toml` is gitignored — never commit it.

```toml
[database]
host = "localhost"          # Database server (determines LOCAL vs REMOTE)
port = 5432
database = "wuzu-1"         # Database name
user = "postgres"
password = "your_password"

[hardware]
uhf_port = "COM9"           # Windows: COMx, Linux: /dev/ttyUSBx
uhf_baudrate = 57600        # Usually 57600 or 115200
uhf_power = 20              # RF power 0-30 dBm

[timing]
scan_timeout = 5            # Seconds before hunt ends (no new finds)
results_display = 10        # Seconds to show results
scan_interval = 0.2         # UHF inventory scan interval
nfc_poll_interval = 0.05    # NFC poll interval
leaderboard_refresh = 60    # Seconds between DB refreshes
idle_timeout = 30           # Seconds before screen saver activates
screensaver_interval = 5    # Screen saver text movement interval
admin_timeout = 30          # Admin screen idle timeout
unknown_tag_timeout = 10    # Unknown tag prompt auto-cancel

[audio]
beep_enabled = true

[audio.beeps]
new_wuzu = [1, 0, 1]       # Quick beep on wuzu found
hunter_id = [2, 1, 2]      # Double beep on badge scan
complete = [3, 2, 3]        # Triple beep on session end

[scoring]
default_points = 10         # Points assigned to new wuzus

[display]
border_char = "─"
main_title = "WUZUScan-76 v1.09b"
```

## Support

- Full documentation: See `README.md`
- Recent changes: See `CHANGELOG.md`

---
**Remember:** The database status updates automatically every 30 seconds!
