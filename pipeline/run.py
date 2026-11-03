"""Runs one experiment on a virtual clock and prints the results.

Example:  python run.py --pipeline B --level Medium --seed 7
Output files go to pipeline/output/ (cloud.db holds every run, one device file per run).
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from cloud import open_cloud
from device import Device
from outages import build_outages
from pipeline_a import PipelineA
from pipeline_b import PipelineB

ROOT = Path(__file__).resolve().parent.parent
MINUTES = ROOT / "generator" / "output" / "minutes.csv"
OUT = Path(__file__).resolve().parent / "output"


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:00Z")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", choices=["A", "B"], required=True)
    ap.add_argument("--level", choices=["None", "Low", "Medium", "High"], required=True)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    run_id = f"{args.pipeline}-{args.level}-s{args.seed:02d}"

    df = pd.read_csv(MINUTES, keep_default_na=False, na_values=[""])
    df = df.rename(columns={"true_state": "raw_state"})
    df = df.astype(object).where(df.notna(), None)

    OUT.mkdir(exist_ok=True)
    cloud = open_cloud(OUT / "cloud.db")
    for table in ["dashboard_state", "ledger", "telemetry_minute", "ingest_log"]:
        cloud.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))
    cloud.execute("DELETE FROM experiment_run WHERE run_id = ?", (run_id,))
    for pid, dev in df[["patient_id", "device_id"]].drop_duplicates().itertuples(index=False):
        cloud.execute("INSERT OR IGNORE INTO patient (patient_id) VALUES (?)", (pid,))
        cloud.execute("INSERT OR IGNORE INTO device VALUES (?, ?)", (dev, pid))
    cloud.execute("INSERT INTO experiment_run VALUES (?, ?, ?, ?, 'virtual', ?)",
                  (run_id, args.pipeline, args.level, args.seed, iso(datetime.now(timezone.utc))))
    cloud.commit()

    dev_path = OUT / f"device_{run_id}.db"
    dev_path.unlink(missing_ok=True)
    device = Device(dev_path, run_id, cloud)
    pipe = PipelineA(device, run_id, args.seed) if args.pipeline == "A" else PipelineB(device, run_id)
    down = build_outages(args.level, args.seed)

    ledger = []
    rows = df.sort_values(["event_time", "device_id"]).to_dict("records")
    by_minute = {}
    for r in rows:
        by_minute.setdefault(r["event_time"], []).append(r)

    nxt = {}   # (device, event_time) -> next row, to spot the minute a session ends
    for dev, g in df.sort_values("event_time").groupby("device_id"):
        states = g["raw_state"].tolist()
        times = g["event_time"].tolist()
        for i, t in enumerate(times):
            nxt[(dev, t)] = states[i + 1] if i + 1 < len(states) else "idle"

    for minute_no, (t, group) in enumerate(sorted(by_minute.items())):
        now = iso(datetime.strptime(t, "%Y-%m-%dT%H:%M:00Z") + timedelta(minutes=1))
        for r in group:
            night, idx = int(r["night"]), minute_no % 1440
            link_up = idx not in down[night]
            device.record(r["device_id"], r)
            ended = r["raw_state"] != "idle" and nxt[(r["device_id"], t)] == "idle"
            pipe.on_minute(r["device_id"], minute_no, now, link_up, ended)
            ledger.append((run_id, r["device_id"], t, r["raw_state"], int(link_up)))
    device.conn.commit()

    cloud.executemany("INSERT INTO ledger VALUES (?, ?, ?, ?, ?)", ledger)
    cloud.commit()
    report(cloud, device, run_id)


def report(cloud, device, run_id):
    led = pd.read_sql("SELECT * FROM ledger WHERE run_id = ?", cloud, params=(run_id,))
    tel = pd.read_sql("SELECT * FROM telemetry_minute WHERE run_id = ?", cloud, params=(run_id,))
    ing = pd.read_sql("SELECT * FROM ingest_log WHERE run_id = ?", cloud, params=(run_id,))
    att = pd.read_sql("SELECT * FROM transmission_log WHERE run_id = ?", device.conn, params=(run_id,))

    m = led.merge(tel[["device_id", "event_time", "received_at"]], on=["device_id", "event_time"], how="left")
    arrived = m.received_at.notna()
    session = m.true_state != "idle"
    delay = (pd.to_datetime(m.received_at[arrived]) - pd.to_datetime(m.event_time[arrived])).dt.total_seconds() / 60

    print(f"\n=== {run_id} ===")
    print(f"minutes recorded          {len(led):,}")
    print(f"minutes arrived           {arrived.sum():,}  ({arrived.mean():.1%})")
    print(f"session minutes arrived   {(arrived & session).sum():,} / {session.sum():,}  ({arrived[session].mean():.1%})")
    print(f"link down minutes         {(led.link_up == 0).sum():,}")
    sd = delay[session[arrived]]
    print(f"delay p50 / p95 (min)     {delay.median():.0f} / {delay.quantile(0.95):.0f}   (session minutes only: {sd.median():.0f} / {sd.quantile(0.95):.0f})")
    print(f"duplicates                {int((ing.row_count - ing.rows_inserted).sum())}")
    print(f"send attempts             {len(att)}  (failed {int((att.result != 'ok').sum())}, manual {int(att.manual.sum())})")


if __name__ == "__main__":
    main()