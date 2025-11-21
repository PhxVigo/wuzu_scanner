# Wuzu Scanner - Quick Reference Card

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
| **DB:LOCAL** | Connected to local database (127.0.0.1) | ✓ Everything working normally |
| **DB:REMOTE** | Connected to remote database server | ✓ Everything working, using remote DB |
| **DB:OFFLINE** | Database unavailable | ⚠ Limited functionality - check database |

## Keyboard Commands

### Main Screen
| Key | Action |
|-----|--------|
| **A** | Add new hunter (register player badge) |
| **W** | Add new wuzu (register UHF tag) |
| **Q** | Quit application |
| **R** | Redraw/refresh screen |
| **Scan Badge** | Start hunting session |

### During Hunt
| Key | Action |
|-----|--------|
| **X** | Exit hunting session early |

### Results Screen
| Key | Action |
|-----|--------|
| **X** | Return to main screen immediately |

## Startup Checklist

1. ✓ Hardware connected (NFC reader, UHF reader)
2. ✓ PostgreSQL running (`sudo systemctl status postgresql`)
3. ✓ Database credentials in `config.toml`
4. ✓ Serial port correct in `config.toml` (COM9 or /dev/ttyUSB0)

**Expected startup output:**
```
[NFC] Using: ACS ACR122U PICC Interface 00 00
[UHF] Opened COM9
[DB] Connected to wuzu_game at localhost:5432
[DB] Connection test successful
[DB] Status: LOCAL
[DB] PostgreSQL 14.5
Starting application...
```

## Troubleshooting

### DB:OFFLINE appears
1. Check PostgreSQL is running
2. Verify credentials in config.toml
3. Test manually: `psql -h localhost -U wuzu_user wuzu_game`

### NFC reader not found
1. Check USB connection
2. Verify PC/SC daemon: `sudo systemctl status pcscd`
3. List readers: `pcsc_scan`

### UHF reader not connecting
1. Check USB/serial connection
2. Verify port in config.toml matches device
3. Linux: Check permissions `sudo usermod -a -G dialout $USER`

## Points System

- Each unique wuzu found = **10 points** (configurable in database)
- Hunting session ends after **5 seconds** of no new finds
- Results display for **10 seconds**

## Game Flow

```
Main Screen → [Scan Badge] → Hunting Mode → Results → Main Screen
     ↑                              ↓
     └──── [A] Add Hunter          Find Wuzus!
     └──── [W] Add Wuzu            
     └──── [Q] Quit
```

## Configuration Quick Reference

Edit `config.toml`:

```toml
[database]
host = "localhost"      # Database server
password = "xxx"        # Your password

[hardware]
uhf_port = "COM9"       # Windows: COMx, Linux: /dev/ttyUSBx

[timing]
scan_timeout = 5        # Seconds before hunt ends
results_display = 10    # Seconds to show results
leaderboard_refresh = 60  # Seconds between DB refreshes
```

## Support

- Full documentation: See `README.md`
- Recent changes: See `CHANGELOG.md`
- Example config: See `config.toml.example`

---
**Remember:** The database status updates automatically every 30 seconds!
