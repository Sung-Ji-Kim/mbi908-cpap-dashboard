"""Reads cloud.db and the device files, writes one row per run to results/per_seed.csv."""
import sqlite3
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "output"
RESULTS = Path(__file__).resolve().parent / "results"


def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def minutes(a, b):
    return (pd.to_datetime(a) - pd.to_datetime(b)).dt.total_seconds() / 60


def one_run(cloud, run):
    rid = run.run_id
    led = pd.read_sql("SELECT * FROM ledger WHERE run_id = ?", cloud, params=(rid,))
    tel = pd.read_sql("SELECT device_id, event_time, received_at FROM telemetry_minute WHERE run_id = ?",
                      cloud, params=(rid,))
    ing = pd.read_sql("SELECT row_count, rows_inserted FROM ingest_log WHERE run_id = ?", cloud, params=(rid,))
    att = pd.read_sql("SELECT * FROM transmission_log WHERE run_id = ?",
                      ro(OUT / f"device_{rid}.db"), params=(rid,))

    # 1) delay and completeness, session minutes only (idle minutes carry no data)
    s = led[led.true_state != "idle"].merge(tel, on=["device_id", "event_time"], how="left")
    delay = minutes(s.received_at, s.event_time)          # NaN = never arrived
    row = {"run_id": rid, "pipeline": run.pipeline, "level": run.failure_level, "seed": run.seed,
           "delay_p50_min": delay.median(), "delay_p95_min": delay.quantile(0.95)}
    for h in (1, 12, 24):
        row[f"complete_{h}h"] = (delay <= h * 60).mean()
    row["complete_end"] = delay.notna().mean()

    # 2) duplicates
    row["dup_rate"] = (ing.row_count - ing.rows_inserted).sum() / max(ing.row_count.sum(), 1)

    # 3) recovery: a failure episode starts at a failed attempt and ends at the next ok attempt
    ok_times, eps = [], []
    for dev, g in att.sort_values("attempt_id").groupby("device_id"):
        up = led[(led.device_id == dev) & (led.link_up == 1)].event_time.sort_values()
        open_fail = None
        for a in g.itertuples():
            if a.result != "ok" and open_fail is None:
                open_fail = a.attempted_at
            elif a.result == "ok" and open_fail is not None:
                back = up[up >= open_fail]               # first minute the link is up again
                back = back.iloc[0] if len(back) else a.attempted_at
                eps.append({"recovered": True, "manual": a.manual,
                            "rec_min": minutes(pd.Series([a.attempted_at]), pd.Series([back]))[0]})
                open_fail = None
        if open_fail is not None:
            eps.append({"recovered": False, "manual": 0, "rec_min": float("nan")})
    eps = pd.DataFrame(eps, columns=["recovered", "manual", "rec_min"])
    row["fail_episodes"] = len(eps)
    row["recovered_no_manual"] = ((eps.recovered) & (eps.manual == 0)).mean() if len(eps) else float("nan")
    row["recovery_p50_min"] = eps.rec_min.median()
    row["manual_interventions"] = int(att.manual.sum())
    return row


def main():
    RESULTS.mkdir(exist_ok=True)
    cloud = ro(OUT / "cloud.db")
    runs = pd.read_sql("SELECT * FROM experiment_run ORDER BY pipeline, failure_level, seed", cloud)
    rows = [one_run(cloud, r) for r in runs.itertuples() if (OUT / f"device_{r.run_id}.db").exists()]
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "per_seed.csv", index=False)
    print(df.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
