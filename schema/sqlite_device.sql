-- SleepStyle device-side schema (SQLite, kept on the device).
-- run_id and device_id refer to the cloud tables, but there is no foreign key across databases.


-- Minutes waiting to be sent. Pipeline B keeps failed batches here and resends them later.
CREATE TABLE IF NOT EXISTS device_buffer (
    run_id          TEXT NOT NULL,
    device_id       TEXT NOT NULL,
    event_time      TEXT NOT NULL,
    -- 5 measurement columns, same as telemetry_minute
    raw_state       TEXT NOT NULL CHECK (raw_state IN ('therapy','mask_off','idle')),
    session_marker  TEXT,
    pressure_cmh2o  REAL,
    leak_lpm        REAL,
    event_count     INTEGER NOT NULL DEFAULT 0,
    acked           INTEGER NOT NULL DEFAULT 0 CHECK (acked IN (0,1)),  -- 1 = cloud confirmed receipt
    PRIMARY KEY (run_id, device_id, event_time)
);

-- One row per send attempt (A: sync at Stop, catch-up, re-pair; B: 15-min batch and retries).
CREATE TABLE IF NOT EXISTS transmission_log (
    attempt_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    device_id     TEXT NOT NULL,
    batch_id      TEXT NOT NULL,
    attempted_at  TEXT NOT NULL,                           -- run clock
    result        TEXT NOT NULL CHECK (result IN ('ok','offline','timeout','http_error')),
    row_count     INTEGER NOT NULL,
    manual        INTEGER NOT NULL DEFAULT 0 CHECK (manual IN (0,1))  -- 1 = manual step, e.g. re-pairing
);
