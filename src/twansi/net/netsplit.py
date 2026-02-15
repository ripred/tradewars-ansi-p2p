from __future__ import annotations

import time


class NetsplitTracker:
    def __init__(self):
        self.last_peer_seen_ts: float = time.time()
        self.split_active: bool = False
        self.merge_count: int = 0

    def on_peer_seen(self) -> None:
        now = time.time()
        if self.split_active:
            self.split_active = False
            self.merge_count += 1
        self.last_peer_seen_ts = now

    def tick(self, peer_count: int, timeout: float = 20.0) -> None:
        now = time.time()
        if peer_count == 0 and (now - self.last_peer_seen_ts) > timeout:
            self.split_active = True
