-- SleepStyle cloud schema, Azure SQL version.
-- Each CREATE is skipped if the table already exists, so running this twice does not delete data.
IF OBJECT_ID('dbo.patient', 'U') IS NULL
    CREATE TABLE dbo.patient (
        patient_id VARCHAR (50) NOT NULL PRIMARY KEY,
        timezone   VARCHAR (40) DEFAULT 'Pacific/Auckland' NOT NULL
    );


GO
IF OBJECT_ID('dbo.device', 'U') IS NULL
    CREATE TABLE dbo.device (
        device_id  VARCHAR (50) NOT NULL PRIMARY KEY,
        patient_id VARCHAR (50) NOT NULL FOREIGN KEY REFERENCES dbo.patient (patient_id)
    );


GO
IF OBJECT_ID('dbo.experiment_run', 'U') IS NULL
    CREATE TABLE dbo.experiment_run (
        run_id        VARCHAR (40) NOT NULL PRIMARY KEY,
        pipeline      CHAR (1)     NOT NULL CHECK (pipeline IN ('A', 'B')),
        failure_level VARCHAR (20) NOT NULL CHECK (failure_level IN ('None', 'Low', 'Medium', 'High')),
        seed          INT          NOT NULL,
        clock         VARCHAR (10) NOT NULL CHECK (clock IN ('virtual', 'real')),
        started_at    DATETIME2    NOT NULL
    );


GO
IF OBJECT_ID('dbo.ingest_log', 'U') IS NULL
    CREATE TABLE dbo.ingest_log (
        batch_id      VARCHAR (50) NOT NULL PRIMARY KEY,
        run_id        VARCHAR (40) NOT NULL FOREIGN KEY REFERENCES dbo.experiment_run (run_id),
        device_id     VARCHAR (50) NOT NULL FOREIGN KEY REFERENCES dbo.device (device_id),
        received_at   DATETIME2    NOT NULL,
        row_count     INT          NOT NULL, -- rows in the request
        rows_inserted INT          NOT NULL -- duplicates = row_count - rows_inserted
    );


GO
IF OBJECT_ID('dbo.telemetry_minute', 'U') IS NULL
    CREATE TABLE dbo.telemetry_minute (
        run_id         VARCHAR (40) NOT NULL FOREIGN KEY REFERENCES dbo.experiment_run (run_id),
        device_id      VARCHAR (50) NOT NULL FOREIGN KEY REFERENCES dbo.device (device_id),
        event_time     DATETIME2    NOT NULL,
        raw_state      VARCHAR (10) NOT NULL CHECK (raw_state IN ('therapy', 'mask_off', 'idle')),
        session_marker VARCHAR (50) NULL, -- NULL when idle
        pressure_cmh2o FLOAT        NULL, -- fixed 7.0 in therapy and mask_off minutes, NULL when idle
        leak_lpm       FLOAT        NULL, -- system leak; >= 120 means mask_off
        event_count    INT          DEFAULT 0 NOT NULL,
        batch_id       VARCHAR (50) NOT NULL FOREIGN KEY REFERENCES dbo.ingest_log (batch_id),
        received_at    DATETIME2    NOT NULL, -- first arrival only, never overwritten
        CONSTRAINT pk_telemetry_minute PRIMARY KEY (run_id, device_id, event_time)
    );


GO
-- Insert with MERGE ... WHEN NOT MATCHED THEN INSERT so a resent row is not counted twice.
-- Ground truth for scoring only. The read API and dashboard never query it.
IF OBJECT_ID('dbo.ledger', 'U') IS NULL
    CREATE TABLE dbo.ledger (
        run_id     VARCHAR (40) NOT NULL FOREIGN KEY REFERENCES dbo.experiment_run (run_id),
        device_id  VARCHAR (50) NOT NULL FOREIGN KEY REFERENCES dbo.device (device_id),
        event_time DATETIME2    NOT NULL,
        true_state VARCHAR (10) NOT NULL CHECK (true_state IN ('therapy', 'mask_off', 'idle')),
        link_up    BIT          NOT NULL,
        CONSTRAINT pk_ledger PRIMARY KEY (run_id, device_id, event_time)
    );


GO
IF OBJECT_ID('dbo.dashboard_state', 'U') IS NULL
    CREATE TABLE dbo.dashboard_state (
        run_id      VARCHAR (40) NOT NULL FOREIGN KEY REFERENCES dbo.experiment_run (run_id),
        device_id   VARCHAR (50) NOT NULL FOREIGN KEY REFERENCES dbo.device (device_id),
        event_time  DATETIME2    NOT NULL,
        computed_at DATETIME2    NOT NULL, -- refresh time (every 15 min)
        state       VARCHAR (10) NOT NULL CHECK (state IN ('therapy', 'mask_off', 'idle', 'no_data')),
        CONSTRAINT pk_dashboard_state PRIMARY KEY (run_id, device_id, event_time, computed_at)
    );