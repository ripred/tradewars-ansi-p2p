from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlayerState:
    player_id: str
    nick: str
    doctrine: str
    credits: int
    ore: int
    gas: int
    crystal: int
    hp: int
    sector: int
    alliance_id: str | None


DOCTRINES = ("assault", "siege", "defense")
