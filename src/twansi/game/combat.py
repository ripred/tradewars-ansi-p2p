from __future__ import annotations

import random
from typing import Any

from .balance import doctrine_modifier


def resolve_battle(attacker: dict[str, Any], defender: dict[str, Any], sector_id: int) -> dict[str, Any]:
    atk_mod = doctrine_modifier(attacker["doctrine"], defender["doctrine"])
    def_mod = doctrine_modifier(defender["doctrine"], attacker["doctrine"])

    atk_roll = random.randint(15, 40) * atk_mod + attacker["gas"] * 0.03 + attacker["ore"] * 0.01
    def_roll = random.randint(15, 40) * def_mod + defender["crystal"] * 0.03 + defender["ore"] * 0.01

    damage_to_def = max(5, int(atk_roll - def_roll * 0.45))
    damage_to_atk = max(5, int(def_roll - atk_roll * 0.45))

    attacker_hp = max(0, attacker["hp"] - damage_to_atk)
    defender_hp = max(0, defender["hp"] - damage_to_def)

    if defender_hp <= 0 and attacker_hp > 0:
        winner = attacker["player_id"]
    elif attacker_hp <= 0 and defender_hp > 0:
        winner = defender["player_id"]
    else:
        winner = attacker["player_id"] if atk_roll >= def_roll else defender["player_id"]

    summary = f"sector {sector_id}: {attacker['nick']} vs {defender['nick']} winner={winner[:8]}"
    return {
        "attacker": attacker["player_id"],
        "defender": defender["player_id"],
        "winner": winner,
        "damage_attacker": damage_to_atk,
        "damage_defender": damage_to_def,
        "attacker_hp": attacker_hp,
        "defender_hp": defender_hp,
        "sector_id": sector_id,
        "summary": summary,
    }
