-- sqlite_device.sql : tables that live on the device (Pipeline B), in the device's own SQLite file.
-- run_id and device_id refer to the Azure tables; there is no cross-database foreign key.

CREATE TABLE IF NOT EXISTS device_buffer (
    run_id          TEXT NOT NULL,
    device_id       TEXT NOT NULL,
    event_time      TEXT NOT NULL,              -- ISO-8601 UTC
    raw_state       TEXT,
    session_marker  TEXT,
    pressure_cmh2o  REAL,
    leak_lpm        REAL,
    oa_count        INTEGER,
    ca_count        INTEGER,
    h_count         INTEGER,
    acked           INTEGER NOT NULL DEFAULT 0 CHECK (acked IN (0, 1)),  -- 1 = cloud confirmed the row
    PRIMARY KEY (run_id, device_id, event_time)
);

CREATE TABLE IF NOT EXISTS transmission_log (
    attempt_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    device_id     TEXT NOT NULL,
    batch_id      TEXT,
    attempted_at  TEXT NOT NULL,
    result        TEXT NOT NULL,                -- e.g. 'ok', 'failed' (values not fixed yet)
    row_count     INTEGER,
    manual        INTEGER NOT NULL DEFAULT 0 CHECK (manual IN (0, 1))   -- 1 = simulated manual action
);

