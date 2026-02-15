from __future__ import annotations

import random
from typing import Any

from twansi.state.store_sqlite import Store


RESOURCES = ("ore", "gas", "crystal")


def market_snapshot(store: Store) -> dict[str, Any]:
    return {
        "prices": store.get_market_prices(),
    }


def drift_market(store: Store) -> dict[str, int]:
    prices = store.get_market_prices()
    out: dict[str, int] = {}
    for res in RESOURCES:
        base = int(prices.get(res, 5))
        shift = random.randint(-1, 1)
        nxt = max(1, base + shift)
        store.update_market_price(res, nxt)
        out[res] = nxt
    return out
