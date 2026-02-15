from __future__ import annotations

from typing import Any


def production_for_sector(richness: int, doctrine: str) -> dict[str, int]:
    base_ore = 6 + richness
    base_gas = 4 + richness // 2
    base_crystal = 3 + richness // 3
    credits = 20 + richness * 2
    if doctrine == "siege":
        base_ore += 2
    elif doctrine == "assault":
        base_gas += 2
    elif doctrine == "defense":
        base_crystal += 2
    return {"credits": credits, "ore": base_ore, "gas": base_gas, "crystal": base_crystal}


def mine_burst() -> dict[str, int]:
    return {"credits": 12, "ore": 8, "gas": 6, "crystal": 3}
