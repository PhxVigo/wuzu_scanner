-- WUZU HUNTING GAME DATABASE SCHEMA
-- PostgreSQL 12+

-- Drop existing tables (careful in production!)
DROP TABLE IF EXISTS scan_events CASCADE;
DROP TABLE IF EXISTS admins CASCADE;
DROP TABLE IF EXISTS wuzus CASCADE;
DROP TABLE IF EXISTS hunters CASCADE;

-- ============================================================================
-- HUNTERS TABLE
-- ============================================================================
CREATE TABLE hunters (
    uid VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    points INTEGER DEFAULT 0 CHECK (points >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP
);

CREATE INDEX idx_hunters_points ON hunters(points DESC);
CREATE INDEX idx_hunters_last_seen ON hunters(last_seen DESC);

COMMENT ON TABLE hunters IS 'Registered hunters with their NFC badge UIDs';
COMMENT ON COLUMN hunters.uid IS 'NFC badge UID (hex string)';
COMMENT ON COLUMN hunters.points IS 'Total points accumulated';
COMMENT ON COLUMN hunters.last_seen IS 'Last time hunter scanned their badge';

-- ============================================================================
-- WUZUS TABLE
-- ============================================================================
CREATE TABLE wuzus (
    epc VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100),
    fact VARCHAR(200),
    points_value INTEGER DEFAULT 10 CHECK (points_value > 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    times_found INTEGER DEFAULT 0 CHECK (times_found >= 0),
    deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_wuzus_times_found ON wuzus(times_found DESC);

COMMENT ON TABLE wuzus IS 'UHF RFID tagged objects (wuzus) to be hunted';
COMMENT ON COLUMN wuzus.epc IS 'UHF RFID EPC (Electronic Product Code)';
COMMENT ON COLUMN wuzus.name IS 'Optional friendly name for the wuzu';
COMMENT ON COLUMN wuzus.fact IS 'A unique fun fact about this wuzu';
COMMENT ON COLUMN wuzus.points_value IS 'Points awarded when found';
COMMENT ON COLUMN wuzus.times_found IS 'Total times this wuzu has been scanned';

-- ============================================================================
-- ADMINS TABLE
-- ============================================================================
CREATE TABLE admins (
    uid VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    password VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(20)
);

COMMENT ON TABLE admins IS 'Registered admins with their NFC badge UIDs (separate from hunters)';
COMMENT ON COLUMN admins.uid IS 'NFC badge UID (hex string)';
COMMENT ON COLUMN admins.name IS 'Human-readable admin name';
COMMENT ON COLUMN admins.password IS 'Admin password for authentication';
COMMENT ON COLUMN admins.created_by IS 'UID of admin who registered this admin';

-- ============================================================================
-- SCAN EVENTS TABLE
-- ============================================================================
CREATE TABLE scan_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(20) NOT NULL,
    hunter_uid VARCHAR(20) REFERENCES hunters(uid) ON DELETE SET NULL,
    wuzu_epc VARCHAR(50) REFERENCES wuzus(epc) ON DELETE SET NULL,
    details TEXT,
    points_awarded INTEGER DEFAULT 0,
    deleted BOOLEAN DEFAULT FALSE,
    deleted_by VARCHAR(20),
    admin_uid VARCHAR(20),
    private BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_scan_events_timestamp ON scan_events(timestamp DESC);
CREATE INDEX idx_scan_events_hunter ON scan_events(hunter_uid);
CREATE INDEX idx_scan_events_wuzu ON scan_events(wuzu_epc);
CREATE INDEX idx_scan_events_type ON scan_events(event_type);

COMMENT ON TABLE scan_events IS 'Log of all scanning events';
COMMENT ON COLUMN scan_events.event_type IS 'Event types: SCORE, NEW, UNKNOWN, TIMEOUT, CANCEL, EXIT, etc.';
COMMENT ON COLUMN scan_events.details IS 'Human-readable event description';
COMMENT ON COLUMN scan_events.points_awarded IS 'Points awarded in this event (if applicable)';
COMMENT ON COLUMN scan_events.deleted IS 'Soft-delete flag for admin removal of scan events';
COMMENT ON COLUMN scan_events.deleted_by IS 'Admin UID who soft-deleted this event';
COMMENT ON COLUMN scan_events.admin_uid IS 'Admin UID who performed this action (for admin events)';
COMMENT ON COLUMN scan_events.private IS 'Private events only visible in admin areas';

-- ============================================================================
-- SAMPLE DATA (for testing)
-- ============================================================================
INSERT INTO hunters (uid, name, points, last_seen) VALUES
    ('0a2312c2', 'NeonFox', 50, CURRENT_TIMESTAMP - INTERVAL '5 minutes'),
    ('7721bb01', 'GlitchCat', 20, CURRENT_TIMESTAMP - INTERVAL '15 minutes'),
    ('1109ee10', 'VoidWanderer', 30, CURRENT_TIMESTAMP - INTERVAL '2 hours');

-- ============================================================================
-- USEFUL QUERIES
-- ============================================================================

-- Top hunters leaderboard
-- SELECT uid, name, points, last_seen 
-- FROM hunters 
-- ORDER BY points DESC, name ASC 
-- LIMIT 10;

-- Recent scan events
-- SELECT timestamp, event_type, hunter_uid, wuzu_epc, details 
-- FROM scan_events 
-- ORDER BY timestamp DESC 
-- LIMIT 50;

-- Most popular wuzus
-- SELECT epc, name, times_found 
-- FROM wuzus 
-- ORDER BY times_found DESC 
-- LIMIT 20;

-- Hunter statistics
-- SELECT 
--     h.name,
--     h.points,
--     COUNT(se.id) as total_scans,
--     COUNT(DISTINCT se.wuzu_epc) as unique_wuzus,
--     MAX(se.timestamp) as last_scan
-- FROM hunters h
-- LEFT JOIN scan_events se ON h.uid = se.hunter_uid
-- GROUP BY h.uid, h.name, h.points
-- ORDER BY h.points DESC;
