from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


class Identity:
    def __init__(self, secret_hex: str):
        self.secret_hex = secret_hex
        self.secret = bytes.fromhex(secret_hex)
        self.sender_id = hashlib.sha256(self.secret).hexdigest()[:32]

    def sign_bytes(self, data: bytes) -> str:
        return hmac.new(self.secret, data, hashlib.sha256).hexdigest()

    def sign_obj(self, obj: dict[str, Any]) -> str:
        canonical = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self.sign_bytes(canonical)


class ShardAuthenticator:
    def __init__(self, shard_key_hex: str):
        self.key = bytes.fromhex(shard_key_hex)

    def sign(self, obj: dict[str, Any]) -> str:
        body = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return hmac.new(self.key, body, hashlib.sha256).hexdigest()

    def verify(self, obj: dict[str, Any], mac: str) -> bool:
        expected = self.sign(obj)
        return hmac.compare_digest(expected, mac)
