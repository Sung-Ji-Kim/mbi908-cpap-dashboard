-- azure.sql : Azure SQL Database (T-SQL), 7 tables
-- Based on the final ER diagram. All times are UTC.
-- received_at uses the run clock (virtual or real).

-- Drop in reverse order so the script can be re-run during development.
IF OBJECT_ID('dbo.dashboard_state',  'U') IS NOT NULL DROP TABLE dbo.dashboard_state;
IF OBJECT_ID('dbo.ledger',           'U') IS NOT NULL DROP TABLE dbo.ledger;
IF OBJECT_ID('dbo.telemetry_minute', 'U') IS NOT NULL DROP TABLE dbo.telemetry_minute;
IF OBJECT_ID('dbo.ingest_log',       'U') IS NOT NULL DROP TABLE dbo.ingest_log;
IF OBJECT_ID('dbo.experiment_run',   'U') IS NOT NULL DROP TABLE dbo.experiment_run;
IF OBJECT_ID('dbo.device',           'U') IS NOT NULL DROP TABLE dbo.device;
IF OBJECT_ID('dbo.patient',          'U') IS NOT NULL DROP TABLE dbo.patient;
GO

CREATE TABLE dbo.patient (
    patient_id  VARCHAR(50) NOT NULL CONSTRAINT PK_patient PRIMARY KEY,
    timezone    VARCHAR(40) NOT NULL            -- IANA name, e.g. 'Pacific/Auckland'
);

CREATE TABLE dbo.device (
    device_id     VARCHAR(50) NOT NULL CONSTRAINT PK_device PRIMARY KEY,
    patient_id    VARCHAR(50) NOT NULL
                  CONSTRAINT FK_device_patient REFERENCES dbo.patient(patient_id),
    device_model  VARCHAR(50) NULL
);

CREATE TABLE dbo.experiment_run (
    run_id         VARCHAR(40) NOT NULL CONSTRAINT PK_experiment_run PRIMARY KEY,
    pipeline       CHAR(1)     NOT NULL CONSTRAINT CK_run_pipeline CHECK (pipeline IN ('A', 'B')),
    failure_level  VARCHAR(20) NOT NULL
                   CONSTRAINT CK_run_level CHECK (failure_level IN ('none', 'low', 'medium', 'high')),
    seed           INT         NOT NULL,
    clock          VARCHAR(10) NOT NULL CONSTRAINT CK_run_clock CHECK (clock IN ('virtual', 'real')),
    started_at     DATETIME2   NOT NULL
);

-- One row per uploaded batch (Pipeline B). batch_id is generated on the device.
CREATE TABLE dbo.ingest_log (
    batch_id       VARCHAR(50) NOT NULL CONSTRAINT PK_ingest_log PRIMARY KEY,
    run_id         VARCHAR(40) NOT NULL
                   CONSTRAINT FK_ingest_run REFERENCES dbo.experiment_run(run_id),
    device_id      VARCHAR(50) NOT NULL
                   CONSTRAINT FK_ingest_device REFERENCES dbo.device(device_id),
    received_at    DATETIME2   NOT NULL,
    row_count      INT         NOT NULL,        -- rows in the batch
    rows_inserted  INT         NOT NULL         -- rows actually inserted (duplicates are skipped)
);

-- All measurements land here. The primary key is the unique key on device and event time
-- (run_id is added so that every run keeps its own copy of the same simulated night).
CREATE TABLE dbo.telemetry_minute (
    run_id          VARCHAR(40) NOT NULL
                    CONSTRAINT FK_tel_run REFERENCES dbo.experiment_run(run_id),
    device_id       VARCHAR(50) NOT NULL
                    CONSTRAINT FK_tel_device REFERENCES dbo.device(device_id),
    event_time      DATETIME2   NOT NULL,       -- time of the measurement on the device
    raw_state       VARCHAR(10) NULL,           -- state as reported by the device
    session_marker  VARCHAR(50) NULL,
    pressure_cmh2o  FLOAT       NULL,
    leak_lpm        FLOAT       NULL,
    oa_count        INT         NULL,
    ca_count        INT         NULL,
    h_count         INT         NULL,
    batch_id        VARCHAR(50) NULL            -- NULL for Pipeline A rows (no batches)
                    CONSTRAINT FK_tel_batch REFERENCES dbo.ingest_log(batch_id),
    received_at     DATETIME2   NOT NULL,       -- arrival time; Timeliness = received_at - event_time
    CONSTRAINT PK_telemetry_minute PRIMARY KEY (run_id, device_id, event_time)
);

-- Ground truth created by the Python generator. Used for scoring only.
CREATE TABLE dbo.ledger (
    run_id      VARCHAR(40) NOT NULL
                CONSTRAINT FK_ledger_run REFERENCES dbo.experiment_run(run_id),
    device_id   VARCHAR(50) NOT NULL
                CONSTRAINT FK_ledger_device REFERENCES dbo.device(device_id),
    event_time  DATETIME2   NOT NULL,
    true_state  VARCHAR(10) NOT NULL,
    link_up     BIT         NOT NULL,           -- 1 = link up at this minute, 0 = inside an injected outage
    CONSTRAINT PK_ledger PRIMARY KEY (run_id, device_id, event_time)
);

-- Dashboard output, one row per state computed for a minute.
-- A minute can appear again with a later computed_at when delayed records revise it.
CREATE TABLE dbo.dashboard_state (
    run_id       VARCHAR(40) NOT NULL
                 CONSTRAINT FK_dash_run REFERENCES dbo.experiment_run(run_id),
    device_id    VARCHAR(50) NOT NULL
                 CONSTRAINT FK_dash_device REFERENCES dbo.device(device_id),
    event_time   DATETIME2   NOT NULL,
    computed_at  DATETIME2   NOT NULL,
    state        VARCHAR(10) NOT NULL,
    CONSTRAINT PK_dashboard_state PRIMARY KEY (run_id, device_id, event_time, computed_at)
);
-- OPEN DECISION: the allowed values of ledger.true_state, telemetry_minute.raw_state and
-- dashboard_state.state are not fixed yet. Add CHECK constraints once they are decided.
GO