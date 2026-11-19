"""Jython scripts cannot import hartlib, so any that name the main Layout Editor panels carry their own copy.
Fail when a copy drifts from hartlib.tables.MAIN_PANEL_NAMES. Scans every script in the dirs that hold
JMRI-run scripts, skipping CPython ones that import hartlib."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[3]
sys.path.insert(0, str(REPO / "tools/hartlib/src"))
from hartlib import tables  # noqa: E402

DIRS = (SCRIPTS, REPO / "jmri/scripts")
MAIN = set(tables.MAIN_PANEL_NAMES)


def scripts():
    for d in DIRS:
        for path in sorted(d.glob("*.py")):
            if "hartlib" not in path.read_text():
                yield path


LITERAL = re.compile(r"[(\[{]\s*((?:(?:\"[^\"\n]*\"|'[^'\n]*')\s*,?\s*)+)[)\]}]")
STRING = re.compile(r"\"([^\"\n]*)\"|'([^'\n]*)'")


def copies(path: Path) -> list[tuple[str, ...]]:
    """String-only tuple, list or set literals that share at least two names with the main panel names.
    Read as text, not parsed: some JMRI scripts are Jython 2 and do not parse as Python 3."""
    found = []
    for m in LITERAL.finditer(path.read_text()):
        vals = tuple(a or b for a, b in STRING.findall(m.group(1)))
        if len(MAIN & set(vals)) >= 2:
            found.append(vals)
    return found


class MainPanelNamesCopiesTest(unittest.TestCase):
    def test_copies_match_hartlib(self):
        total = 0
        for path in scripts():
            for vals in copies(path):
                total += 1
                self.assertEqual(
                    sorted(vals), sorted(tables.MAIN_PANEL_NAMES),
                    f"{path.relative_to(REPO)} has main panel names {vals} but hartlib.tables.MAIN_PANEL_NAMES "
                    f"is {tables.MAIN_PANEL_NAMES}; change them together")
        self.assertTrue(total, "no copy of the main panel names found in any Jython script; update this test")


if __name__ == "__main__":
    unittest.main()
