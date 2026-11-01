from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import refresh_bean_comments


class RefreshTargetsTest(unittest.TestCase):
    def test_every_target_exists(self) -> None:
        missing = [str(p) for p in refresh_bean_comments.TARGETS if not p.exists()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
