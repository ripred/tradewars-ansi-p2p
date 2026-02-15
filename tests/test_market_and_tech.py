from __future__ import annotations

import tempfile
import unittest

from twansi.game.tech import upgrade_tech
from twansi.state.store_sqlite import Store


class MarketTechTest(unittest.TestCase):
    def test_buy_sell_and_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            s = Store(f"{td}/db.sqlite")
            pid = "p1"
            s.ensure_player(pid, "pilot")

            before = s.get_player(pid)
            trade = s.trade_resource(pid, "ore", 5, "buy")
            self.assertEqual(trade["side"], "buy")
            after_buy = s.get_player(pid)
            self.assertGreater(after_buy["ore"], before["ore"])

            trade2 = s.trade_resource(pid, "ore", 3, "sell")
            self.assertEqual(trade2["side"], "sell")
            after_sell = s.get_player(pid)
            self.assertLess(after_sell["ore"], after_buy["ore"])

            up = upgrade_tech(s, pid, "mining")
            self.assertEqual(up["to_tier"], 1)
            lv = s.get_tech_levels(pid)
            self.assertEqual(lv["mining"], 1)


if __name__ == "__main__":
    unittest.main()
