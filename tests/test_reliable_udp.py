from __future__ import annotations

import unittest

from twansi.identity import ShardAuthenticator
from twansi.net.reliable import ReliableMesh


class DummyTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def send(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))

    def broadcast(self, data: bytes, port: int) -> None:
        self.sent.append((data, ("255.255.255.255", port)))


class ReliableTest(unittest.TestCase):
    def test_ack_removes_pending(self) -> None:
        tr = DummyTransport()
        mesh = ReliableMesh(tr, ShardAuthenticator("01" * 32), "sender", "alpha", lambda *_: None)
        seq = mesh.send("PING", {"x": 1}, ("127.0.0.1", 1), reliable=True)
        self.assertIn(seq, mesh.pending)
        mesh._apply_ack(seq, 0)
        self.assertNotIn(seq, mesh.pending)


if __name__ == "__main__":
    unittest.main()
