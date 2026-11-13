"""SleepStyle cloud API: Azure Functions for receiving and reading CPAP data.

POST /api/ingest                        a device sends one batch (Pipeline B, and A via the phone)
GET  /api/patients                      list of patients and their devices
GET  /api/patients/{patient_id}/nights  7 nights for the dashboard: summary + hour-by-hour states

Where the data goes (set in local.settings.json, or in the Static Web App environment variables):
  SQL_SERVER set   -> Azure SQL, with SQL_DATABASE, SQL_USER, SQL_PASSWORD
                      (pymssql: a pip package only, so no system driver is needed on the Mac or on Azure)
  SQL_SERVER empty -> the SQLite file in CLOUD_DB_PATH (local practice)

POST /api/ingest with JSON:
  {"run_id", "device_id", "batch_id", "sent_at", "rows": [ {event_time, raw_state, ...}, ... ]}
Replies 200 with {"inserted": n, "duplicates": m}.
"""
import json
import logging
import os
import sqlite3
import time as clock
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import azure.functions as func


COLS = ["event_time", "raw_state", "session_marker", "pressure_cmh2o", "leak_lpm", "event_count"]
NEEDED = ["run_id", "device_id", "batch_id", "rows"]
ISO = "%Y-%m-%dT%H:%M:%SZ"


# ---------------------------------------------------------------- storage: SQLite or Azure SQL

def use_azure():
    return bool(os.environ.get("SQL_SERVER"))


def to_dt(s):
    """ISO text -> naive UTC datetime (what Azure SQL DATETIME2 stores)."""
    return datetime.strptime(s, ISO)


def to_iso(v):
    """A time from either database -> ISO text."""
    if v is None or isinstance(v, str):
        return v
    return v.strftime(ISO)


def open_db():
    if not use_azure():
        conn = sqlite3.connect(os.environ["CLOUD_DB_PATH"], timeout=30)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    import pymssql
    # A paused free-offer database takes up to a minute to wake up. Try a few times.
    for wait in [0, 5, 10, 20, 30, None]:
        try:
            return pymssql.connect(server=os.environ["SQL_SERVER"], database=os.environ["SQL_DATABASE"],
                                   user=os.environ["SQL_USER"], password=os.environ["SQL_PASSWORD"],
                                   port=1433, encryption="require", login_timeout=30, timeout=60)
        except pymssql.OperationalError as e:
            if wait is None:
                raise
            logging.warning("database not ready yet (%s), retrying in %ss", str(e)[:80], wait)
            clock.sleep(wait)


def integrity_errors():
    if use_azure():
        import pymssql
        return (sqlite3.IntegrityError, pymssql.IntegrityError)
    return (sqlite3.IntegrityError,)


def run(cur, sql, params=()):
    """SQLite uses ? placeholders, pymssql uses %s. The SQL here is written with ?."""
    if use_azure():
        sql = sql.replace("?", "%s")
    cur.execute(sql, tuple(params))
    return cur


def query(conn, sql, params=()):
    """Runs a SELECT and returns a list of dicts. Times come back as ISO text."""
    cur = run(conn.cursor(), sql, params)
    names = [d[0] for d in cur.description]
    return [{k: to_iso(v) if isinstance(v, datetime) else v for k, v in zip(names, row)}
            for row in cur.fetchall()]


def save_batch(conn, run_id, device_id, batch_id, rows, received_at):
    """Same rules as cloud.receive_batch(). A resent batch or row is ignored, never counted twice."""
    cur = conn.cursor()
    if not use_azure():
        cur.execute("INSERT OR IGNORE INTO ingest_log VALUES (?, ?, ?, ?, ?, 0)",
                    (batch_id, run_id, device_id, received_at, len(rows)))
        before = conn.total_changes
        cur.executemany(
            "INSERT OR IGNORE INTO telemetry_minute VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(run_id, device_id, *[r.get(c) for c in COLS], batch_id, received_at) for r in rows],
        )
        inserted = conn.total_changes - before
    else:
        got = to_dt(received_at)
        run(cur,
            "IF NOT EXISTS (SELECT 1 FROM dbo.ingest_log WHERE batch_id = ?) "
            "INSERT INTO dbo.ingest_log VALUES (?, ?, ?, ?, ?, 0)",
            (batch_id, batch_id, run_id, device_id, got, len(rows)),
        )
        inserted = 0
        # Azure SQL allows 2,100 parameters per statement, so rows go in chunks of 300.
        for i in range(0, len(rows), 300):
            chunk = rows[i:i + 300]
            values = ", ".join(["(?, ?, ?, ?, ?, ?)"] * len(chunk))
            params = [run_id, device_id, batch_id, got]
            for r in chunk:
                params += [to_dt(r["event_time"]), r["raw_state"], r.get("session_marker"),
                           r.get("pressure_cmh2o"), r.get("leak_lpm"), r.get("event_count", 0)]
            run(cur,
                "INSERT INTO dbo.telemetry_minute (run_id, device_id, batch_id, received_at, "
                "event_time, raw_state, session_marker, pressure_cmh2o, leak_lpm, event_count) "
                "SELECT p.run_id, p.device_id, p.batch_id, p.received_at, v.* "
                "FROM (SELECT ? AS run_id, ? AS device_id, ? AS batch_id, ? AS received_at) AS p "
                f"CROSS JOIN (VALUES {values}) AS v(event_time, raw_state, session_marker, "
                "pressure_cmh2o, leak_lpm, event_count) "
                "WHERE NOT EXISTS (SELECT 1 FROM dbo.telemetry_minute t WHERE t.run_id = p.run_id "
                "AND t.device_id = p.device_id AND t.event_time = v.event_time)",
                params,
            )
            inserted += cur.rowcount
    run(cur, "UPDATE ingest_log SET rows_inserted = rows_inserted + ? WHERE batch_id = ?",
                (inserted, batch_id))
    conn.commit()
    return inserted


def reply(body, status):
    return func.HttpResponse(json.dumps(body), status_code=status, mimetype="application/json")


# ---------------------------------------------------------------- receive

def ingest(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return reply({"error": "body is not JSON"}, 400)
    missing = [k for k in NEEDED if k not in body]
    if missing:
        return reply({"error": f"missing fields: {missing}"}, 400)

    # Virtual-clock runs send their own clock in sent_at. Real runs use the server clock.
    received_at = body.get("sent_at") or datetime.now(timezone.utc).strftime(ISO)
    rows = body["rows"]
    try:
        conn = open_db()
        try:
            inserted = save_batch(conn, body["run_id"], body["device_id"], body["batch_id"], rows, received_at)
        finally:
            conn.close()
    except integrity_errors() as e:
        logging.warning("rejected batch %s: %s", body["batch_id"], e)
        return reply({"error": f"rejected: {e}"}, 422)

    logging.info("batch %s: %d rows, %d new", body["batch_id"], len(rows), inserted)
    return reply({"inserted": inserted, "duplicates": len(rows) - inserted}, 200)


# ---------------------------------------------------------------- read API for the dashboard

CODE = {"therapy": "t", "mask_off": "m"}   # idle minutes are left out: a gap means "not using"


def night_summary(rows, minutes_due):
    """rows: telemetry of one night. minutes_due: minutes of the night that are already in the past."""
    therapy = [r for r in rows if r["raw_state"] == "therapy"]
    leaks = [r["leak_lpm"] for r in therapy if r["leak_lpm"] is not None]
    hours = len(therapy) / 60
    return {
        "therapy_min": len(therapy),
        "mask_off_min": sum(r["raw_state"] == "mask_off" for r in rows),
        "sessions": len({r["session_marker"] for r in rows if r["session_marker"]}),
        "avg_leak_lpm": round(sum(leaks) / len(leaks), 1) if leaks else None,
        "ahi": round(sum(r["event_count"] for r in therapy) / hours, 1) if hours else None,
        "not_received_min": max(minutes_due - len(rows), 0),
    }


def segments(rows, start, minutes_due):
    """Minute states as [code, start minute, length]. t = therapy, m = mask off, n = not received."""
    state = [None] * 1440                      # None = idle or still in the future
    for i in range(minutes_due):
        state[i] = "n"
    for r in rows:
        i = int((to_dt(r["event_time"]).replace(tzinfo=timezone.utc) - start).total_seconds() // 60)
        if 0 <= i < 1440:
            state[i] = CODE.get(r["raw_state"])
    out = []
    for i, s in enumerate(state):
        if s is None:
            continue
        if out and out[-1][0] == s and out[-1][1] + out[-1][2] == i:
            out[-1][2] += 1
        else:
            out.append([s, i, 1])
    return out


def patients(req: func.HttpRequest) -> func.HttpResponse:
    conn = open_db()
    try:
        rows = query(conn, "SELECT p.patient_id, p.timezone, d.device_id FROM patient p "
                           "JOIN device d ON d.patient_id = p.patient_id ORDER BY p.patient_id")
    finally:
        conn.close()
    return reply(rows, 200)


def nights(req: func.HttpRequest) -> func.HttpResponse:
    """Query: run_id (required), from (first night, local date, default 2026-11-02),
    days (default 7), as_of (UTC time the dashboard is looking from, default now).
    Only rows that had arrived by as_of are used, so a replay shows what the patient saw then."""
    pid = req.route_params.get("patient_id")
    run_id = req.params.get("run_id") or os.environ.get("DEFAULT_RUN_ID")
    if not run_id:
        return reply({"error": "run_id is required"}, 400)
    try:
        first = date.fromisoformat(req.params.get("from", "2026-11-02"))
        days = min(int(req.params.get("days", "7")), 31)
        as_of = req.params.get("as_of") or datetime.now(timezone.utc).strftime(ISO)
        as_of_dt = to_dt(as_of).replace(tzinfo=timezone.utc)
    except ValueError:
        return reply({"error": "check from (YYYY-MM-DD), days (number) and as_of (YYYY-MM-DDTHH:MM:SSZ)"}, 400)

    # SQLite compares ISO text, Azure SQL compares DATETIME2.
    t = (lambda dt: dt.astimezone(timezone.utc).replace(tzinfo=None)) if use_azure() \
        else (lambda dt: dt.astimezone(timezone.utc).strftime(ISO))

    conn = open_db()
    try:
        found = query(conn, "SELECT p.timezone, d.device_id FROM patient p "
                            "JOIN device d ON d.patient_id = p.patient_id WHERE p.patient_id = ?", (pid,))
        if not found:
            return reply({"error": f"unknown patient {pid}"}, 404)
        tz_name, device_id = found[0]["timezone"], found[0]["device_id"]
        tz = ZoneInfo(tz_name)
        last = query(conn, "SELECT MAX(received_at) AS last FROM telemetry_minute "
                           "WHERE run_id = ? AND device_id = ? AND received_at <= ?",
                     (run_id, device_id, t(as_of_dt)))[0]["last"]

        out = []
        for k in range(days):
            day = first + timedelta(days=k)
            start = datetime.combine(day, time(12), tz)          # a night runs 12:00 to 12:00 local
            end = start + timedelta(days=1)
            due = int(max(min((as_of_dt - start).total_seconds() // 60, 1440), 0))
            rows = query(conn,
                         "SELECT event_time, raw_state, session_marker, leak_lpm, event_count "
                         "FROM telemetry_minute WHERE run_id = ? AND device_id = ? "
                         "AND event_time >= ? AND event_time < ? AND received_at <= ? ORDER BY event_time",
                         (run_id, device_id, t(start), t(end), t(as_of_dt)))
            out.append({"night": day.isoformat(), "start_utc": start.astimezone(timezone.utc).strftime(ISO),
                        **night_summary(rows, due), "segments": segments(rows, start, due)})
    finally:
        conn.close()

    return reply({"patient_id": pid, "device_id": device_id, "timezone": tz_name,
                  "run_id": run_id, "as_of": as_of, "last_received": to_iso(last), "nights": out}, 200)
