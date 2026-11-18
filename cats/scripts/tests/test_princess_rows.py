"""Princess on the CATS desks: K-1 / K-2 on the outer rows, the mains in the centre (ADR-017 item 8)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cats/scripts"))
import desks  # noqa: E402  (cats/scripts/tests/desks.py: the live desks)


class PrincessRows(unittest.TestCase):
    def test_live_desk_polarity(self):
        # the live (generated) desks: Switches 37 and 39 close to the mains, NORMAL, and throw to the K tracks
        want = {"OS Switch 37": ("Track McKeesport", "Track K-2"), "OS Switch 39": ("Track McKees Rocks", "Track K-1")}
        for desk in desks.LIVE:
            for os_block, (closed, thrown) in want.items():
                with self.subTest(desk=desk.name, plant=os_block):
                    self.assertEqual(desks.routes(desk, os_block), {"close": (closed, True), "throw": (thrown, False)})


if __name__ == "__main__":
    unittest.main()
