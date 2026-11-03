"""Pipeline B: the device sends straight to the cloud every 15 minutes.

Rules (Excel rows 24 to 26):
- Every 15 minutes the device sends all rows that are not acked yet.
- A failed batch is retried every 15 minutes, up to 4 tries (60 minutes).
- After 4 failures the batch is 'failed', but its rows stay in the buffer
  and go out with the next batch once the link is back. No manual step.
"""
INTERVAL = 15
MAX_TRIES = 4


class PipelineB:
    def __init__(self, device, run_id):
        self.device = device
        self.run_id = run_id
        self.batch = {}    # device_id -> [batch_id, tries]
        self.count = {}    # device_id -> number of batches made

    def on_minute(self, device_id, minute_no, now, link_up, session_ended):
        if (minute_no + 1) % INTERVAL != 0:
            return
        if not self.device.unacked(device_id):
            return
        if device_id not in self.batch:
            n = self.count.get(device_id, 0) + 1
            self.count[device_id] = n
            self.batch[device_id] = [f"{self.run_id}-{device_id}-b{n:04d}", 0]
        batch_id, tries = self.batch[device_id]
        ok = self.device.send(device_id, batch_id, now, link_up)
        tries += 1
        if ok or tries >= MAX_TRIES:
            del self.batch[device_id]   # sent, or marked failed (rows stay in the buffer)
        else:
            self.batch[device_id][1] = tries