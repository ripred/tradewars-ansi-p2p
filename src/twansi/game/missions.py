from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Mission:
    mission_id: str
    kind: str
    target_sector: int
    reward_credits: int
    reward_ore: int
    reward_gas: int
    reward_crystal: int
    slot: int
    expires_in_s: int


def _seed64(*parts: Any) -> int:
    s = "|".join(str(p) for p in parts)
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False)


def current_missions(shard: str, epoch: int, sectors: int, now_ts: float) -> list[Mission]:
    # Deterministic missions per shard/epoch/time-slot.
    slot = int(now_ts // 300)  # 5 min windows
    expires_in = int(300 - (now_ts % 300))
    rng = _seed64("twansi-missions", shard, int(epoch), int(sectors), int(slot))

    def pick(i: int, lo: int, hi: int) -> int:
        return lo + int(_seed64(rng, i) % (hi - lo + 1))

    # 3 concurrent missions.
    missions: list[Mission] = []
    kinds = ["survey", "raid", "supply"]
    for idx, kind in enumerate(kinds):
        target = pick(idx + 10, 1, max(1, int(sectors)))
        base = 180 + pick(idx + 50, 0, 160)
        if kind == "raid":
            base += 120
        if kind == "supply":
            base += 60
        mid = hashlib.sha256(f"{shard}|{epoch}|{slot}|{kind}|{target}".encode("utf-8")).hexdigest()[:24]
        missions.append(
            Mission(
                mission_id=mid,
                kind=kind,
                target_sector=int(target),
                reward_credits=int(base),
                reward_ore=0,
                reward_gas=6 if kind == "raid" else 0,
                reward_crystal=2 if kind == "survey" else 0,
                slot=int(slot),
                expires_in_s=expires_in,
            )
        )
    return missions

