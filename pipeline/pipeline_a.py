"""Pipeline A: the current SleepStyle app. Device -> phone (Bluetooth, Bumble) -> cloud.

Rules (Excel rows 20 to 22 and 28):
- When a session ends (the user presses Stop), the app syncs once.
- If the link is down at Stop, that sync fails.
- When the link comes back after a failed sync, the app reconnects on its own
  (using the saved pairing keys) with probability 0.5. Otherwise the data waits
  for the next Stop.
- After 3 failed syncs in a row, the bond is treated as broken: the pairing keys
  are deleted and the user re-pairs by hand (manual = 1) once the link is back.
Every sync that happens moves the rows over a real Bumble BLE connection.
"""
import random

from ble_link import BleLink

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
        self.ble = {}         # device_id -> BleLink (paired once at setup)

    def _link(self, device_id):
        if device_id not in self.ble:
            link = BleLink(len(self.ble) + 1)
            link.pair()       # first pairing when the patient sets up the app
            self.ble[device_id] = link
        return self.ble[device_id]

    def _batch_id(self, device_id):
        n = self.count.get(device_id, 0) + 1
        self.count[device_id] = n
        return f"{self.run_id}-{device_id}-a{n:04d}"

    def _sync(self, device_id, now, link_up, manual=0):
        ble = self._link(device_id)
        if manual:
            ble.pair()
        return self.device.send(device_id, self._batch_id(device_id), now, link_up,
                                manual=manual, carry=ble.transfer)

    def on_minute(self, device_id, minute_no, now, link_up, session_ended):
        came_back = link_up and not self.was_up.get(device_id, True)
        self.was_up[device_id] = link_up

        if session_ended:
            if self._sync(device_id, now, link_up):
                self.fails[device_id] = 0
                self.waiting[device_id] = False
            else:
                self.fails[device_id] = self.fails.get(device_id, 0) + 1
                self.waiting[device_id] = True
                if self.fails[device_id] >= REPAIR_AFTER:
                    self._link(device_id).unpair()
            return

        if link_up and self.waiting.get(device_id):
            if self.fails.get(device_id, 0) >= REPAIR_AFTER:
                self._sync(device_id, now, True, manual=1)
                self.fails[device_id] = 0
                self.waiting[device_id] = False
            elif came_back and self.rng.random() < CATCH_UP_P:
                self._sync(device_id, now, True)
                self.fails[device_id] = 0
                self.waiting[device_id] = False