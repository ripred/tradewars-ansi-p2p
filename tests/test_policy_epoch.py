from __future__ import annotations

import json
import tempfile
import unittest

from twansi.policy import derive_shard_key, load_policy


class PolicyEpochTest(unittest.TestCase):
    def test_epoch_changes_key(self) -> None:
        k1 = derive_shard_key("alpha", 1, secret="s")
        k2 = derive_shard_key("alpha", 2, secret="s")
        self.assertNotEqual(k1, k2)

    def test_policy_load_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = {
                "min_protocol_version": 2,
                "max_protocol_version": 3,
                "protocol_epoch": 9,
                "max_event_hops": 1,
                "reliable_event_types": ["battle"],
                "rate_limits": {"packets_per_sec": 77},
            }
            with open(f"{td}/twansi_policy.json", "w", encoding="utf-8") as f:
                json.dump(p, f)
            pol = load_policy(td)
            self.assertEqual(pol.min_protocol_version, 2)
            self.assertEqual(pol.max_protocol_version, 3)
            self.assertEqual(pol.protocol_epoch, 9)
            self.assertEqual(pol.packets_per_sec, 77)
            self.assertTrue(pol.policy_hash)


if __name__ == "__main__":
    unittest.main()
