"""The layout documentation page matches its template and block_lengths.csv (one row per detector), drawing D2
states the same section count, and the hand-edited drawings carry no SOQ wording."""
import io
import re
import sys
import tokenize
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import build_layout_docs as ld  # noqa: E402


class LayoutDocs(unittest.TestCase):
    def test_outputs_are_current(self):
        for path, text in ld.outputs().items():
            self.assertTrue(path.exists() and path.read_text() == text,
                            f"{path} is stale: run python3 www/scripts/build_layout_docs.py")

    def test_page_reads_nothing_from_the_soq(self):
        # The SOQ is submitted and frozen; the page is maintained on its own (owner, 2026-11-22).
        page = ld.PAGE.read_text()
        self.assertNotIn("docs/ap/electrical", page)
        src = (SCRIPTS / "build_layout_docs.py").read_text()
        strings = [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.STRING]
        self.assertFalse([s for s in strings[1:] if "ap/electrical" in s or "build_soq" in s])   # [0] is the docstring
        for rel in set(re.findall(r'\.\./(assets/behind/layout-docs/[\w./-]+)', page)):
            self.assertTrue((ld.PORTAL / rel).is_file(), rel)

    def test_drawings_carry_no_soq_wording(self):
        ld.check_drawings()

    def test_every_section_has_a_label(self):
        for s in ld.detected_sections():
            ld.label(s["name"])

    def test_parts_fold_into_their_detector(self):
        def row(name, sensor, plan, measured=None, note=""):
            return ld.railroad.BlockLength(2, name, sensor, plan, measured, "timed" if measured else "plan", "1",
                                           name, note)
        rows = [row("OS Switch 1", "Block 4-2", 9.2, 22.6),
                row("Track 1-3 at 1", "Block 4-2", 5.0, note="a part of OS Switch 1, on its detector"),
                row("OS Switch 9", "Block 13-8", 9.2),
                row("Track 9-11", "Block 13-8", 10.3, note="a part of OS Switch 9, on its detector"),
                row("Track 109-111", "BS Switch 109", 5.4, note="main level")]
        # the rows come from hartlib.railroad.read_block_lengths, in file order
        with mock.patch.object(ld.railroad, "read_block_lengths", return_value={r.user_name: r for r in rows}):
            got = ld.detected_sections()
        self.assertEqual([(s["name"], s["inches"], s["estimate"]) for s in got],
                         [("OS Switch 1", 22.6, False), ("OS Switch 9", 19.5, True)])
        rows[3] = replace(rows[3], occupancy_sensor="Block 4-2")     # 9-11 put on OS Switch 1's detector by mistake
        with mock.patch.object(ld.railroad, "read_block_lengths", return_value={r.user_name: r for r in rows}), \
                self.assertRaises(SystemExit):
            ld.detected_sections()

    def test_d2_must_state_the_live_count(self):
        ld.check_d2(len(ld.detected_sections()))
        with self.assertRaises(SystemExit):
            ld.check_d2(len(ld.detected_sections()) + 1)


if __name__ == "__main__":
    unittest.main()
