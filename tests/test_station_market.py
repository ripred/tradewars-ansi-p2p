from __future__ import annotations

import tempfile
import unittest

from twansi.state.store_sqlite import Store


class StationMarketTest(unittest.TestCase):
    def test_station_inventory_and_trade(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with Store(f"{td}/db.sqlite") as s:
                pid = "p1"
                s.ensure_sector(1, richness=5, danger=5)
                s.ensure_player(pid, "pilot")

                m = s.station_market(1)
                self.assertIn("ore", m["prices"])
                self.assertGreater(m["stock"]["ore"], 0)

                p0 = s.get_player(pid)
                trade = s.station_trade(pid, 1, "ore", 3, "buy")
                self.assertEqual(trade["side"], "buy")
                p1 = s.get_player(pid)
                self.assertGreater(p1["ore"], p0["ore"])

                trade2 = s.station_trade(pid, 1, "ore", 2, "sell")
                self.assertEqual(trade2["side"], "sell")


if __name__ == "__main__":
    unittest.main()
