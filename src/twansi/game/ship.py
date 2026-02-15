from __future__ import annotations

from typing import Any

from twansi.game.tech import tech_effects


def ship_stats(player: dict[str, Any], tech_levels: dict[str, int]) -> dict[str, Any]:
    fx = tech_effects(tech_levels)
    hull_tier = int(tech_levels.get("ship_hull", 0))
    mining_tier = int(tech_levels.get("mining", 0))

    base_hp = 100 + hull_tier * 18
    max_hp = int(round(base_hp * fx["hull_bonus"]))

    cargo_capacity = 320 + hull_tier * 45 + mining_tier * 30
    cargo_used = int(player.get("ore", 0)) + int(player.get("gas", 0)) + int(player.get("crystal", 0))
    overload = max(0, cargo_used - cargo_capacity)

    scan_range = 40 + hull_tier * 6 + int(tech_levels.get("shields", 0)) * 2
    speed = 1.0 + 0.08 * hull_tier
    if overload > 0:
        speed *= max(0.55, 1.0 - overload / max(1, cargo_capacity) * 0.6)

    return {
        "max_hp": max_hp,
        "shield_max": int(round((40 + int(tech_levels.get(\"shields\", 0)) * 20) * fx[\"shield_bonus\"])),
        "weapon_power": round(1.0 + 0.07 * int(tech_levels.get(\"weapons\", 0)), 3),
        "defense_power": round(1.0 + 0.06 * int(tech_levels.get(\"defense_grid\", 0)) + 0.03 * int(tech_levels.get(\"shields\", 0)), 3),
        "cargo_capacity": cargo_capacity,
        "cargo_used": cargo_used,
        "cargo_overload": overload,
        "scan_range": scan_range,
        "speed": round(speed, 3),
        "effects": fx,
    }
