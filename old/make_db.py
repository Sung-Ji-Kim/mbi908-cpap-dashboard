import sqlite3
from pathlib import Path

DB_PATH = Path("db/local.db")
SQL_PATH = Path("schema/sqlite_local.sql")

DB_PATH.parent.mkdir(exist_ok=True)      # if there is no db, make folder
if DB_PATH.exists():
    DB_PATH.unlink()                      # it there is alredy exist, erase and make a new one.

conn = sqlite3.connect(DB_PATH)
conn.executescript(SQL_PATH.read_text(encoding="utf-8"))
conn.commit()

rows = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
print([r[0] for r in rows])
conn.close()