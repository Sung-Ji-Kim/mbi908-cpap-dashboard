import random
from datetime import datetime, timedelta, timezone


def make_night(rng, start, minutes):
    states = ["no_session"] * minutes

    session_start = rng.randint(0, 15)       # minutes before the mask goes on
    for m in range(session_start, minutes):
        states[m] = "therapy"

    for _ in range(rng.randint(0, 3)):       # 0 to 3 mask-off episodes
        length = rng.randint(3, 20)
        first = rng.randint(session_start, minutes - length)
        for m in range(first, first + length):
            states[m] = "mask_off"

    rows = []
    for m in range(minutes):
        t = start + timedelta(minutes=m)
        rows.append((t.strftime("%Y-%m-%dT%H:%M:%SZ"), states[m]))
    return rows

def make_records(rng, device_id, rows):
    records = []
    session = f"{device_id}_{rows[0][0][:10]}"   # one session id per night
    for event_time, state in rows:
        if state == "no_session":
            continue                              # the device sends nothing
        if state == "therapy":
            leak = rng.uniform(5, 20)
        else:
            leak = rng.uniform(40, 60)            # mask off = high leak
        pressure = rng.gauss(10, 0.5)
        oa = 1 if rng.random() < 0.02 else 0
        ca = 1 if rng.random() < 0.01 else 0
        h = 1 if rng.random() < 0.03 else 0
        records.append((event_time, "on", session, round(pressure, 1), round(leak, 1), oa, ca, h))
    return records

if __name__ == "__main__":
    from collections import Counter
    start = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    rows = make_night(random.Random(3), start, 480)
    print(Counter(s for _, s in rows))
    records = make_records(random.Random("3-meas"), "d1", rows)
    print(len(records))
    print(records[0])
    print(records[-1])
    print("leak max:", max(r[4] for r in records), "leak min:", min(r[4] for r in records))