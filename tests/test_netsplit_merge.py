from __future__ import annotations

import time
import unittest

from twansi.net.netsplit import NetsplitTracker


class NetsplitTest(unittest.TestCase):
    def test_split_then_merge(self) -> None:
        n = NetsplitTracker()
        n.last_peer_seen_ts = time.time() - 60
        n.tick(peer_count=0, timeout=5)
        self.assertTrue(n.split_active)
        n.on_peer_seen()
        self.assertFalse(n.split_active)
        self.assertEqual(n.merge_count, 1)


if __name__ == "__main__":
    unittest.main()
