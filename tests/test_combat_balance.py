from __future__ import annotations

import unittest

from twansi.game.balance import doctrine_modifier


class CombatBalanceTest(unittest.TestCase):
    def test_rps_modifiers(self) -> None:
        self.assertGreater(doctrine_modifier("assault", "siege"), 1.0)
        self.assertGreater(doctrine_modifier("siege", "defense"), 1.0)
        self.assertGreater(doctrine_modifier("defense", "assault"), 1.0)
        self.assertLess(doctrine_modifier("siege", "assault"), 1.0)


if __name__ == "__main__":
    unittest.main()
