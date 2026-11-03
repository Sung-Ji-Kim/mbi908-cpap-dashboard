"""Checks output/minutes.csv against the targets in the Excel file.
 
Run after generate.py:  python check.py
Every line should end with OK.
"""
from pathlib import Path
 
import pandas as pd
 
CSV = Path(__file__).parent / "output" / "minutes.csv"
 
# Targets from MBI908_variable_reference.xlsx (환자 P01~P05, totals over 7 nights)
TARGET = {
    "P01": {"therapy": 2940, "mask_off": 0,   "idle": 7140},
    "P02": {"therapy": 2785, "mask_off": 150, "idle": 7145},
    "P03": {"therapy": 1114, "mask_off": 0,   "idle": 8966},
    "P04": {"therapy": 2755, "mask_off": 0,   "idle": 7325},
    "P05": {"therapy": 3335, "mask_off": 0,   "idle": 6745},
}
AHI = {"P01": 3.7, "P02": 5.8, "P03": 3.0, "P04": 4.0, "P05": 2.5}
 
df = pd.read_csv(CSV)
 
 
def line(label, ok):
    print(f"{label:<55} {'OK' if ok else 'CHECK'}")
 
 
line(f"total rows = 50,400 (got {len(df):,})", len(df) == 50_400)
line("no duplicate (device, minute)", not df.duplicated(["device_id", "event_time"]).any())
 
counts = df.groupby(["patient_id", "true_state"]).size().unstack(fill_value=0)
for pid, t in TARGET.items():
    got = {s: int(counts.loc[pid].get(s, 0)) for s in t}
    line(f"{pid} minutes {got}", got == t)
 
on = df[df.true_state != "idle"]
line("pressure is 7.0 in every therapy/mask_off minute", (on.pressure_cmh2o == 7.0).all())
line("pressure and leak empty in every idle minute", df[df.true_state == "idle"][["pressure_cmh2o", "leak_lpm"]].isna().all().all())
line("therapy leak always below 120", (df[df.true_state == "therapy"].leak_lpm < 120).all())
line("mask_off leak always 120 or more", (df[df.true_state == "mask_off"].leak_lpm >= 120).all())
 
nightly = df[df.true_state == "therapy"].groupby(["patient_id", "night"]).size()
p03 = nightly.reindex([("P03", n) for n in range(1, 8)], fill_value=0)
used = int((p03 >= 240).sum())
line(f"P03 nights with 4h or more = 2 (got {used})", used == 2)
 
sessions = df.dropna(subset=["session_marker"]).groupby(["patient_id", "night"]).session_marker.nunique()
line("P04 has 2 to 3 sessions every night", sessions.loc["P04"].between(2, 3).all() and len(sessions.loc["P04"]) == 7)
 
print("\nAHI (events / therapy hours). Random, so close to target is enough:")
th = df[df.true_state == "therapy"].groupby("patient_id")
for pid, g in th:
    ahi = g.event_count.sum() / (len(g) / 60)
    print(f"  {pid}: {ahi:.1f}  (target {AHI[pid]})")
 

