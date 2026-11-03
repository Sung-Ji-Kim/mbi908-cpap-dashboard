"""
Network outage schedule for one experiment.

Levels (from the Excel sheet, design assumptions):
  None   0 outages per night
  Low    1 outage,      5 to  15 minutes
  Medium 2 to 3,       20 to  60 minutes each
  High   1 to 2,       90 to 240 minutes each

The same outages apply to all 5 devices, and the same seed gives the same
outages for Pipeline A and Pipeline B. Outages start between 21:00 and 11:00
local time (assumption: this window covers every patient's sleep).
"""
import random

LEVELS = {
    "None":   {"count": (0, 0), "length": (0, 0)},
    "Low":    {"count": (1, 1), "length": (5, 15)},
    "Medium": {"count": (2, 3), "length": (20, 60)},
    "High":   {"count": (1, 2), "length": (90, 240)},
}
START_WINDOW = (540, 1380)   # minutes from 12:00 -> 21:00 to 11:00


def build_outages(level, seed, nights=7):
    """Returns {night: set of minute indexes (0-1439) when the link is down}."""
    rule = LEVELS[level]
    rng = random.Random(seed)
    down = {}
    for night in range(1, nights + 1):
        minutes = set()
        for _ in range(rng.randint(*rule["count"])):
            length = rng.randint(*rule["length"])
            start = rng.randint(*START_WINDOW)
            minutes.update(range(start, min(start + length, 1440)))
        down[night] = minutes
    return down







