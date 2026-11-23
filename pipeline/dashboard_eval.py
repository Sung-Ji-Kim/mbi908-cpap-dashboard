
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
RESULTS = HERE / "results"
REFRESH = 15          # minutes
WATCH = 24 * 60       # minutes each minute is watched after it happens
STATES = ["therapy", "mask_off", "idle", "no_data"]


def mins(series):
    """ISO UTC text -> minutes since 1970 (int64)."""
    t = pd.to_datetime(series, utc=True)
    return ((t - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(minutes=1)).astype("int64")


def iso(m):
    return (pd.Timestamp("1970-01-01", tz="UTC") + pd.to_timedelta(np.asarray(m), unit="min")).strftime("%Y-%m-%dT%H:%M:00Z")


def n_refresh(a, b):
    """Number of refresh times R with a <= R < b (R on the 15-minute grid). Arrays."""
    a = np.asarray(a, dtype="int64"); b = np.asarray(b, dtype="int64")
    first = -(-a // REFRESH) * REFRESH                   # first grid point >= a
    return np.where(b > first, (b - 1 - first) // REFRESH + 1, 0)


def load(cloud, rid):
    led = pd.read_sql("SELECT device_id, event_time, true_state FROM ledger WHERE run_id = ?", cloud, params=(rid,))
    tel = pd.read_sql("SELECT device_id, event_time, raw_state, received_at FROM telemetry_minute WHERE run_id = ?",
                      cloud, params=(rid,))
    d = led.merge(tel, on=["device_id", "event_time"], how="left")
    d["m"] = mins(d.event_time)
    d["r"] = np.where(d.received_at.notna(), mins(d.received_at.fillna("1970-01-01T00:00:00Z")), np.iinfo("int64").max // 4)
    d["m"] = d["m"] + 1                                  # a minute can be shown once it has ended
    d["r"] = np.maximum(d["r"], d["m"])
    d["shown"] = d.raw_state.fillna(d.true_state)        # state once received (equals true_state)
    # nights run 12:00 to 12:00 Pacific/Auckland
    local = pd.to_datetime(d.event_time, utc=True).dt.tz_convert("Pacific/Auckland")
    d["night"] = (local - pd.Timedelta(hours=12)).dt.date
    d["f"] = d.groupby(["device_id", "night"]).r.transform("min")   # first arrival of any record of that night
    return d


def score(d, rule="known"):
    """Weighted confusion counts {(truth, shown): n} for the dashboard and the baseline view.

    rule="known"  (main result): while a record has not reached the cloud, the truth is no_data,
                  because nothing can be known about that minute yet.
    rule="actual" (secondary): the truth is the ledger state, except that a missing therapy or
                  mask-off minute is no_data. Used only for the hidden-state rate.
    """
    m, r, f, end = d.m.values, d.r.values, d.f.values, d.m.values + WATCH
    true_state = d.true_state.values
    if rule == "known":
        true_missing = np.full(len(d), "no_data")
    else:
        in_use = np.isin(true_state, ["therapy", "mask_off"])
        true_missing = np.where(in_use, "no_data", "idle")   # truth while the record is still missing

    before = n_refresh(m, np.minimum(r, end))            # refreshes before the record arrived
    after = n_refresh(np.maximum(r, m), end)             # refreshes after it arrived

    dash, base = {}, {}
    def add(cm, t, s, n):
        for tt, ss, nn in zip(t, s, n):
            if nn:
                cm[(tt, ss)] = cm.get((tt, ss), 0) + int(nn)

    # dashboard
    add(dash, true_missing, np.full(len(d), "no_data"), before)
    add(dash, true_state, true_state, after)

    # baseline: [m, f) whole night unseen -> no_data; [f, r) idle; [r, end) therapy or idle
    b1 = n_refresh(m, np.minimum(f, end))
    b2 = n_refresh(np.maximum(f, m), np.minimum(r, end))
    b3 = after
    shown_after = np.where(true_state == "therapy", "therapy", "idle")
    add(base, true_missing, np.full(len(d), "no_data"), b1)
    add(base, true_missing, np.full(len(d), "idle"), b2)
    add(base, true_state, shown_after, b3)
    return dash, base


def metrics(cm, prefix):
    out = {}
    tot_true = {s: sum(v for (t, _), v in cm.items() if t == s) for s in STATES}
    tot_shown = {s: sum(v for (_, x), v in cm.items() if x == s) for s in STATES}
    for s in ["no_data", "mask_off", "idle", "therapy"]:
        hit = cm.get((s, s), 0)
        out[f"{prefix}_{s}_precision"] = hit / tot_shown[s] if tot_shown[s] else np.nan
        out[f"{prefix}_{s}_recall"] = hit / tot_true[s] if tot_true[s] else np.nan
    not_nd = sum(v for (t, _), v in cm.items() if t != "no_data")
    false_nd = sum(v for (t, x), v in cm.items() if t != "no_data" and x == "no_data")
    out[f"{prefix}_false_no_data_rate"] = false_nd / not_nd if not_nd else np.nan
    return out


def state_rows(d, rid):
    """dashboard_state rows: first refresh after each minute, plus the correcting refresh."""
    first_r = -(-d.m.values // REFRESH) * REFRESH
    arrived = d.r.values < d.m.values + WATCH
    fix_r = -(-d.r.values // REFRESH) * REFRESH
    initial = np.where(d.r.values <= first_r, d.shown.values, "no_data")
    rows = pd.DataFrame({"run_id": rid, "device_id": d.device_id.values, "event_time": d.event_time.values,
                         "computed_at": iso(first_r), "state": initial})
    changed = (initial == "no_data") & arrived
    fix = pd.DataFrame({"run_id": rid, "device_id": d.device_id.values[changed], "event_time": d.event_time.values[changed],
                        "computed_at": iso(fix_r[changed]), "state": d.shown.values[changed]})
    return pd.concat([rows, fix], ignore_index=True)


def one_run(cloud, run):
    rid = run.run_id
    d = load(cloud, rid)
    dash, base = score(d, "known")
    row = {"run_id": rid, "pipeline": run.pipeline, "level": run.failure_level, "seed": run.seed}
    row.update(metrics(dash, "dash"))
    row.update(metrics(base, "summary"))
    # hidden-state rate: share of (minute, refresh) pairs where the dashboard shows no_data
    # although the patient was not using the device (an idle minute not received yet)
    dash_actual, _ = score(d, "actual")
    row["dash_hidden_state_rate"] = metrics(dash_actual, "x")["x_false_no_data_rate"]
    late = d[(d.r > d.m) & (d.r < d.m + WATCH)]
    corr = (-(-late.r // REFRESH) * REFRESH) - late.r
    row["correction_p50_min"] = corr.median() if len(corr) else 0.0
    row["correction_max_min"] = corr.max() if len(corr) else 0.0

    states = state_rows(d, rid)
    cloud.execute("DELETE FROM dashboard_state WHERE run_id = ?", (rid,))
    cloud.executemany("INSERT INTO dashboard_state VALUES (?, ?, ?, ?, ?)", states.itertuples(index=False, name=None))
    cloud.commit()
    return row


def main():
    cloud = sqlite3.connect(OUT / "cloud.db")
    runs = pd.read_sql("SELECT run_id, pipeline, failure_level, seed FROM experiment_run ORDER BY run_id", cloud)
    if len(sys.argv) > 1:
        runs = runs[runs.run_id.isin(sys.argv[1:])]
    rows = []
    for run in runs.itertuples():
        if not cloud.execute("SELECT 1 FROM ledger WHERE run_id = ? LIMIT 1", (run.run_id,)).fetchone():
            print(f"skip {run.run_id} (no ledger)")
            continue
        rows.append(one_run(cloud, run))
        r = rows[-1]
        print(f"{run.run_id:<16} no_data recall dash {r['dash_no_data_recall']:.3f} / summary {r['summary_no_data_recall']:.3f}  "
              f"false no-data dash {r['dash_false_no_data_rate']:.3f} / summary {r['summary_false_no_data_rate']:.3f}  "
              f"hidden {r['dash_hidden_state_rate']:.3f}  "
              f"correction p50 {r['correction_p50_min']:.0f} min")
    RESULTS.mkdir(exist_ok=True)
    per = pd.DataFrame(rows)
    per.to_csv(RESULTS / "srq2_per_seed.csv", index=False)

    keys = [c for c in per.columns if c.startswith(("dash_", "summary_", "correction_"))]
    g = per.groupby(["pipeline", "level"])[keys]
    summary = pd.concat({"median": g.median(), "q1": g.quantile(0.25), "q3": g.quantile(0.75)}, axis=1)
    summary.to_csv(RESULTS / "srq2_summary.csv")
    print(f"\nwrote {RESULTS / 'srq2_per_seed.csv'} ({len(per)} runs) and srq2_summary.csv")


if __name__ == "__main__":
    main()