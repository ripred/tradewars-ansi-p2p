from __future__ import annotations

import tempfile
import unittest

from twansi.state.store_sqlite import Store


class PortTest(unittest.TestCase):
    def test_port_trade_buy_sell_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with Store(f"{td}/db.sqlite") as s:
                s.ensure_sector(1, richness=5, danger=4)
                pid = "p1"
                s.ensure_player(pid, "p")
                s.ensure_port(1, port_class="SBB", stock={"ore": 120, "gas": 120, "crystal": 120})
                info = s.port_info(1)
                self.assertIsNotNone(info)

                # SBB: sells ore, buys gas/crystal.
                r = s.port_trade(pid, 1, "ore", 1, "buy")
                self.assertEqual(r["side"], "buy")

                with self.assertRaises(ValueError):
                    s.port_trade(pid, 1, "ore", 1, "sell")
                with self.assertRaises(ValueError):
                    s.port_trade(pid, 1, "gas", 1, "buy")

                s.db.execute("UPDATE players SET gas=999 WHERE player_id=?", (pid,))
                s.db.commit()
                r2 = s.port_trade(pid, 1, "gas", 2, "sell")
                self.assertEqual(r2["side"], "sell")

                # No hard out-of-stock: port stock may go negative for mesh-convergent deltas.
                s.db.execute("UPDATE port_inventory SET stock=0 WHERE sector_id=1 AND resource='ore'")
                s.db.commit()
                r3 = s.port_trade(pid, 1, "ore", 50, "buy")
                self.assertEqual(r3["resource"], "ore")


if __name__ == "__main__":
    unittest.main()
