"""The layout documentation page matches its template, block_lengths.csv (one row per detector) and the device
master's names; drawing D2 states the same section count and plans P3 and P4 the same lengths; a rename in the field
file renames the track on the page; the hand-edited drawings carry no SOQ wording."""
import csv
import io
import re
import shutil
import sys
import tempfile
import tokenize
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import build_layout_docs as ld  # noqa: E402

devices = ld.devices


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
            ld.label(s)

    def test_every_label_is_a_live_block(self):
        # a label for a block the plan no longer has would hide a renumbered switch
        master = ld.master_rows()
        self.assertFalse([bid for bid in ld.LABELS if (ld.LEVEL, bid) not in master])

    def test_parts_fold_into_their_detector(self):
        def length(bid, sensor, plan, measured=None):
            return ld.railroad.BlockLength(2, bid, sensor, plan, measured, "timed" if measured else "plan", "1",
                                           bid, "")
        lengths = [length("os:1", "Block 4-2", 9.2, 22.6), length("block:1B-3A:1/2", "Block 4-2", 5.0),
                   length("os:9", "Block 13-8", 9.2), length("block:9A-11C", "Block 13-8", 10.3),
                   length("block:109-111", "BS Switch 109", 5.4)]
        master = {("1", "os:1"): {"user_name": "OS Switch 1", "role": "", "part_of": ""},
                  ("1", "block:1B-3A:1/2"): {"user_name": "Track 1-3 at 1", "role": "part", "part_of": "OS Switch 1"},
                  ("1", "os:9"): {"user_name": "OS Switch 9", "role": "", "part_of": ""},
                  ("1", "block:9A-11C"): {"user_name": "Track 9-11", "role": "part", "part_of": "OS Switch 9"}}
        got = ld.detected_sections({r.id: r for r in lengths}, master)
        self.assertEqual([(s["id"], s["name"], s["inches"], s["estimate"]) for s in got],
                         [("os:1", "OS Switch 1", 22.6, False), ("os:9", "OS Switch 9", 19.5, True)])
        master[("1", "block:9A-11C")] = {**master[("1", "block:9A-11C")], "part_of": "OS Switch 1"}   # wrong block
        with self.assertRaises(SystemExit):
            ld.detected_sections({r.id: r for r in lengths}, master)

    def test_d2_must_state_the_live_count(self):
        ld.check_d2(len(ld.detected_sections()))
        with self.assertRaises(SystemExit):
            ld.check_d2(len(ld.detected_sections()) + 1)

    def test_plans_must_state_the_live_lengths(self):
        fact = ld.facts(ld.detected_sections())
        ld.check_plans(fact)
        with self.assertRaises(SystemExit):
            ld.check_plans({**fact, "SIDING_IN": str(int(fact["SIDING_IN"]) + 1)})

    def test_crossovers_come_from_the_os_halves(self):
        rows = [{"id": i, "inches": 100.0} for i in (ld.RS1, ld.SIDING, *ld.YARD)]
        rows += [{"id": i, "inches": 9.0} for i in ("os:35:A-33A", "os:7:A-5B", "os:23:A-1A", "os:23:A-31B", "os:3")]
        self.assertEqual(ld.facts(rows)["CROSSOVERS"], "7, 23 and 35")


class RenameReachesThePage(unittest.TestCase):
    """A copy of the device master whose field file renames a staging track and an OS block, as the owner would;
    nothing else changes (block_lengths.csv keeps its labels, as before the length-labels step runs)."""
    RENAMES = {("1", "block:17C-29C"): "Track S-9", ("1", "os:19"): "OS South 19"}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        here = devices.Files.here()
        for src in (here.master, here.dictionary, here.field):
            shutil.copy(src, Path(cls.tmp.name) / src.name)
        cls.files = devices.Files.under(Path(cls.tmp.name))
        rows = list(csv.DictReader(io.StringIO(cls.files.field.read_text(encoding="utf-8"))))
        hit = 0
        for r in rows:
            if (r["level"], r["id"]) in cls.RENAMES:
                r["user_name"] = cls.RENAMES[(r["level"], r["id"])]
                hit += 1
        assert hit == len(cls.RENAMES), hit
        cls.files.field.write_text(devices.master_text(rows), encoding="utf-8")
        cls.page = ld.outputs(cls.files)[ld.PAGE]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_renamed_track_is_on_the_page(self):
        self.assertIn("<td>Yard track Y2</td><td>S-9</td>", self.page)          # the section list
        self.assertIn("South Yard S-R, S-9, S-2, S-3, S-4", self.page)          # the overview's label table
        self.assertNotIn(">S-1<", self.page)
        self.assertNotIn("S-R, S-1,", self.page)

    def test_the_renamed_os_block_keeps_its_parts(self):
        self.assertIn("<td>Turnout 19</td><td>OS South 19</td>", self.page)
        self.assertNotIn("OS Switch 19", self.page)

    def test_nothing_else_changes(self):
        live = ld.PAGE.read_text()
        renamed = (self.page.replace("S-9", "S-1").replace("OS South 19", "OS Switch 19"))
        self.assertEqual(renamed, live)


if __name__ == "__main__":
    unittest.main()
