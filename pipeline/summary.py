"""Median and IQR (Q1 to Q3) for each pipeline x level, from results/per_seed.csv."""
from pathlib import Path

import pandas as pd

RESULTS = Path(__file__).resolve().parent / "results"
COLS = ["delay_p50_min", "delay_p95_min", "complete_1h", "complete_12h", "complete_24h",
        "dup_rate", "recovered_no_manual", "recovery_p50_min", "manual_interventions"]
ORDER = ["None", "Low", "Medium", "High"]

# keep_default_na=False: otherwise pandas reads the level "None" as a missing value
df = pd.read_csv(RESULTS / "per_seed.csv", keep_default_na=False, na_values=[""])
rows = []
for (p, lv), g in df.groupby(["pipeline", "level"]):
    r = {"pipeline": p, "level": lv, "n": len(g)}
    for c in COLS:
        q1, med, q3 = g[c].quantile([0.25, 0.5, 0.75])
        r[c] = f"{med:.2f} [{q1:.2f}-{q3:.2f}]" if pd.notna(med) else "n/a"
    rows.append(r)
out = pd.DataFrame(rows)
out["level"] = pd.Categorical(out.level, ORDER, ordered=True)
out = out.sort_values(["pipeline", "level"])
out.to_csv(RESULTS / "summary_median_iqr.csv", index=False)
print(out.to_string(index=False))

# ---- Paired comparison: same seed = same outages for A and B ----
# For each level and seed: difference = B minus A. Report the median and IQR of the
# differences and how many of the seeds B did better, worse or the same.
LOWER_BETTER = ["delay_p50_min", "delay_p95_min", "dup_rate", "recovery_p50_min", "manual_interventions",
                "dash_hidden_state_rate"]
HIGHER_BETTER = ["complete_1h", "complete_12h", "complete_24h", "complete_end", "recovered_no_manual",
                 "dash_no_data_recall", "dash_mask_off_recall"]

srq2 = pd.read_csv(RESULTS / "srq2_per_seed.csv", keep_default_na=False, na_values=[""])
both = df.merge(srq2.drop(columns=["run_id"]), on=["pipeline", "level", "seed"], how="left")
a = both[both.pipeline == "A"].set_index(["level", "seed"])
b = both[both.pipeline == "B"].set_index(["level", "seed"])

pair_rows = []
for c in LOWER_BETTER + HIGHER_BETTER:
    diff = (b[c] - a[c]).dropna()          # one value per (level, seed) pair
    for lv, d in diff.groupby(level="level"):
        q1, med, q3 = d.quantile([0.25, 0.5, 0.75])
        better = (d < 0) if c in LOWER_BETTER else (d > 0)
        same = d.abs() < 1e-9
        pair_rows.append({"metric": c, "level": lv, "pairs": len(d),
                          "diff_B_minus_A": f"{med:.3f} [{q1:.3f}, {q3:.3f}]",
                          "B_better": int((better & ~same).sum()), "same": int(same.sum()),
                          "B_worse": int((~better & ~same).sum())})
pairs = pd.DataFrame(pair_rows)
pairs["level"] = pd.Categorical(pairs.level, ORDER, ordered=True)
pairs["metric"] = pd.Categorical(pairs.metric, LOWER_BETTER + HIGHER_BETTER, ordered=True)
pairs = pairs.sort_values(["metric", "level"])
pairs.to_csv(RESULTS / "paired_B_vs_A.csv", index=False)
print("\nPaired comparison (B minus A, median [Q1, Q3]; counts are seeds)")
print(pairs.to_string(index=False))