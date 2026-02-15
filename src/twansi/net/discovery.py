from __future__ import annotations

import asyncio
import random
from typing import Callable


class DiscoveryScheduler:
    def __init__(self, interval: float = 8.0):
        self.interval = interval
        self._running = False

    async def run(self, announce_cb: Callable[[], None]) -> None:
        self._running = True
        while self._running:
            announce_cb()
            jitter = random.uniform(-1.5, 1.5)
            await asyncio.sleep(max(2.0, self.interval + jitter))

    def stop(self) -> None:
        self._running = False
