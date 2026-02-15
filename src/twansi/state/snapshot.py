from __future__ import annotations

import hashlib
import json
from typing import Any

from .store_sqlite import Store


def snapshot_hash(store: Store) -> str:
    players = store.list_players()
    battles = store.recent_battles(50)
    blob = json.dumps({"players": players, "battles": battles}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def snapshot_payload(store: Store) -> dict[str, Any]:
    return {
        "players": store.list_players(),
        "battles": store.recent_battles(100),
        "hash": snapshot_hash(store),
    }
