"""SleepStyle receiver: Azure Function that takes one batch from a device.

POST /api/ingest with JSON:
  {"run_id", "device_id", "batch_id", "sent_at", "rows": [ {event_time, raw_state, ...}, ... ]}
Replies 200 with {"inserted": n, "duplicates": m}.

Local run: the data goes into the SQLite file named in CLOUD_DB_PATH (local.settings.json).
Later the same code switches to Azure SQL.
"""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

COLS = ["event_time", "raw_state", "session_marker", "pressure_cmh2o", "leak_lpm", "event_count"]
NEEDED = ["run_id", "device_id", "batch_id", "rows"]


def open_db():
    conn = sqlite3.connect(os.environ["CLOUD_DB_PATH"], timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def save_batch(conn, run_id, device_id, batch_id, rows, received_at):
    """Same rules as cloud.receive_batch(). A resent batch or row is ignored, never counted twice."""
    conn.execute(
        "INSERT OR IGNORE INTO ingest_log VALUES (?, ?, ?, ?, ?, 0)",
        (batch_id, run_id, device_id, received_at, len(rows)),
    )
    before = conn.total_changes
    conn.executemany(
        """INSERT OR IGNORE INTO telemetry_minute
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(run_id, device_id, *[r.get(c) for c in COLS], batch_id, received_at) for r in rows],
    )
    inserted = conn.total_changes - before
    conn.execute(
        "UPDATE ingest_log SET rows_inserted = rows_inserted + ? WHERE batch_id = ?",
        (inserted, batch_id),
    )
    conn.commit()
    return inserted


def reply(body, status):
    return func.HttpResponse(json.dumps(body), status_code=status, mimetype="application/json")


@app.route(route="ingest", methods=["POST"])
def ingest(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return reply({"error": "body is not JSON"}, 400)
    missing = [k for k in NEEDED if k not in body]
    if missing:
        return reply({"error": f"missing fields: {missing}"}, 400)

    # Virtual-clock runs send their own clock in sent_at. Real runs use the server clock.
    received_at = body.get("sent_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = body["rows"]
    try:
        conn = open_db()
        try:
            inserted = save_batch(conn, body["run_id"], body["device_id"], body["batch_id"], rows, received_at)
        finally:
            conn.close()
    except sqlite3.IntegrityError as e:
        logging.warning("rejected batch %s: %s", body["batch_id"], e)
        return reply({"error": f"rejected: {e}"}, 422)

    logging.info("batch %s: %d rows, %d new", body["batch_id"], len(rows), inserted)
    return reply({"inserted": inserted, "duplicates": len(rows) - inserted}, 200)
