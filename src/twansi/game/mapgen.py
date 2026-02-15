from __future__ import annotations

import hashlib
import random
from typing import Any

from twansi.state.store_sqlite import Store


def _seed64(*parts: Any) -> int:
    s = "|".join(str(p) for p in parts)
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False)


def ensure_map(store: Store, sectors: int = 64, shard: str = "alpha", epoch: int = 1) -> None:
    # Deterministic world gen is critical for a serverless mesh: every node in the same shard/epoch
    # must derive the same topology (sectors/warps/ports) without coordination.
    base_seed = _seed64("twansi-map", shard, epoch, sectors)
    for s in range(1, sectors + 1):
        srng = random.Random(_seed64("twansi-sector", base_seed, s))
        richness = srng.randint(1, 8)
        danger = srng.randint(1, 10)
        store.ensure_sector(s, richness, danger)

    # Create a sparse-but-connected warp graph (undirected) for navigation.
    # Ensure ring connectivity, then add random extra warps.
    for s in range(1, sectors + 1):
        nxt = s + 1 if s < sectors else 1
        store.add_warp(s, nxt)
        store.add_warp(nxt, s)

    extra = max(sectors, int(sectors * 1.6))
    wrng = random.Random(_seed64("twansi-warps", base_seed))
    for _ in range(extra):
        a = wrng.randint(1, sectors)
        b = wrng.randint(1, sectors)
        if a == b:
            continue
        store.add_warp(a, b)
        store.add_warp(b, a)

    # Seed ports across the galaxy (roughly 35% of sectors).
    prng = random.Random(_seed64("twansi-ports", base_seed))
    for s in range(1, sectors + 1):
        if prng.random() < 0.35:
            srng = random.Random(_seed64("twansi-port", base_seed, s))
            pclass = srng.choice(["BBS", "BSS", "SBB", "SSB", "BSB", "SBS"])
            richness = int((store.get_sector(s) or {}).get("richness", 4))
            danger = int((store.get_sector(s) or {}).get("danger", 5))
            base = 300 + richness * 70 - danger * 12
            base = max(120, base)
            weights = {"ore": 1.0, "gas": 1.0, "crystal": 1.0}
            if pclass[0] == "B":
                weights["ore"] *= 0.7
            else:
                weights["ore"] *= 1.25
            if pclass[1] == "B":
                weights["gas"] *= 0.7
            else:
                weights["gas"] *= 1.25
            if pclass[2] == "B":
                weights["crystal"] *= 0.7
            else:
                weights["crystal"] *= 1.25
            stock = {res: int(base * weights[res]) + srng.randint(0, 60) for res in ("ore", "gas", "crystal")}
            store.ensure_port(s, port_class=pclass, stock=stock)
