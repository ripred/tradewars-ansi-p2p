from __future__ import annotations

import random
from typing import Any

from twansi.game.balance import doctrine_modifier


def resolve_battle_v2(
    attacker: dict[str, Any],
    defender: dict[str, Any],
    sector: dict[str, Any] | None,
    atk_ship: dict[str, Any],
    def_ship: dict[str, Any],
) -> dict[str, Any]:
    sector_id = int(attacker.get("sector", 1))
    owner = str((sector or {}).get("owner_player_id") or "")
    defense_level = int((sector or {}).get("defense_level", 0) or 0)

    atk_mod = doctrine_modifier(str(attacker.get("doctrine", "assault")), str(defender.get("doctrine", "assault")))
    def_mod = doctrine_modifier(str(defender.get("doctrine", "assault")), str(attacker.get("doctrine", "assault")))

    atk_weapon = float(atk_ship.get("weapon_power", 1.0))
    def_weapon = float(def_ship.get("weapon_power", 1.0))
    atk_defense = float(atk_ship.get("defense_power", 1.0))
    def_defense = float(def_ship.get("defense_power", 1.0))

    sector_bonus = 1.0
    if owner and owner == str(defender.get("player_id", "")):
        sector_bonus = min(1.25, 1.0 + 0.04 * defense_level)

    atk_roll = (random.randint(18, 44) * atk_mod) * atk_weapon + float(attacker.get("gas", 0)) * 0.02
    def_roll = (random.randint(18, 44) * def_mod) * def_weapon * sector_bonus + float(defender.get("crystal", 0)) * 0.02

    # Damage amounts (pre-mitigation)
    dmg_to_def = max(6, int(atk_roll - def_roll * 0.35))
    dmg_to_atk = max(6, int(def_roll - atk_roll * 0.35))

    # Apply defense mitigation
    dmg_to_def = max(1, int(dmg_to_def / max(0.5, def_defense)))
    dmg_to_atk = max(1, int(dmg_to_atk / max(0.5, atk_defense)))

    def_shield = int(defender.get("shield", 0))
    atk_shield = int(attacker.get("shield", 0))

    # Shields absorb first
    def_absorb = min(def_shield, dmg_to_def)
    atk_absorb = min(atk_shield, dmg_to_atk)
    def_shield_after = def_shield - def_absorb
    atk_shield_after = atk_shield - atk_absorb
    def_hp_after = max(0, int(defender.get("hp", 100)) - (dmg_to_def - def_absorb))
    atk_hp_after = max(0, int(attacker.get("hp", 100)) - (dmg_to_atk - atk_absorb))

    if def_hp_after <= 0 and atk_hp_after > 0:
        winner = str(attacker.get("player_id"))
    elif atk_hp_after <= 0 and def_hp_after > 0:
        winner = str(defender.get("player_id"))
    else:
        winner = str(attacker.get("player_id")) if atk_roll >= def_roll else str(defender.get("player_id"))

    summary = f"sec {sector_id} {attacker.get('nick')} vs {defender.get('nick')} win={winner[:8]} defL={defense_level}"
    return {
        "attacker": attacker.get("player_id"),
        "defender": defender.get("player_id"),
        "winner": winner,
        "sector_id": sector_id,
        "defense_level": defense_level,
        "damage_attacker": dmg_to_atk,
        "damage_defender": dmg_to_def,
        "attacker_hp": atk_hp_after,
        "defender_hp": def_hp_after,
        "attacker_shield": atk_shield,
        "defender_shield": def_shield,
        "attacker_shield_after": atk_shield_after,
        "defender_shield_after": def_shield_after,
        "summary": summary,
    }
