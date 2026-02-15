from __future__ import annotations

import tempfile
import time
import unittest

from twansi.game.mapgen import ensure_map
from twansi.state.store_sqlite import Store


class APAndWarpsTest(unittest.TestCase):
    def test_ap_regen_and_consume(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = Store(f"{td}/db.sqlite")
            pid = "p1"
            s.ensure_player(pid, "n")
            p = s.get_player(pid)
            self.assertIsNotNone(p)

            s.db.execute("UPDATE players SET ap=0, ap_updated_ts=? WHERE player_id=?", (time.time() - 3600, pid))
            s.db.commit()
            ap = s.regen_ap(pid, max_ap=50, per_minute=10)
            self.assertGreaterEqual(ap, 50)
            s.consume_ap(pid, 5)
            p2 = s.get_player(pid)
            self.assertEqual(int(p2["ap"]), ap - 5)

    def test_warp_graph_exists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = Store(f"{td}/db.sqlite")
            ensure_map(s, sectors=40)
            w = s.list_warps(1)
            self.assertGreaterEqual(len(w), 1)
            # ring connectivity implies 2 is connected to 1
            self.assertIn(2, w)


if __name__ == "__main__":
    unittest.main()
