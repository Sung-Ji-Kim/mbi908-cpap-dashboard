import sqlite3
from config import DB_PATH, N_PATIENTS, TIMEZONE

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON") # To check foreign keys, it needs to turn on in SQLite.

for i in range(1, N_PATIENTS + 1):
    conn.execute(
        "INSERT OR IGNORE INTO patient (patient_id, timezone) VALUES (?, ?)",
        (f"p{i}", TIMEZONE),
    )
    conn.execute(
        "INSERT OR IGNORE INTO device (device_id, patient_id, device_model) VALUES (?, ?, ?)",
        (f"d{i}", f"p{i}", "simulated"),
    )

conn.commit()
for row in conn.execute("SELECT device_id, patient_id FROM device"):
    print(row)
conn.close()

