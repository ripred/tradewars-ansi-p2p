from __future__ import annotations

import unittest

from twansi.game.economy import production_for_sector


class EconomyTest(unittest.TestCase):
    def test_production_positive(self) -> None:
        for doctrine in ("assault", "siege", "defense"):
            p = production_for_sector(5, doctrine)
            self.assertGreater(p["credits"], 0)
            self.assertGreater(p["ore"], 0)
            self.assertGreater(p["gas"], 0)
            self.assertGreater(p["crystal"], 0)


if __name__ == "__main__":
    unittest.main()
