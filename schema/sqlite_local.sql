-- SleepStyle cloud schema, SQLite version for local development.
-- Same 7 tables as azure.sql. Use this file until the Azure SQL database exists.
-- received_at and computed_at use the run clock (virtual or real).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patient (
    patient_id  TEXT PRIMARY KEY,                          -- 'P01' ~ 'P05'
    timezone    TEXT NOT NULL DEFAULT 'Pacific/Auckland'
);

CREATE TABLE IF NOT EXISTS device (
    device_id   TEXT PRIMARY KEY,                          -- 'D01' ~ 'D05'
    patient_id  TEXT NOT NULL REFERENCES patient(patient_id)
);

CREATE TABLE IF NOT EXISTS experiment_run (
    run_id         TEXT PRIMARY KEY,                       -- e.g. 'B-Medium-s07'
    pipeline       TEXT NOT NULL CHECK (pipeline IN ('A','B')),
    failure_level  TEXT NOT NULL CHECK (failure_level IN ('None','Low','Medium','High')),
    seed           INTEGER NOT NULL,
    clock          TEXT NOT NULL CHECK (clock IN ('virtual','real')),
    started_at     TEXT NOT NULL
);

-- One row per batch that reached the cloud.
CREATE TABLE IF NOT EXISTS ingest_log (
    batch_id       TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES experiment_run(run_id),
    device_id      TEXT NOT NULL REFERENCES device(device_id),
    received_at    TEXT NOT NULL,
    row_count      INTEGER NOT NULL,                       -- rows in the request
    rows_inserted  INTEGER NOT NULL                        -- duplicates = row_count - rows_inserted
);

-- All measurements land here. One row per device per minute.
CREATE TABLE IF NOT EXISTS telemetry_minute (
    run_id          TEXT NOT NULL REFERENCES experiment_run(run_id),
    device_id       TEXT NOT NULL REFERENCES device(device_id),
    event_time      TEXT NOT NULL,                         -- start of the minute
    raw_state       TEXT NOT NULL CHECK (raw_state IN ('therapy','mask_off','idle')),
    session_marker  TEXT,                                  -- NULL when idle
    pressure_cmh2o  REAL,                                  -- fixed 7.0 in therapy and mask_off minutes, NULL when idle
    leak_lpm        REAL,                                  -- system leak; >= 120 means mask_off
    event_count     INTEGER NOT NULL DEFAULT 0,            -- breathing events in this minute; AHI = sum / therapy hours
    batch_id        TEXT NOT NULL REFERENCES ingest_log(batch_id),
    received_at     TEXT NOT NULL,                         -- first arrival only, never overwritten
    PRIMARY KEY (run_id, device_id, event_time)
);
-- Insert with INSERT OR IGNORE so a resent row is not counted twice.

-- Ground truth for scoring only. The read API and dashboard never query it.
CREATE TABLE IF NOT EXISTS ledger (
    run_id      TEXT NOT NULL REFERENCES experiment_run(run_id),
    device_id   TEXT NOT NULL REFERENCES device(device_id),
    event_time  TEXT NOT NULL,
    true_state  TEXT NOT NULL CHECK (true_state IN ('therapy','mask_off','idle')),
    link_up     INTEGER NOT NULL CHECK (link_up IN (0,1)),
    PRIMARY KEY (run_id, device_id, event_time)
);

-- What the dashboard showed for each minute at each refresh. Scored against ledger.
CREATE TABLE IF NOT EXISTS dashboard_state (
    run_id       TEXT NOT NULL REFERENCES experiment_run(run_id),
    device_id    TEXT NOT NULL REFERENCES device(device_id),
    event_time   TEXT NOT NULL,
    computed_at  TEXT NOT NULL,                            -- refresh time (every 15 min)
    state        TEXT NOT NULL CHECK (state IN ('therapy','mask_off','idle','no_data')),
    PRIMARY KEY (run_id, device_id, event_time, computed_at)
);

--Index for the batch_id foreign key, so deleting or check a batch does not scan every day.
CREATE INDEX IF NOT EXISTS ix_telemetry_batch ON telemetry_minute(batch_id);
