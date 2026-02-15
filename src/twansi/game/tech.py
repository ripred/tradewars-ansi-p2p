from __future__ import annotations

from typing import Any

from twansi.state.store_sqlite import Store


TECH_DOMAINS = ("ship_hull", "weapons", "shields", "mining", "defense_grid")
MAX_TIER = 8


def tier_cost(level: int) -> dict[str, int]:
    nxt = level + 1
    return {
        "credits": 220 * nxt,
        "ore": 18 * nxt,
        "gas": 14 * nxt,
        "crystal": 12 * nxt,
    }


def upgrade_tech(store: Store, player_id: str, domain: str) -> dict[str, Any]:
    domain = domain.strip().lower()
    if domain not in TECH_DOMAINS:
        raise ValueError("invalid tech domain")

    p = store.get_player(player_id)
    if not p:
        raise ValueError("player missing")

    levels = store.get_tech_levels(player_id)
    cur = int(levels.get(domain, 0))
    if cur >= MAX_TIER:
        raise ValueError("already at max tier")

    cost = tier_cost(cur)
    if int(p["credits"]) < cost["credits"] or int(p["ore"]) < cost["ore"] or int(p["gas"]) < cost["gas"] or int(p["crystal"]) < cost["crystal"]:
        raise ValueError("insufficient resources for upgrade")

    store.update_player_resources(
        player_id,
        credits=-cost["credits"],
        ore=-cost["ore"],
        gas=-cost["gas"],
        crystal=-cost["crystal"],
    )
    store.set_tech_level(player_id, domain, cur + 1)

    return {
        "domain": domain,
        "from_tier": cur,
        "to_tier": cur + 1,
        "cost": cost,
    }


def tech_effects(levels: dict[str, int]) -> dict[str, float]:
    return {
        "combat_bonus": 1.0 + 0.05 * levels.get("weapons", 0),
        "shield_bonus": 1.0 + 0.05 * levels.get("shields", 0),
        "mining_bonus": 1.0 + 0.06 * levels.get("mining", 0),
        "hull_bonus": 1.0 + 0.07 * levels.get("ship_hull", 0),
        "defense_bonus": 1.0 + 0.06 * levels.get("defense_grid", 0),
    }
