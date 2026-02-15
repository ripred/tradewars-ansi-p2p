from __future__ import annotations

import json
import time
from typing import Any


PROTOCOL_VERSION = 1


def canonical_bytes(envelope: dict[str, Any]) -> bytes:
    return json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")


def make_envelope(
    *,
    msg_type: str,
    sender: str,
    seq: int,
    ack: int,
    ack_bits: int,
    shard: str,
    payload: dict[str, Any],
    reliable: bool = False,
    ack_only: bool = False,
) -> dict[str, Any]:
    flags: list[str] = []
    if reliable:
        flags.append("reliable")
    if ack_only:
        flags.append("ack_only")
    return {
        "v": PROTOCOL_VERSION,
        "type": msg_type,
        "sender": sender,
        "seq": seq,
        "ack": ack,
        "ack_bits": ack_bits,
        "ts": int(time.time() * 1000),
        "shard": shard,
        "flags": flags,
        "payload": payload,
    }
