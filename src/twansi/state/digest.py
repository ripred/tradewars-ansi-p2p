from __future__ import annotations

from collections import Counter
from typing import Any

from .store_sqlite import Store


def build_offline_digest(store: Store, player_id: str) -> dict[str, Any]:
    cursor = store.get_digest_cursor(player_id)
    events = store.events_since(cursor)
    if not events:
        return {
            "new_events": 0,
            "credits_delta": 0,
            "ore_delta": 0,
            "gas_delta": 0,
            "crystal_delta": 0,
            "battles": 0,
            "wins": 0,
            "losses": 0,
            "conquests": 0,
            "damage_taken": 0,
            "event_types": {},
        }

    stats = Counter()
    credits = ore = gas = crystal = conquests = damage_taken = wins = losses = battles = 0
    for e in events:
        et = e["event_type"]
        pl = e["payload"]
        stats[et] += 1
        if et == "resource_tick" and pl.get("player_id") == player_id:
            credits += int(pl.get("credits", 0))
            ore += int(pl.get("ore", 0))
            gas += int(pl.get("gas", 0))
            crystal += int(pl.get("crystal", 0))
        if et == "battle":
            battles += 1
            if pl.get("attacker") == player_id or pl.get("defender") == player_id:
                if pl.get("winner") == player_id:
                    wins += 1
                else:
                    losses += 1
                damage_taken += int(pl.get("damage_taken_by_player", 0))
        if et == "sector_claim" and pl.get("player_id") == player_id:
            conquests += 1

    store.set_digest_cursor(player_id, events[-1]["id"])
    return {
        "new_events": len(events),
        "credits_delta": credits,
        "ore_delta": ore,
        "gas_delta": gas,
        "crystal_delta": crystal,
        "battles": battles,
        "wins": wins,
        "losses": losses,
        "conquests": conquests,
        "damage_taken": damage_taken,
        "event_types": dict(stats),
    }
