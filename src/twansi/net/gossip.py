from __future__ import annotations

import time
from collections import deque
from typing import Any


class GossipBuffer:
    def __init__(self, max_items: int = 5000):
        self.items: deque[tuple[str, float, dict[str, Any]]] = deque(maxlen=max_items)
        self.seen_ids: set[str] = set()

    def add(self, event_id: str, payload: dict[str, Any]) -> bool:
        if event_id in self.seen_ids:
            return False
        self.seen_ids.add(event_id)
        self.items.append((event_id, time.time(), payload))
        if len(self.seen_ids) > 20000:
            # prune set lazily using deque contents
            self.seen_ids = {eid for eid, _, _ in self.items}
        return True

    def recent(self, max_age: float = 30.0, limit: int = 100) -> list[dict[str, Any]]:
        cutoff = time.time() - max_age
        out: list[dict[str, Any]] = []
        for eid, ts, payload in reversed(self.items):
            if ts < cutoff:
                break
            out.append({"event_id": eid, "payload": payload})
            if len(out) >= limit:
                break
        return list(reversed(out))
