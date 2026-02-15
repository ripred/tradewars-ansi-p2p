from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Policy:
    min_protocol_version: int
    max_protocol_version: int
    protocol_epoch: int
    max_event_hops: int
    reliable_event_types: tuple[str, ...]
    packets_per_sec: int
    policy_hash: str


def _default_policy_dict() -> dict[str, Any]:
    return {
        "min_protocol_version": 1,
        "max_protocol_version": 1,
        "protocol_epoch": 1,
        "max_event_hops": 2,
        "reliable_event_types": [
            "battle",
            "market_trade",
            "chat",
            "mission_complete",
            "tech_upgrade",
            "jump",
            "defense_upgrade",
            "alliance_join",
            "alliance_create",
            "alliance_rename",
            "alliance_leave",
            "alliance_kick",
        ],
        "rate_limits": {"packets_per_sec": 120},
    }


def _hash_policy(d: dict[str, Any]) -> str:
    canonical = json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def load_policy(repo_root: str | None = None) -> Policy:
    # repo_root defaults to cwd; allow override for tests.
    root = Path(repo_root or os.getcwd()).resolve()
    path = root / "twansi_policy.json"
    if path.exists():
        d = json.loads(path.read_text(encoding="utf-8"))
    else:
        d = _default_policy_dict()

    # normalize
    min_v = int(d.get("min_protocol_version", 1))
    max_v = int(d.get("max_protocol_version", min_v))
    epoch = int(d.get("protocol_epoch", 1))
    max_hops = int(d.get("max_event_hops", 2))
    rel = tuple(str(x) for x in d.get("reliable_event_types", []))
    rl = d.get("rate_limits", {}) or {}
    pps = int(rl.get("packets_per_sec", 120))

    ph = _hash_policy({
        "min_protocol_version": min_v,
        "max_protocol_version": max_v,
        "protocol_epoch": epoch,
        "max_event_hops": max_hops,
        "reliable_event_types": list(rel),
        "rate_limits": {"packets_per_sec": pps},
    })

    return Policy(
        min_protocol_version=min_v,
        max_protocol_version=max_v,
        protocol_epoch=epoch,
        max_event_hops=max_hops,
        reliable_event_types=rel,
        packets_per_sec=pps,
        policy_hash=ph,
    )


def derive_shard_key(shard: str, epoch: int, secret: str | None = None) -> str:
    # IMPORTANT: if secret is empty, this is public and provides no security against a malicious client.
    # It does provide a clean protocol epoch rotation mechanism for honest nodes.
    s = secret or os.environ.get("TWANSI_SHARD_SECRET", "")
    material = f"twansi:{shard}:epoch:{int(epoch)}:{s}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()
