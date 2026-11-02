import random
import sqlite3
from datetime import datetime, timedelta, timezone

from config import DB_PATH, N_PATIENTS, N_NIGHTS, NIGHT_MINUTES
from generator import make_night

FIRST_NIGHT = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)


def build_ledger(conn, run_id, seed):
    conn.execute("DELETE FROM ledger WHERE run_id = ?", (run_id,))   # safe to re-run
    rng = random.Random(seed)
    rows = []
    for p in range(1, N_PATIENTS + 1):
        for n in range(N_NIGHTS):
            start = FIRST_NIGHT + timedelta(days=n)
            for event_time, state in make_night(rng, start, NIGHT_MINUTES):
                rows.append((run_id, f"d{p}", event_time, state, 1))
    conn.executemany(
        "INSERT INTO ledger (run_id, device_id, event_time, true_state, link_up) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT OR IGNORE INTO experiment_run "
        "(run_id, pipeline, failure_level, seed, clock, started_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("demo_B_none_1", "B", "none", 1, "virtual", "2026-11-02T00:00:00Z"),
    )
    n = build_ledger(conn, "demo_B_none_1", 1)
    conn.commit()
    print(n)
    print(conn.execute("SELECT true_state, COUNT(*) FROM ledger GROUP BY true_state").fetchall())
    conn.close()