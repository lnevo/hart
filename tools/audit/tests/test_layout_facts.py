"""check_layout_facts.py passes on the repo and catches a flipped switch sense.

The Switch 9 rewiring (2026-11-12) took three commits to bring tables.xml, the
CATS desks and the generators back into agreement. Each test below flips one
side of Switch 9 in a temporary copy and expects the check to name Switch 9 and
the two sources that disagree.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/audit"))
import check_layout_facts as check  # noqa: E402

DATA_FILES = ("switches.csv", "switch_legs.csv", "public_name_map.csv", "control_points.csv")


class LayoutFactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def copy(self, src: Path, edit=None) -> Path:
        dst = self.tmp / src.name
        text = src.read_text(encoding="utf-8")
        if edit is not None:
            new = edit(text)
            self.assertTrue(new != text, f"edit did not change {src.name}")
            text = new
        dst.write_text(text, encoding="utf-8")
        return dst

    def failures(self, **kw) -> list[str]:
        return check.run(**kw).failures(check.KNOWN)

    def test_repo_passes(self) -> None:
        self.assertEqual(self.failures(), [])

    def test_flipped_continuing_sense(self) -> None:
        tables = self.copy(check.TABLES, lambda t: re.sub(
            r'(<layoutturnout ident="TO10"[^>]*?) continuing="4"', r'\1 continuing="2"', t))
        out = self.failures(tables=tables)
        self.assertTrue(any(m.startswith("Switch 9: Layout Editor TO10 (continuing=2) closes to Track EH-3")
                            and "switch_legs.csv says closed Track EH-2" in m for m in out), out)

    def test_flipped_block_path(self) -> None:
        def flip(text: str) -> str:
            os9 = re.search(r"<occupancysensor>BS Switch 9</occupancysensor>.*?</block>", text, re.S)
            body = os9.group(0).replace(
                '<beansetting setting="2">\n          <turnout systemName="Switch 9" />',
                '<beansetting setting="4">\n          <turnout systemName="Switch 9" />')
            return text[:os9.start()] + body + text[os9.end():]

        out = self.failures(tables=self.copy(check.TABLES, flip))
        self.assertTrue(any(m.startswith("Switch 9: OS Switch 9 block paths reach Track EH-2")
                            and "closed leg" in m for m in out), out)

    def test_flipped_cats_normal(self) -> None:
        def flip(text: str) -> str:
            cell = re.search(r'<SECTION X="24" Y="8">.*?</SECTION>', text, re.S)
            body = cell.group(0).replace('ROUTEID="BOTTOM" NORMAL="true"', 'ROUTEID="BOTTOM"').replace(
                'ROUTEID="LEFT"', 'ROUTEID="LEFT" NORMAL="true"')
            return text[:cell.start()] + body + text[cell.end():]

        desk = self.copy(check.DESKS[0], flip)
        out = self.failures(desks=(desk,))
        self.assertTrue(any(m.startswith("Switch 9: HART_CTC.xml OS Switch 9 NORMAL") for m in out), out)

    def test_flipped_fact_fails_on_every_side(self) -> None:
        data = self.tmp / "data"
        data.mkdir()
        for name in DATA_FILES:
            shutil.copy(check.facts.DATA / name, data / name)
        legs = data / "switch_legs.csv"
        legs.write_text(legs.read_text().replace(
            "9,OS Switch 9,Track EH-2,Track EH-3", "9,OS Switch 9,Track EH-3,Track EH-2"))
        out = [m for m in self.failures(data=data) if m.startswith("Switch 9:")]
        self.assertTrue(any("Layout Editor TO10" in m for m in out), out)
        self.assertTrue(any("block paths" in m for m in out), out)
        self.assertTrue(any("HART_CTC.xml" in m and "(close) leads to Track EH-2" in m for m in out), out)
        self.assertTrue(any("HART_ABS.xml" in m for m in out), out)

    def test_stale_known_entry_fails(self) -> None:
        report = check.run()
        known = dict(check.KNOWN, **{"uss-dot:Switch 1": "made up"})
        self.assertIn("KNOWN entry 'uss-dot:Switch 1' no longer happens; remove it from KNOWN",
                      report.failures(known))

    def test_throat_blocks_count_as_their_track(self) -> None:
        t = check.Tables(check.TABLES)
        self.assertEqual(t.track_name("Track S-R West"), "Track S-R")
        self.assertEqual(t.track_name("Track Main West"), "Track Main West")


if __name__ == "__main__":
    unittest.main()
