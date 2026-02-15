from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Peer:
    peer_id: str
    host: str
    port: int
    shard: str
    nick: str
    last_seen: float
    latency_ms: float = 0.0
    score: float = 100.0


class Membership:
    def __init__(self) -> None:
        self.peers: dict[str, Peer] = {}

    def seen(self, peer_id: str, host: str, port: int, shard: str, nick: str) -> None:
        now = time.time()
        p = self.peers.get(peer_id)
        if p is None:
            self.peers[peer_id] = Peer(peer_id=peer_id, host=host, port=port, shard=shard, nick=nick, last_seen=now)
        else:
            p.host = host
            p.port = port
            p.shard = shard
            p.nick = nick
            p.last_seen = now

    def penalize(self, peer_id: str, amount: float) -> None:
        p = self.peers.get(peer_id)
        if p:
            p.score = max(0.0, p.score - amount)

    def healthy(self, max_age: float = 30.0) -> list[Peer]:
        now = time.time()
        return [p for p in self.peers.values() if (now - p.last_seen) <= max_age and p.score > 10]

    def stale(self, max_age: float = 30.0) -> list[Peer]:
        now = time.time()
        return [p for p in self.peers.values() if (now - p.last_seen) > max_age]
