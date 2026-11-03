"""Device side: the SQLite buffer on each CPAP device and the send log.

record() saves one minute as it is measured (acked = 0).
send() tries to upload rows, logs the attempt, and marks rows acked on success.
"""
import sqlite3
from pathlib import Path

from cloud import receive_batch

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "sqlite_device.sql"
COLS = ["event_time", "raw_state", "session_marker", "pressure_cmh2o", "leak_lpm", "event_count"]


class Device:
    def __init__(self, path, run_id, cloud):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA.read_text())
        self.run_id = run_id
        self.cloud = cloud

    def record(self, device_id, row):
        self.conn.execute(
            "INSERT INTO device_buffer VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (self.run_id, device_id, *[row[c] for c in COLS]),
        )

    def unacked(self, device_id):
        cur = self.conn.execute(
            f"SELECT {', '.join(COLS)} FROM device_buffer "
            "WHERE run_id = ? AND device_id = ? AND acked = 0 ORDER BY event_time",
            (self.run_id, device_id),
        )
        return [dict(zip(COLS, r)) for r in cur.fetchall()]

    def send(self, device_id, batch_id, now, link_up, manual=0):
        """One upload attempt. Returns True if the cloud received the rows."""
        rows = self.unacked(device_id)
        result = "ok" if link_up else "offline"
        self.conn.execute(
            "INSERT INTO transmission_log (run_id, device_id, batch_id, attempted_at, result, row_count, manual) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.run_id, device_id, batch_id, now, result, len(rows), manual),
        )
        if link_up and rows:
            receive_batch(self.cloud, self.run_id, device_id, batch_id, rows, now)
            self.conn.execute(
                "UPDATE device_buffer SET acked = 1 WHERE run_id = ? AND device_id = ? AND acked = 0 "
                "AND event_time <= ?",
                (self.run_id, device_id, rows[-1]["event_time"]),
            )
        self.conn.commit()
        return link_up