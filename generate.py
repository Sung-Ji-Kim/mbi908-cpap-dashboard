"""Builds the 1-minute synthetic data for P01 ~ P05 over 7 nights.
 
Output: output/minutes.csv, one row per patient per minute (5 x 7 x 1,440 = 50,400 rows).
true_state in this file is the ground truth that later goes into the ledger table.
The same file feeds both Pipeline A and Pipeline B, so they get identical data.
 
Run:  python generate.py
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
 
import numpy as np
 
import patients as cfg
 
TZ = ZoneInfo(cfg.TIMEZONE)
UTC = ZoneInfo("UTC")
OUT = Path(__file__).parent / "output" / "minutes.csv"
 
 
def night_start(night):
    """Local 12:00 that starts the given night (night 1 = FIRST_NIGHT)."""
    day = datetime.fromisoformat(cfg.FIRST_NIGHT) + timedelta(days=night - 1)
    return day.replace(hour=12, tzinfo=TZ)
 
 
def minute_index(hhmm):
    """Minutes from the 12:00 night start. 23:00 -> 660, 06:00 -> 1080."""
    h, m = map(int, hhmm.split(":"))
    return (h - 12) * 60 + m if h >= 12 else (h + 12) * 60 + m
 
 
def build_night(pid, night, rng):
    """Returns 1,440 rows for one patient and one night."""
    p = cfg.PATIENTS[pid]
    state = ["idle"] * 1440
    marker = [None] * 1440
 
    for k, (a, b) in enumerate(cfg.SESSIONS[pid][night], start=1):
        for i in range(minute_index(a), minute_index(b)):
            state[i] = "therapy"
            marker[i] = f"{pid}-N{night}-S{k}"
 
    for a in cfg.MASK_OFF.get(pid, {}).get(night, []):
        s = minute_index(a)
        for i in range(s, s + cfg.MASK_OFF_LENGTH):
            state[i] = "mask_off"
 
    mean, low, high = p["leak"]
    sd = (high - low) / 4
    start = night_start(night)
    rows = []
    for i in range(1440):
        local = start + timedelta(minutes=i)
        if state[i] == "therapy":
            pressure = cfg.PRESSURE
            leak = round(float(np.clip(rng.normal(mean, sd), low, high)), 1)
            events = int(rng.poisson(p["ahi"] / 60))
        elif state[i] == "mask_off":
            pressure = cfg.PRESSURE
            leak = round(float(rng.uniform(*cfg.MASK_OFF_LEAK)), 1)
            events = 0
        else:
            pressure, leak, events = None, None, 0
        rows.append({
            "patient_id": pid,
            "device_id": p["device_id"],
            "night": night,
            "event_time": local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:00Z"),
            "local_time": local.strftime("%Y-%m-%d %H:%M"),
            "true_state": state[i],
            "session_marker": marker[i],
            "pressure_cmh2o": pressure,
            "leak_lpm": leak,
            "event_count": events,
        })
    return rows
 
 
def main():
    rng = np.random.default_rng(cfg.BASE_SEED)
    rows = []
    for pid in cfg.PATIENTS:
        for night in range(1, cfg.NIGHTS + 1):
            rows.extend(build_night(pid, night, rng))
 
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"saved {len(rows):,} rows to {OUT}")
 
 
if __name__ == "__main__":
    main()
 