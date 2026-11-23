
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
RESULTS = HERE / "results"
VALUES = [0.3, 0.7]
LEVELS = ["Medium", "High"]
SEEDS = range(1, 6)
# metric -> True if lower is better
METRICS = {"delay_p50_min": True, "delay_p95_min": True, "complete_24h": False,
           "recovered_no_manual": False, "manual_interventions": True}

if "compare" not in sys.argv:
    for p in VALUES:
        for level in LEVELS:
            for seed in SEEDS:
                run_id = f"A-{level}-s{seed:02d}-cu{p:.1f}"
                if (OUT / f"device_{run_id}.db").exists():
                    print(f"skip {run_id}")
                    continue
                t0 = time.time()
                subprocess.run([sys.executable, str(HERE / "run.py"), "--pipeline", "A", "--level", level,
                                "--seed", str(seed), "--catch-up", str(p)], check=True, stdout=subprocess.DEVNULL)
                print(f"done {run_id}  ({time.time() - t0:.0f}s)")
    subprocess.run([sys.executable, str(HERE / "metrics.py"), "sens"], check=True, stdout=subprocess.DEVNULL)

main = pd.read_csv(RESULTS / "per_seed.csv", keep_default_na=False, na_values=[""])
sens = pd.read_csv(RESULTS / "per_seed_sens.csv", keep_default_na=False, na_values=[""])
main = main[main.level.isin(LEVELS) & main.seed.isin(SEEDS)]
sens["catch_up"] = sens.run_id.str.extract(r"-cu([0-9.]+)$")[0].astype(float)
a = pd.concat([main[main.pipeline == "A"].assign(catch_up=0.5), sens])
b = main[main.pipeline == "B"].set_index(["level", "seed"])

rows = []
for (p, level), g in a.groupby(["catch_up", "level"]):
    g = g.set_index(["level", "seed"])
    for c, lower in METRICS.items():
        d = (b[c] - g[c]).dropna()
        same = d.abs() < 1e-9
        better = (d < 0) if lower else (d > 0)
        rows.append({"metric": c, "level": level, "A_catch_up": p,
                     "A_median": round(g[c].median(), 3), "B_median": round(b.loc[level, c].median(), 3),
                     "B_better": int((better & ~same).sum()), "same": int(same.sum()),
                     "B_worse": int((~better & ~same).sum())})
out = pd.DataFrame(rows)
out["metric"] = pd.Categorical(out.metric, list(METRICS), ordered=True)
out["level"] = pd.Categorical(out.level, LEVELS, ordered=True)
out = out.sort_values(["metric", "level", "A_catch_up"])
out.to_csv(RESULTS / "sensitivity_catch_up.csv", index=False)
print("\nSensitivity: A catch-up probability 0.3 / 0.5 / 0.7 vs B (seeds 1-5; counts are seeds)")
print(out.to_string(index=False))