"""Copy finished runs from the local cloud database (SQLite) into Azure SQL in one go.

Use it for dashboard data. The live path (run.py --http) sends one batch at a time
and takes about 30 minutes per night; this copies a whole week in a minute or two.
Rows already in Azure are skipped, so it is safe to run twice.

  pip install pymssql          (once, inside the venv)
  python load_to_azure.py --run B-Medium-s03
  python load_to_azure.py --run B-Medium-s03 A-High-s01

The password is typed at the prompt and is not saved anywhere.
"""
import argparse
import getpass
import sqlite3
from pathlib import Path

import pymssql

HERE = Path(__file__).resolve().parent
SERVER = "sql-mbi908-sungji.database.windows.net"
DATABASE = "sqldb-mbi908"
USER = "mbi908admin"

RUN_COLS = ["run_id", "pipeline", "failure_level", "seed", "clock", "started_at"]
LOG_COLS = ["batch_id", "run_id", "device_id", "received_at", "row_count", "rows_inserted"]
TEL_COLS = ["run_id", "device_id", "batch_id", "received_at", "event_time", "raw_state",
            "session_marker", "pressure_cmh2o", "leak_lpm", "event_count"]


def to_dt(v):
    """'2026-11-02T10:00:00Z' -> '2026-11-02 10:00:00' (DATETIME2 in Azure is UTC)."""
    return v.replace("T", " ").replace("Z", "") if isinstance(v, str) else v


def insert_new(cur, table, cols, rows, key_sql, chunk):
    """Insert rows whose key is not in the table yet. Returns the number inserted."""
    added = 0
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        one = "(" + ", ".join(["%s"] * len(cols)) + ")"
        values = ", ".join([one] * len(part))
        sql = (f"INSERT INTO dbo.{table} ({', '.join(cols)}) "
               f"SELECT {', '.join('v.' + c for c in cols)} FROM (VALUES {values}) AS v({', '.join(cols)}) "
               f"WHERE NOT EXISTS (SELECT 1 FROM dbo.{table} t WHERE {key_sql})")
        cur.execute(sql, tuple(x for r in part for x in r))
        added += cur.rowcount
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", nargs="+", required=True, help="run ids, e.g. B-Medium-s03")
    ap.add_argument("--db", default=str(HERE / "output" / "cloud.db"), help="local cloud database")
    ap.add_argument("--server", default=SERVER)
    ap.add_argument("--database", default=DATABASE)
    ap.add_argument("--user", default=USER)
    args = ap.parse_args()

    src = sqlite3.connect(args.db)
    have = {r[0] for r in src.execute("SELECT DISTINCT run_id FROM ingest_log")}
    missing = [r for r in args.run if r not in have]
    if missing:
        print(f"Not in {args.db}: {', '.join(missing)}")
        print(f"Runs there: {', '.join(sorted(have)) or '(none)'}")
        return

    password = getpass.getpass(f"Password for {args.user}: ")
    print("Connecting (the first time can take up to a minute while the database wakes up)...")
    conn = pymssql.connect(server=args.server, database=args.database, user=args.user,
                           password=password, port=1433, encryption="require",
                           login_timeout=90, timeout=300)
    cur = conn.cursor()

    for run_id in args.run:
        run = src.execute("SELECT run_id, pipeline, failure_level, seed, clock, started_at FROM experiment_run "
                          "WHERE run_id = ?", (run_id,)).fetchone()
        insert_new(cur, "experiment_run", RUN_COLS, [tuple(to_dt(v) for v in run)], "t.run_id = v.run_id", 1)
        log = [tuple(to_dt(v) if c == "received_at" else v for c, v in zip(LOG_COLS, r))
               for r in src.execute(f"SELECT {', '.join(LOG_COLS)} FROM ingest_log WHERE run_id = ?", (run_id,))]
        tel = [tuple(to_dt(v) if c in ("received_at", "event_time") else v for c, v in zip(TEL_COLS, r))
               for r in src.execute(f"SELECT {', '.join(TEL_COLS)} FROM telemetry_minute WHERE run_id = ?", (run_id,))]
        n_log = insert_new(cur, "ingest_log", LOG_COLS, log, "t.batch_id = v.batch_id", 300)
        conn.commit()
        n_tel = insert_new(cur, "telemetry_minute", TEL_COLS, tel,
                           "t.run_id = v.run_id AND t.device_id = v.device_id AND t.event_time = v.event_time", 200)
        conn.commit()
        print(f"{run_id}: batches {n_log} new / {len(log)}, rows {n_tel} new / {len(tel)}")

    conn.close()
    print("Done. Check in a browser: .../api/patients/P02/nights?run_id=" + args.run[0])


if __name__ == "__main__":
    main()
