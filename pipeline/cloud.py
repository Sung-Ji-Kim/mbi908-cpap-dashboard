"""Cloud side, local version: the SQLite file that stands in for Azure SQL,
and receive_batch(), which stands in for the Azure Function that receives data.
"""
import csv
import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "sqlite_local.sql"
HTTP_LOG = Path(__file__).resolve().parent / "results" / "live_http_log.csv"


def open_cloud(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text())
    return conn


def receive_batch(conn, run_id, device_id, batch_id, rows, now):
    """Saves one batch. Returns how many rows were new.

    rows: list of dicts with event_time and the 5 measurement columns.
    A row that already exists is ignored, so a resent row is never counted twice.
    """
    conn.execute(
        "INSERT INTO ingest_log VALUES (?, ?, ?, ?, ?, 0)",
        (batch_id, run_id, device_id, now, len(rows)),
    )
    before = conn.total_changes
    conn.executemany(
        """INSERT OR IGNORE INTO telemetry_minute
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(run_id, device_id, r["event_time"], r["raw_state"], r["session_marker"],
          r["pressure_cmh2o"], r["leak_lpm"], r["event_count"], batch_id, now)
         for r in rows],
    )
    inserted = conn.total_changes - before
    conn.execute("UPDATE ingest_log SET rows_inserted = ? WHERE batch_id = ?", (inserted, batch_id))
    conn.commit()
    return inserted


def post_batch(url, run_id, device_id, batch_id, rows, now):

    body = json.dumps({"run_id": run_id, "device_id": device_id, "batch_id": batch_id,
                       "sent_at": now, "rows": rows}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    sent = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            result = "ok" if res.status == 200 else "http_error"
    except TimeoutError:
        result = "timeout"
    except OSError:
        result = "http_error"
    log_http(run_id, device_id, batch_id, len(rows), sent, (time.perf_counter() - t0) * 1000, result)
    return result


def log_http(run_id, device_id, batch_id, n_rows, sent, ms, result):
    """One line per HTTP send: real clock time and how long Azure took to answer."""
    HTTP_LOG.parent.mkdir(exist_ok=True)
    new = not HTTP_LOG.exists()
    with HTTP_LOG.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["sent_real_utc", "run_id", "device_id", "batch_id", "rows", "response_ms", "result"])
        w.writerow([sent.strftime("%Y-%m-%dT%H:%M:%SZ"), run_id, device_id, batch_id, n_rows, round(ms), result])    
