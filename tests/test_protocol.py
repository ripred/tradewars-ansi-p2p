from __future__ import annotations

import unittest

from twansi.identity import ShardAuthenticator
from twansi.net.messages import make_envelope


class ProtocolTest(unittest.TestCase):
    def test_envelope_sign_verify(self) -> None:
        auth = ShardAuthenticator("ab" * 32)
        env = make_envelope(
            msg_type="HELLO",
            sender="peer1",
            seq=1,
            ack=0,
            ack_bits=0,
            shard="alpha",
            epoch=1,
            payload={"nick": "cap"},
            reliable=False,
        )
        mac = auth.sign(env)
        self.assertTrue(auth.verify(env, mac))
        env["payload"]["nick"] = "tampered"
        self.assertFalse(auth.verify(env, mac))


if __name__ == "__main__":
    unittest.main()
