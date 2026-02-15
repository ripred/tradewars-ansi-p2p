from __future__ import annotations

import random

from twansi.state.store_sqlite import Store


def ensure_map(store: Store, sectors: int = 64) -> None:
    for s in range(1, sectors + 1):
        richness = random.randint(1, 8)
        danger = random.randint(1, 10)
        store.ensure_sector(s, richness, danger)

    # Create a sparse-but-connected warp graph (undirected) for navigation.
    # Ensure ring connectivity, then add random extra warps.
    for s in range(1, sectors + 1):
        nxt = s + 1 if s < sectors else 1
        store.add_warp(s, nxt)
        store.add_warp(nxt, s)

    extra = max(sectors, int(sectors * 1.6))
    for _ in range(extra):
        a = random.randint(1, sectors)
        b = random.randint(1, sectors)
        if a == b:
            continue
        store.add_warp(a, b)
        store.add_warp(b, a)
