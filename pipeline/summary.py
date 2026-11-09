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
