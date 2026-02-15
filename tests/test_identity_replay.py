from __future__ import annotations

import unittest

from twansi.identity import Identity


class IdentityTest(unittest.TestCase):
    def test_identity_sign_deterministic(self) -> None:
        ident = Identity("11" * 32)
        payload = {"a": 1, "b": "x"}
        sig1 = ident.sign_obj(payload)
        sig2 = ident.sign_obj(payload)
        self.assertEqual(sig1, sig2)


if __name__ == "__main__":
    unittest.main()
