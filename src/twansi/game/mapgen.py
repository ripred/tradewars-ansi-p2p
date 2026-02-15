from __future__ import annotations

import random

from twansi.state.store_sqlite import Store


def ensure_map(store: Store, sectors: int = 64) -> None:
    for s in range(1, sectors + 1):
        richness = random.randint(1, 8)
        danger = random.randint(1, 10)
        store.ensure_sector(s, richness, danger)
