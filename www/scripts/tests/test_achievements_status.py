"""Achievement dashboard status and bar rules: runs achievements_status_test.js with node; skipped when node is missing."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

JS = Path(__file__).with_name("achievements_status_test.js")
PAGE = Path(__file__).resolve().parents[2] / "ap" / "index.html"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AchievementsStatus(unittest.TestCase):
    def test_rules(self):
        r = subprocess.run(["node", str(JS)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class PathTable(unittest.TestCase):
    """The "path to seven" marks are filled from the checklists, so each must name a real one, as the dashboard cards do."""

    def test_every_row_names_a_checklist(self):
        html = PAGE.read_text(encoding="utf-8")
        ids = re.findall(r'data-ap-path="([^"]+)"', html)
        self.assertEqual(len(ids), 7)
        cards = set(re.findall(r'data-ap-cert="([^"]+)"', html))
        for cid in ids:
            self.assertIn(f'id="{cid}"', html, cid)
            self.assertIn(cid, cards, cid)


if __name__ == "__main__":
    unittest.main()
