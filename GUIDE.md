# Wuzu Scanner - Guide

## Status Bar Indicators

```
┌ DB:LOCAL | UPTIME:00:05:23 | TIME:14:30:12 ───┐
   ↑            ↑                    ↑
   │            │                    │
   │            │                    └─ Current time
   │            └────────────────────── System uptime
   └─────────────────────────────────── Database status
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
- **N** or **X** - Dismiss (auto-cancels after `unknown_tag_timeout` seconds)

### During Hunt
| Key | Action |
|-----|--------|
| **X** | Exit hunting session early |
| **R** | Redraw/refresh screen |

### Results Screen
| Key | Action |
|-----|--------|
| **X** | Return to main screen immediately |
| **R** | Redraw/refresh screen |

Auto-returns to main screen after `results_display` seconds.

### Admin Screen
Scan an admin NFC badge on the main screen to enter. Password is required on first access per session.

| Key | Action |
|-----|--------|
| **W** | Add new wuzu (register UHF tag) |
| **E** | Edit wuzu (scan tag to select) |
| **H** | Edit hunter (scan badge to select) |
| **A** | Add new admin (scan badge, set name & password) |
| **O** | Override scan (scan hunter badge, then force-score wuzus) |
| **S** | Scan-out mode (scan wuzus to mark them as scanned out) |
| **Q** | Quit application (with confirmation) |
| **X** | Exit admin mode (return to main screen) |
| **R** | Redraw/refresh screen |

### Edit Hunter (within Admin)
Scan a hunter badge to select. Shows the hunter's scan history panel.

| Key | Action |
|-----|--------|
| **N** | Edit hunter name |
| **M** | Adjust hunter score (enter positive or negative number) |
| **J** or **2** | Move selection down in scan history |
| **K** or **8** | Move selection up in scan history |
| **X** | Back to admin menu |

### Edit Wuzu (within Admin)
Scan a wuzu UHF tag to select. Shows the wuzu's scan history panel.

| Key | Action |
|-----|--------|
| **N** | Edit name |
| **P** | Edit points value |
| **F** | Edit fact |
| **D** | Delete wuzu (soft delete, with confirmation) |
| **J** or **2** | Move selection down in scan history |
| **K** or **8** | Move selection up in scan history |
| **X** | Back to admin menu |

### Admin Override Scan
Select **O** from the admin menu, then scan a hunter badge to target. All wuzus scanned in this mode score immediately, bypassing cooldown and scan-out validation. Unregistered wuzus score with `default_points` but are not registered. Logged as `OVERRIDE_SCORE` events.

### Admin Scan-Out
Select **S** from the admin menu, then scan wuzus to mark them as "scanned out". This clears them for re-scoring by hunters (when `scan_out` is enabled in config). Logged as `SCAN_OUT` events.

## Screen Saver

Activates after `idle_timeout` seconds of inactivity on the main screen (default: 30 seconds). Any badge scan or keypress returns to the main screen.

## Admin Timeout

The admin screen automatically returns to the main screen after `admin_timeout` seconds of inactivity (default: 30 seconds).

## Points System & Scan Validation

### Basic Scoring
- Each unique wuzu found awards points (default: 10, set via `default_points` in `[scoring]`)
- Points per wuzu can be individually changed via admin Edit Wuzu
- Hunting session ends after `scan_timeout` seconds of no new finds (default: 5)
- Results display for `results_display` seconds (default: 10)

### Re-scoring Rules
The `[scoring]` config section controls when a previously-found wuzu can be scored again:

| Setting | Effect |
|---------|--------|
| `cooldown_minutes` | Minutes before same wuzu can be re-scored (0 = no cooldown) |
| `scan_out` | Require the wuzu to be scanned out by an admin before re-scoring |
| `cooldown_overrides_scan_out` | Allow expired cooldown to substitute for a missing scan-out |

**Common configurations:**

| Mode | Settings | Behavior |
|------|----------|----------|
| **Free play** | `scan_out=false`, `cooldown=0` | Everything scores freely, no restrictions |
| **Cooldown only** | `scan_out=false`, `cooldown>0` | Must wait cooldown before re-scoring; valid scan-out overrides the wait |
| **Scan-out only** | `scan_out=true`, `cooldown_overrides_scan_out=false` | Admin must scan out wuzu before it can be re-scored |
| **Hybrid** | `scan_out=true`, `cooldown_overrides_scan_out=true`, `cooldown>0` | Scan-out required, but expired cooldown can substitute |

Wuzus that fail validation are logged as `REJECTED` (not shown to the hunter).

## Game Flow

```
Main Screen ──[Scan Hunter Badge]──> Hunting Mode ──> Results ──> Main Screen
     │                                    │
     ├── [A] Add Hunter                   └── Find Wuzus!
     ├── [Scan Admin Badge] ──> Admin Screen
     │        ├── [W] Add Wuzu
     │        ├── [E] Edit Wuzu
     │        ├── [H] Edit Hunter
     │        ├── [A] Add Admin
     │        ├── [O] Override Scan ──> Select Hunter ──> Force-score Wuzus
     │        └── [S] Scan-Out ──> Mark Wuzus as Scanned Out
     └── (idle) ──> Screen Saver ──(any input)──> Main Screen
```

## Startup Checklist

1. Copy `example-config.toml` to `config.toml` if you haven't already
2. Hardware connected (NFC reader + UHF reader)
3. PostgreSQL running (`sudo systemctl status postgresql`)
4. Database credentials set in `config.toml`
5. Serial UHF: correct port in `config.toml` (`COM3`, `/dev/ttyUSB0`, etc.)

**Expected startup output:**
```
[NFC] Using: ACS ACR122U PICC Interface 00 00
[UHF] Opened COM3
[DB] Connected to wuzu at localhost:5432
[DB] Connection test successful
[DB] Status: LOCAL
[DB] PostgreSQL 14.5
Starting application...
```

## Troubleshooting

### DB:OFFLINE appears
1. Check PostgreSQL is running
2. Verify credentials in `config.toml`
3. Test manually: `psql -h localhost -U wuzu wuzu`

### NFC reader not found
1. Check USB connection
2. Verify PC/SC daemon: `sudo systemctl status pcscd`
3. List readers: `pcsc_scan`

### UHF reader not connecting
1. Check USB/serial connection
2. Verify port in `config.toml` matches device
3. Linux: check permissions `sudo usermod -a -G dialout $USER`

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
database = "wuzu"           # Database name
user = "wuzu"
password = "your_password"

[hardware]
uhf_port = "COM3"           # Windows: COMx, Linux: /dev/ttyUSBx
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
hunter_id = [0, 0, 0]      # Beep on badge scan (disabled)
complete = [0, 0, 0]        # Beep on session end (disabled)
# Format: [active_time, silent_time, times]
# active_time/silent_time in 100ms units, [0,0,0] = disabled

[scoring]
default_points = 10         # Points assigned to new wuzus
cooldown_minutes = 1        # Minutes before re-scoring same wuzu (0 = disabled)
scan_out = false            # Require admin scan-out before re-scoring
cooldown_overrides_scan_out = false  # Expired cooldown substitutes for scan-out

[display]
border_char = "─"
main_title = "WUZUScan-76 v1.09b"
```

## Support

- Full documentation: See `README.md`
- Recent changes: See `CHANGELOG.md`

---
**Remember:** The database status updates automatically every 30 seconds!
