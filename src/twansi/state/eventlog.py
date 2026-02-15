from __future__ import annotations

import hashlib
import json
import time
from typing import Any


def event_id(sender_id: str, local_counter: int, payload: dict[str, Any]) -> str:
    base = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    raw = f"{sender_id}:{local_counter}:{int(time.time()*1000)}:{base}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def compact_event(event_type: str, payload: dict[str, Any], sender: str, event_id_str: str) -> dict[str, Any]:
    return {
        "event_id": event_id_str,
        "event_type": event_type,
        "payload": payload,
        "sender": sender,
    }
