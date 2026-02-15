from __future__ import annotations

import hashlib
from typing import Any

from twansi.state.store_sqlite import Store


RESOURCES = ("ore", "gas", "crystal")
BASE = {"ore": 5, "gas": 6, "crystal": 8}


def market_snapshot(store: Store) -> dict[str, Any]:
    return {
        "prices": store.get_market_prices(),
    }


def _det_shift(store: Store, res: str, slot: int) -> int:
    # Deterministic per shard+epoch+resource+time-slot. Prevents economic divergence/exploits in a mesh.
    s = f"twansi-market|{store.world_shard}|{store.world_epoch}|{slot}|{res}"
    h = hashlib.sha256(s.encode("utf-8")).digest()
    # Map to -2..2
    return (h[0] % 5) - 2


def drift_market(store: Store, now_ts: float) -> dict[str, int]:
    slot = int(now_ts // 60)
    out: dict[str, int] = {}
    for res in RESOURCES:
        base = int(BASE.get(res, 5))
        shift = _det_shift(store, res, slot)
        nxt = max(1, base + shift)
        store.update_market_price(res, nxt)
        out[res] = nxt
    return out
