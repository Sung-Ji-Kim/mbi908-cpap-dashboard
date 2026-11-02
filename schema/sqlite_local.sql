-- sqlite_local.sql : the 7 Azure tables mirrored in SQLite for local development.
-- Type mapping: VARCHAR/CHAR -> TEXT, INT/BIGINT -> INTEGER, FLOAT -> REAL,
--               DATETIME2 -> TEXT (ISO-8601 UTC, e.g. '2026-11-02T13:05:00Z'), BIT -> INTEGER (0/1).
-- Run PRAGMA foreign_keys = ON on every connection (SQLite does not enforce foreign keys by default).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patient (
    patient_id  TEXT PRIMARY KEY,
    timezone    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device (
    device_id     TEXT PRIMARY KEY,
    patient_id    TEXT NOT NULL REFERENCES patient(patient_id),
    device_model  TEXT
);

CREATE TABLE IF NOT EXISTS experiment_run (
    run_id         TEXT PRIMARY KEY,
    pipeline       TEXT NOT NULL CHECK (pipeline IN ('A', 'B')),
    failure_level  TEXT NOT NULL CHECK (failure_level IN ('none', 'low', 'medium', 'high')),
    seed           INTEGER NOT NULL,
    clock          TEXT NOT NULL CHECK (clock IN ('virtual', 'real')),
    started_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_log (
    batch_id       TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES experiment_run(run_id),
    device_id      TEXT NOT NULL REFERENCES device(device_id),
    received_at    TEXT NOT NULL,
    row_count      INTEGER NOT NULL,
    rows_inserted  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry_minute (
    run_id          TEXT NOT NULL REFERENCES experiment_run(run_id),
    device_id       TEXT NOT NULL REFERENCES device(device_id),
    event_time      TEXT NOT NULL,
    raw_state       TEXT,
    session_marker  TEXT,
    pressure_cmh2o  REAL,
    leak_lpm        REAL,
    oa_count        INTEGER,
    ca_count        INTEGER,
    h_count         INTEGER,
    batch_id        TEXT REFERENCES ingest_log(batch_id),
    received_at     TEXT NOT NULL,
    PRIMARY KEY (run_id, device_id, event_time)
);

CREATE TABLE IF NOT EXISTS ledger (
    run_id      TEXT NOT NULL REFERENCES experiment_run(run_id),
    device_id   TEXT NOT NULL REFERENCES device(device_id),
    event_time  TEXT NOT NULL,
    true_state  TEXT NOT NULL,
    link_up     INTEGER NOT NULL CHECK (link_up IN (0, 1)),
    PRIMARY KEY (run_id, device_id, event_time)
);

CREATE TABLE IF NOT EXISTS dashboard_state (
    run_id       TEXT NOT NULL REFERENCES experiment_run(run_id),
    device_id    TEXT NOT NULL REFERENCES device(device_id),
    event_time   TEXT NOT NULL,
    computed_at  TEXT NOT NULL,
    state        TEXT NOT NULL,
    PRIMARY KEY (run_id, device_id, event_time, computed_at)
);