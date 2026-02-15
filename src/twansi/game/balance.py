from __future__ import annotations


def doctrine_modifier(attacker: str, defender: str) -> float:
    attacker = attacker.lower()
    defender = defender.lower()
    if attacker == defender:
        return 1.0
    if attacker == "assault" and defender == "siege":
        return 1.2
    if attacker == "siege" and defender == "defense":
        return 1.2
    if attacker == "defense" and defender == "assault":
        return 1.2
    return 0.85
