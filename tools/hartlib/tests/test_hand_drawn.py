"""hartlib.hand_drawn: the last hand-drawn tables.xml, read from git after the Layout Editor cut-over."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import hand_drawn, tables  # noqa: E402


class HandDrawnTest(unittest.TestCase):
    def test_the_pinned_commit_holds_the_hand_drawn_panel(self):
        try:
            path = hand_drawn.tables_path()
        except ValueError as exc:
            self.skipTest(str(exc))
        self.assertEqual(path.read_bytes(), hand_drawn.tables_bytes())
        panel = tables.layout_editor(tables.read(path))
        self.assertIsNotNone(panel)
        self.assertFalse(tables.generated_panel(panel))
        self.assertEqual(hand_drawn.tables_path(), path)                # once per process

    def test_a_missing_object_is_a_clear_error_and_a_skip_in_tests(self):
        with self.assertRaisesRegex(ValueError, "not in this checkout's git"):
            hand_drawn.tables_bytes("0000000000000000000000000000000000000000")
        with mock.patch.object(hand_drawn, "tables_path", side_effect=ValueError("no git here")), \
                self.assertRaisesRegex(unittest.SkipTest, "needs the last hand-drawn files from git: no git here"):
            hand_drawn.skip_unless_available()


    def test_the_hand_wired_cats_desks(self):
        try:
            ctc = hand_drawn.cats_desk_path("HART_CTC.xml")
        except ValueError as exc:
            self.skipTest(str(exc))
        self.assertEqual(ctc.name, "HART_CTC.xml")
        self.assertIn(b"<DOCUMENT", ctc.read_bytes()[:400])
        self.assertEqual(hand_drawn.skip_unless_available("HART_ABS.xml").name, "HART_ABS.xml")
        with self.assertRaisesRegex(ValueError, "not a hand-wired CATS desk"):
            hand_drawn.cats_desk_path("HART_Digicon.xml")
        with self.assertRaisesRegex(ValueError, "not a hand-wired CATS desk"):    # raised, not skipped
            hand_drawn.skip_unless_available("HART_Digicon.xml")


if __name__ == "__main__":
    unittest.main()
