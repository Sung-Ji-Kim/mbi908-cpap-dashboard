"""Pipeline A: the current SleepStyle app. Device -> phone (Bluetooth) -> cloud.

Rules (Excel rows 20 to 22 and 28), rule-based version.
Bumble will later replace the link check with a real Bluetooth connection.
- When a session ends (the user presses Stop), the app syncs once.
- If the link is down at Stop, that sync fails.
- When the link comes back after a failed sync, the app catches up
  on its own with probability 0.5. Otherwise the data waits for the next Stop.
- After 3 failed syncs in a row, the user re-pairs the device by hand
  (manual = 1) as soon as the link is back.
"""
import random

CATCH_UP_P = 0.5
REPAIR_AFTER = 3


class PipelineA:
    def __init__(self, device, run_id, seed):
        self.device = device
        self.run_id = run_id
        self.rng = random.Random(seed + 1000)
        self.fails = {}       # device_id -> failed syncs in a row
        self.waiting = {}     # device_id -> True after a failed sync
        self.was_up = {}      # device_id -> link state in the previous minute
        self.count = {}

    def _batch_id(self, device_id):
        n = self.count.get(device_id, 0) + 1
        self.count[device_id] = n
        return f"{self.run_id}-{device_id}-a{n:04d}"

    def on_minute(self, device_id, minute_no, now, link_up, session_ended):
        came_back = link_up and not self.was_up.get(device_id, True)
        self.was_up[device_id] = link_up

        if session_ended:
            ok = self.device.send(device_id, self._batch_id(device_id), now, link_up)
            if ok:
                self.fails[device_id] = 0
                self.waiting[device_id] = False
            else:
                self.fails[device_id] = self.fails.get(device_id, 0) + 1
                self.waiting[device_id] = True
            return

        if link_up and self.waiting.get(device_id):
            if self.fails.get(device_id, 0) >= REPAIR_AFTER:
                self.device.send(device_id, self._batch_id(device_id), now, True, manual=1)
                self.fails[device_id] = 0
                self.waiting[device_id] = False
            elif came_back:
                if self.rng.random() < CATCH_UP_P:
                    self.device.send(device_id, self._batch_id(device_id), now, True)
                    self.fails[device_id] = 0
                    self.waiting[device_id] = False