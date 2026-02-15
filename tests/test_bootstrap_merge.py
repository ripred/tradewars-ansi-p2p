from __future__ import annotations

import unittest

from twansi.net.bootstrap import merge_seeds


class BootstrapMergeTest(unittest.TestCase):
    def test_merge_dedup_and_limit(self) -> None:
        a = ["a:1", "b:2"]
        b = ("b:2", "c:3", "d:4")
        out = merge_seeds(a, b, max_total=3)
        self.assertEqual(out, ["a:1", "b:2", "c:3"])


if __name__ == "__main__":
    unittest.main()
