from __future__ import annotations

from typing import Any

from twansi.state.store_sqlite import Store


TECH_DOMAINS = ("ship_hull", "weapons", "shields", "mining", "defense_grid")
MAX_TIER = 8


def tech_tree_spec() -> dict[str, dict[str, Any]]:
    # Tiered tree with simple cross-domain gating to force meaningful progression paths.
    return {
        "ship_hull": {
            "name": "Ship Hull",
            "max_tier": 8,
            "requires": {},
        },
        "weapons": {
            "name": "Weapons",
            "max_tier": 8,
            "requires": {"ship_hull": 1},
        },
        "shields": {
            "name": "Shields",
            "max_tier": 8,
            "requires": {"ship_hull": 1},
        },
        "mining": {
            "name": "Mining",
            "max_tier": 8,
            "requires": {},
        },
        "defense_grid": {
            "name": "Defense Grid",
            "max_tier": 8,
            "requires": {"ship_hull": 2, "shields": 1},
        },
    }


def tier_cost(level: int) -> dict[str, int]:
    nxt = level + 1
    # costs rise superlinearly to preserve long-term multiplayer economy pressure.
    cost_mult = 1.0 + (nxt * 0.12)
    return {
        "credits": int((220 * nxt) * cost_mult),
        "ore": int((18 * nxt) * cost_mult),
        "gas": int((14 * nxt) * cost_mult),
        "crystal": int((12 * nxt) * cost_mult),
    }


def can_upgrade(levels: dict[str, int], domain: str, next_tier: int) -> tuple[bool, str]:
    spec = tech_tree_spec().get(domain)
    if not spec:
        return False, "invalid tech domain"
    if next_tier > int(spec.get("max_tier", MAX_TIER)):
        return False, "already at max tier"
    requires: dict[str, int] = dict(spec.get("requires", {}))
    for dep, min_tier in requires.items():
        if int(levels.get(dep, 0)) < int(min_tier):
            return False, f"requires {dep} tier {min_tier}+"
    # Additional gating for combat/defense paths: advanced tiers require hull progression.
    if domain in {"weapons", "shields", "defense_grid"} and int(levels.get("ship_hull", 0)) < max(1, next_tier - 1):
        return False, f"requires ship_hull tier {max(1, next_tier - 1)}+"
    return True, ""


def upgrade_tech(store: Store, player_id: str, domain: str) -> dict[str, Any]:
    domain = domain.strip().lower()
    if domain not in TECH_DOMAINS:
        raise ValueError("invalid tech domain")

    p = store.get_player(player_id)
    if not p:
        raise ValueError("player missing")

    levels = store.get_tech_levels(player_id)
    cur = int(levels.get(domain, 0))
    next_tier = cur + 1
    allowed, reason = can_upgrade(levels, domain, next_tier)
    if not allowed:
        raise ValueError(reason)

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
        "requires": tech_tree_spec()[domain].get("requires", {}),
    }


def tech_effects(levels: dict[str, int]) -> dict[str, float]:
    return {
        "combat_bonus": 1.0 + 0.06 * levels.get("weapons", 0),
        "shield_bonus": 1.0 + 0.055 * levels.get("shields", 0),
        "mining_bonus": 1.0 + 0.07 * levels.get("mining", 0),
        "hull_bonus": 1.0 + 0.08 * levels.get("ship_hull", 0),
        "defense_bonus": 1.0 + 0.065 * levels.get("defense_grid", 0),
    }
