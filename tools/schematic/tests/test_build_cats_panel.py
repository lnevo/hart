"""build_cats_panel.check_desk_faults: the plugin's desk faults printed with their count, and a desk with one stops."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_cats_panel as b  # noqa: E402


def fake_cats(found):
    """A stand-in for the plugin's cats module whose faults() returns `found` and records what it was asked."""
    asked = []

    def faults(P, fit):
        asked.append((P, fit))
        return list(found)
    return SimpleNamespace(faults=faults, asked=asked)


class DeskFaults(unittest.TestCase):

    def run_check(self, found):
        cats = fake_cats(found)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                b.check_desk_faults(cats, "panel", (62, 30))
            except b.CatsPanelError as exc:
                return out.getvalue(), str(exc), cats.asked
        return out.getvalue(), None, cats.asked

    def test_no_fault_prints_the_count_and_goes_on(self):
        out, code, asked = self.run_check([])
        self.assertEqual(out, "CATS desk faults: 0\n")
        self.assertIsNone(code)
        self.assertEqual(asked, [("panel", (62, 30))])       # the window's fit is passed on

    def test_a_fault_is_listed_and_stops(self):
        fault = "Main level: blocks A, B land in one cell, (17, 15) edge LEFT, where both reach one edge"
        out, code, _asked = self.run_check([fault])
        self.assertEqual(out, f"CATS desk faults: 1\n  {fault}\n")
        self.assertEqual(code, "error: the desk has 1 fault(s), listed above")


if __name__ == "__main__":
    unittest.main()
