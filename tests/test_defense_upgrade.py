from __future__ import annotations

import tempfile
import unittest

from twansi.state.store_sqlite import Store


class DefenseUpgradeTest(unittest.TestCase):
    def test_upgrade_requires_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with Store(f"{td}/db.sqlite") as s:
                s.ensure_sector(1, richness=4, danger=4)
                pid = "p1"
                s.ensure_player(pid, "p")
                # not owner
                with self.assertRaises(ValueError):
                    s.upgrade_sector_defense(1, pid)
                s.claim_sector(1, pid)
                lvl = s.upgrade_sector_defense(1, pid)
                self.assertGreaterEqual(lvl, 1)


if __name__ == "__main__":
    unittest.main()
