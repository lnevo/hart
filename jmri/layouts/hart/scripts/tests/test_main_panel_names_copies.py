"""The Jython scripts cannot import hartlib, so they carry their own copy of the main Layout Editor panel names.
Fail when a copy drifts from hartlib.tables.MAIN_PANEL_NAMES."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS.parents[3] / "tools/hartlib/src"))
from hartlib import tables  # noqa: E402

ANCHOR = tables.MAIN_PANEL_NAMES[0]


def copies(path: Path) -> list[tuple[str, ...]]:
    """Every tuple, list or set literal of strings in the script that holds the first main panel name."""
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            vals = tuple(e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
            if len(vals) == len(node.elts) and ANCHOR in vals:
                found.append(vals)
    return found


class MainPanelNamesCopiesTest(unittest.TestCase):
    def test_copies_match_hartlib(self):
        for name in ("discover_nx.py", "panel_status.py"):
            found = copies(SCRIPTS / name)
            self.assertTrue(found, f"{name}: no copy of the main panel names found; update this test if it moved")
            for vals in found:
                self.assertEqual(
                    sorted(vals), sorted(tables.MAIN_PANEL_NAMES),
                    f"{name} has main panel names {vals} but hartlib.tables.MAIN_PANEL_NAMES is "
                    f"{tables.MAIN_PANEL_NAMES}; change them together")


if __name__ == "__main__":
    unittest.main()
