from __future__ import annotations

import tempfile
import unittest

from twansi.state.digest import build_offline_digest
from twansi.state.store_sqlite import Store


class DigestTest(unittest.TestCase):
    def test_digest_counts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with Store(f"{td}/db.sqlite") as store:
                pid = "p1"
                store.ensure_player(pid, "n1")
                store.record_event("p1", "resource_tick", {"player_id": pid, "credits": 5, "ore": 2, "gas": 1, "crystal": 3})
                store.record_event("p2", "battle", {"attacker": pid, "defender": "p2", "winner": pid, "damage_taken_by_player": 4})
                d = build_offline_digest(store, pid)
                self.assertEqual(d["credits_delta"], 5)
                self.assertEqual(d["battles"], 1)
                self.assertEqual(d["wins"], 1)


if __name__ == "__main__":
    unittest.main()
