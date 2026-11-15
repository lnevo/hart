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


RANK = {"done": 4, "ready": 3, "part": 2, "todo": 1, "ask": 1}


def status_of(marks):
    """Python copy of statusOf in www/js/achievements.js."""
    n = {k: marks.count(k) for k in ("done", "ready", "part", "todo", "ask")}
    total = len(marks)
    if not total:
        return ""
    if n["done"] == total:
        return "done"
    if n["ready"] and n["done"] + n["ready"] == total:
        return "ready"
    if n["done"] or n["ready"] or n["part"]:
        return "part"
    if n["ask"] == total:
        return "ask"
    return "todo"


class PathTable(unittest.TestCase):
    """The "path to seven" marks are filled from the checklists by achievements.js; the static marks
    (what readers without JavaScript and link previews see) must agree with them too."""

    def setUp(self):
        self.html = PAGE.read_text(encoding="utf-8")

    def cert_status(self, cid):
        m = re.search(r'<details class="ap-cert" id="' + re.escape(cid) + r'"[^>]*>(.*?)</details>', self.html, re.S)
        self.assertIsNotNone(m, f"no checklist <details class=\"ap-cert\" id=\"{cid}\">")
        lists = re.findall(r'<ul class="ap-list">(.*?)</ul>', m.group(1), re.S)
        return status_of(re.findall(r'class="ap-mark (\w+)"', "".join(lists)))

    def test_static_marks_match_checklists(self):
        rows = re.findall(r'class="ap-mark (\w+)" data-ap-path="([^"]+)"', self.html)
        self.assertTrue(rows)
        for shown, ids in rows:
            best = max((self.cert_status(i) for i in ids.split()), key=lambda s: RANK.get(s, 0))
            self.assertEqual(shown, best, ids)


if __name__ == "__main__":
    unittest.main()
