# Wuzu Scanner - Recent Changes

## Database Status Monitoring (Latest Update)

### New Features

#### 1. Database Connection Testing
- On startup, the application now runs `SELECT version();` to verify database connectivity
- Displays PostgreSQL version if connection is successful
- Shows clear warnings if database is offline

#### 2. Dynamic Status Bar
The status bar now shows real-time database connection status:

- **DB:LOCAL** - Connected to localhost (127.0.0.1, ::1)
- **DB:REMOTE** - Connected to remote database server
- **DB:OFFLINE** - Database unavailable, running in demo mode

**Before:**
```
┌ SYS:ONLINE | UPTIME:00:05:23 | LAST-SCAN:14:23:45 | TIME:14:30:12 ─┐
```

**After:**
```
┌ DB:LOCAL | UPTIME:00:05:23 | LAST-SCAN:14:23:45 | TIME:14:30:12 ───┐
```

#### 3. Automatic Health Checks
- Database connection is tested every 30 seconds
- If connection status changes (e.g., database goes offline), status bar updates automatically
- Console logs connection state changes

#### 4. Startup Diagnostics
The application now provides detailed startup information:

```
[NFC] Using: ACS ACR122U PICC Interface 00 00
[UHF] Opened COM9
[UHF] Fetching reader info...
[DB] Connected to wuzu_game at localhost:5432
[DB] Connection test successful
[DB] Status: LOCAL
[DB] PostgreSQL 14.5
Starting application...
```

### Configuration

All database settings are now pulled from `config.toml`:

```toml
[database]
host = "localhost"          # Determines LOCAL vs REMOTE status
port = 5432
database = "wuzu_game"
user = "wuzu_user"
password = "your_password"
```

### Technical Details

**New Methods:**
- `DatabaseManager.test_connection()` - Tests connection and returns status dict
- Returns: `{'status': 'LOCAL'|'REMOTE'|'OFFLINE', 'version': str, 'host': str}`

**New Class Variables:**
- `WuzuApp.db_status` - Current database connection status
- `WuzuApp.last_db_health_check` - Timestamp of last health check
- `WuzuApp.db_health_check_interval` - Seconds between checks (30s)

**Modified Methods:**
- `Screen.render_status_bar()` - Now displays DB status instead of static "SYS:ONLINE"
- `WuzuApp.__init__()` - Runs connection test on startup
- `WuzuApp.run()` - Periodic health checks in main loop

### Benefits

1. **Immediate Feedback** - Operators know database status at a glance
2. **Troubleshooting** - Clear indication if database issues occur
3. **Network Awareness** - Distinction between local and remote connections
4. **Graceful Degradation** - Application continues in demo mode if DB is offline
5. **Self-Healing** - Automatically detects when database comes back online

### Demo Mode

If the database is OFFLINE, the application still runs with limited functionality:
- Cannot add new hunters or wuzus
- Cannot record scores
- Cannot display leaderboard or event log
- Useful for hardware testing without database setup

## Previous Updates

### PostgreSQL Integration
- Replaced in-memory data storage with PostgreSQL
- Immediate write-through on all events
- On-demand queries for display data
- No local caching required

### Configuration System
- TOML-based configuration
- All timing parameters configurable
- Hardware settings externalized
- Audio beep patterns customizable

### Multi-Screen Architecture
- Screen-based UI system
- Modular screen classes
- Efficient dirty panel rendering
- Cross-platform terminal support
