"""hartlib.block_lengths: the plan file and the measured file, the two answers (plan and operating length), and the
readers on each side (ADR-039 lane L8, owner 2026-11-25).

A reader of the plan length (the schematic, the Layout Editor drawing, mast and signal placement, the levels and
layout pages) never calls the operating reader, and a reader of the operating length (the Dispatcher's block lengths
in tables.xml, speed matching) never calls a plan reader. SIDES lists each module that calls a reader of
hartlib.block_lengths; a module that calls one and is not listed fails, so a new reader picks a side.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1]
from hartlib import block_lengths as BL  # noqa: E402
from hartlib import paths, railroad_facts, tables  # noqa: E402

REPO = paths.REPO_ROOT
PLAN_FNS = {"read_plan", "plan_blocks", "plan_lengths", "plan_cm", "plan_length"}
OPERATING_FNS = {"operating_lengths", "operating_length"}
MEASURED_FNS = {"measured_lengths", "read_measured", "write_measured", "measured_text"}
PLAN, OPERATING, BOTH = "plan", "operating", "both"

# module -> its side. "both": prints the plan length and the length tables.xml holds side by side.
SIDES = {
    "tools/schematic/build_signals.py": PLAN,           # mast distances on the drawn tracks
    "tools/schematic/device_map_masts.py": PLAN,        # staging mast placement (build_device_map, build_masts)
    "tools/schematic/le_names.py": PLAN,                # the Layout Editor drawing's staging cuts and main lengths
    "tools/schematic/plan_lengths.py": PLAN,            # the plan file's writer
    "tools/anyrail/levels_page.py": PLAN,               # the track plan page
    "www/scripts/build_layout_docs.py": PLAN,           # the layout documentation page
    "tools/hartlib/src/hartlib/railroad.py": PLAN,      # Railroad.block_lengths
    "tools/hartlib/src/hartlib/railroad_invariants.py": PLAN,
    "tools/hartlib/src/hartlib/tables_build.py": OPERATING,     # the Dispatcher's block lengths in tables.xml
    "jmri/layouts/hart/scripts/infer_block_lengths.py": OPERATING,  # speed matching, the measured file's writer
    "jmri/layouts/hart/scripts/export_track_lengths.py": BOTH,  # docs/jmri/TRACK_LENGTHS.md and its tables check
}
# the modules that may read the measured rows themselves: the pages that print them beside the plan length, the
# export, the measured file's writer, and the facts check that holds its ids to the plan file
MEASURED_READERS = {"tools/anyrail/levels_page.py", "www/scripts/build_layout_docs.py",
                    "jmri/layouts/hart/scripts/export_track_lengths.py",
                    "jmri/layouts/hart/scripts/infer_block_lengths.py",
                    "tools/hartlib/src/hartlib/railroad_invariants.py"}
CALL = re.compile(r"\bblock_lengths\.(\w+)\(")
SKIP = ("archive/", "external/", "reference/", "tools/cats/src-repo/")


def calls() -> dict[str, set[str]]:
    """{module: the hartlib.block_lengths functions it calls} of every tracked script outside tests."""
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=REPO, capture_output=True, text=True,
                           check=True).stdout.split()
    out = {}
    for f in files:
        if f.startswith(SKIP) or "/tests/" in f or f == "tools/hartlib/src/hartlib/block_lengths.py":
            continue
        text = (REPO / f).read_text(encoding="utf-8", errors="replace")
        if "block_lengths" not in text:
            continue
        found = {m.group(1) for m in CALL.finditer(text)} & (PLAN_FNS | OPERATING_FNS | MEASURED_FNS)
        if found or re.search(r"from hartlib\.block_lengths import|from \.block_lengths import", text):
            out[f] = found or {"(imported by name)"}
    return out


class Sides(unittest.TestCase):
    """Each reader takes the length of its side only."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.calls = calls()

    def test_every_reader_is_on_a_side(self) -> None:
        self.assertEqual(sorted(set(self.calls) - set(SIDES)), [],
                         "call the readers as block_lengths.<name>() and list the module in SIDES")

    def test_no_reader_takes_the_other_sides_length(self) -> None:
        bad = []
        for f, fns in self.calls.items():
            side = SIDES.get(f)
            if side == PLAN and fns & OPERATING_FNS:
                bad.append(f"{f}: a plan-side reader calls {sorted(fns & OPERATING_FNS)}")
            if side == OPERATING and fns & PLAN_FNS:
                bad.append(f"{f}: an operating-side reader calls {sorted(fns & PLAN_FNS)}")
            if fns & MEASURED_FNS and f not in MEASURED_READERS:
                bad.append(f"{f}: reads the measured rows ({sorted(fns & MEASURED_FNS)})")
        self.assertEqual(bad, [])

    def test_each_listed_reader_calls_its_sides_reader(self) -> None:
        want = {PLAN: PLAN_FNS, OPERATING: OPERATING_FNS, BOTH: PLAN_FNS | OPERATING_FNS}
        stale = [f for f, side in SIDES.items() if not self.calls.get(f, set()) & want[side]]
        self.assertEqual(stale, [], "a module in SIDES no longer reads a length: drop it")

    def test_the_check_sees_a_reader_on_the_wrong_side(self) -> None:
        """CALL finds a qualified call, so a plan-side module that called the operating reader would be caught."""
        self.assertEqual({m.group(1) for m in CALL.finditer("x = block_lengths.operating_lengths()")},
                         {"operating_lengths"})


class Files(unittest.TestCase):
    """The two files read strictly; a copy of the repo's in a temporary folder."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.plan = self.tmp / BL.PLAN_NAME
        shutil.copyfile(BL.PLAN, self.plan)
        shutil.copyfile(BL.MEASURED, self.tmp / BL.MEASURED_NAME)
        self.text = self.plan.read_text(encoding="utf-8")
        self.mtext = (self.tmp / BL.MEASURED_NAME).read_text(encoding="utf-8")

    def fails(self, fn, pattern: str) -> None:
        with self.assertRaisesRegex(railroad_facts.FactsError, pattern):
            fn()

    def test_the_repo_files(self) -> None:
        self.assertEqual(BL.measured_path(BL.PLAN), BL.MEASURED)
        plan = BL.read_plan()
        measured = BL.read_measured()
        self.assertTrue(measured and set(measured) <= set(plan))
        self.assertEqual(list(plan.values())[0].level, "1")
        blocks = BL.plan_blocks()
        self.assertEqual(len(blocks), len(plan))
        w1 = blocks["Track W-1"]
        self.assertEqual((w1.level, w1.id, w1.occupancy_sensor, w1.plan_in), ("1", "block:3B-end", "Block 4-4", 105.2))
        self.assertEqual(blocks["Track Helix Outer"].occupancy_sensor, "BS Helix Outer")   # no occupancy row
        # a part reports on its block's detector
        self.assertEqual(blocks["Track 1-3 at 1"].occupancy_sensor, blocks["OS Switch 1"].occupancy_sensor)

    def test_plan_and_operating_lengths(self) -> None:
        plan, operating = BL.plan_lengths(self.plan), BL.operating_lengths(self.plan)
        measured = BL.measured_lengths(self.plan)
        self.assertEqual(set(plan), set(operating))
        for name in plan:
            if name not in measured:
                self.assertEqual(operating[name], plan[name], name)
        mw = measured["Track Main West"]
        self.assertEqual((mw.id, mw.measured_in, mw.run, mw.date), ("block:1A-23A", 217.3, "loop1 laps", "2026-11-08"))
        self.assertEqual(plan["Track Main West"], 231.0)
        self.assertEqual(BL.plan_length("block:1A-23A", self.plan), 231.0)
        self.assertEqual(BL.operating_length("block:1A-23A", self.plan), 217.3)
        self.assertEqual(BL.operating_length("block:3B-end", self.plan), 105.2)
        self.assertEqual(BL.plan_cm(self.plan)["Track Main West"], 231.0 * 2.54)
        self.fails(lambda: BL.plan_length("block:nowhere", self.plan), "no row for block:nowhere")
        # OS Switch 1's detector holds the part Track 1-3 at 1 (5.0 in): the OS block takes the measured rest
        self.assertEqual((operating["OS Switch 1"], operating["Track 1-3 at 1"]), (17.6, 5.0))
        self.assertEqual(BL.operating_length("os:1", self.plan), 17.6)

    def test_each_measured_detector_adds_up_to_its_measured_length(self) -> None:
        """A measured length is the timing of the whole detector: the operating lengths of the detector's JMRI blocks
        add up to it, so the Dispatcher counts no track twice."""
        blocks, operating, measured = BL.plan_blocks(self.plan), BL.operating_lengths(self.plan), BL.measured_lengths(self.plan)
        groups = BL.detector_blocks(blocks)
        shared = 0
        for name, m in measured.items():
            names = groups[(blocks[name].level, blocks[name].occupancy_sensor)]
            shared += len(names) > 1
            self.assertAlmostEqual(sum(operating[n] for n in names), m.measured_in, places=6, msg=name)
        self.assertGreaterEqual(shared, 3)              # OS Switch 1, 15 and 35a carry parts

    def test_a_detector_its_parts_overfill_stops(self) -> None:
        path = self.tmp / BL.MEASURED_NAME
        os1 = next(line for line in self.mtext.splitlines() if line.startswith("os:1,"))
        path.write_text(self.mtext.replace(os1, os1.replace(",22.6,", ",5.0,")), encoding="utf-8")
        self.fails(lambda: BL.operating_lengths(self.plan), "OS Switch 1: measured 5.0 in .* add up to 5.0 in")
        path.write_text(self.mtext + "block:1B-3A:1/2,6.0,loop1 laps,2026-11-08,\n", encoding="utf-8")
        self.fails(lambda: BL.operating_lengths(self.plan), "are all measured")

    def test_a_bad_plan_row_stops(self) -> None:
        w1 = next(line for line in self.text.splitlines() if line.startswith("1,block:3B-end,"))
        for bad, why in ((w1.replace(",105.2,", ",long,"), "plan_in 'long' is not a number"),
                         (w1.replace(",105.2,", ",,"), "no plan_in"),
                         (w1.replace(",105.2,", ",-1,"), "plan_in -1 is below zero"),
                         (w1.replace("1,block:3B-end,", "4,block:3B-end,"), "a level 1 to 3"),
                         (w1.replace("1,block:3B-end,", "1,,"), "a level 1 to 3")):
            self.plan.write_text(self.text.replace(w1, bad), encoding="utf-8")
            self.fails(lambda: BL.read_plan(self.plan), f"line 2: .*{why}")
        self.plan.write_text(self.text + w1.replace("1,", "2,", 1) + "\n", encoding="utf-8")   # an id on two levels
        self.fails(lambda: BL.read_plan(self.plan), "each id once")
        self.plan.write_text(self.text.replace(w1, w1.replace("block:3B-end", "block:3Z-end")), encoding="utf-8")
        self.fails(lambda: BL.plan_blocks(self.plan), "line 2: block:3Z-end is no level 1 block row of the device "
                                                     "master")

    def test_a_bad_measured_row_stops(self) -> None:
        path = self.tmp / BL.MEASURED_NAME
        first = self.mtext.splitlines()[1]
        ident, inches = first.split(",")[:2]
        for bad, why in ((first.replace(ident, "block:nowhere", 1), "no row of block_lengths.csv"),
                         (first.replace(f",{inches},", ",0,", 1), "measured_in 0 is not above zero"),
                         (first.replace("loop1 laps", ""), "run '' and date"),
                         (first.replace("2026-11-08", "8 Nov"), "date '8 Nov'")):
            path.write_text(self.mtext.replace(first, bad), encoding="utf-8")
            self.fails(lambda: BL.read_measured(plan=self.plan), f"line 2: .*{why}")
        path.write_text(self.mtext + first + "\n", encoding="utf-8")
        self.fails(lambda: BL.read_measured(plan=self.plan), "or is given twice")

    def test_write_measured_round_trips(self) -> None:
        rows = list(BL.read_measured(plan=self.plan).values())
        BL.write_measured(rows, self.plan)
        self.assertEqual((self.tmp / BL.MEASURED_NAME).read_text(encoding="utf-8"), self.mtext)
        ok = BL.Measured(0, "block:3B-end", 1.0, "loop1 laps", "2026-11-08", "")
        from dataclasses import replace
        for bad, why in ((replace(ok, id="block:nowhere"), "'block:nowhere' is no row"),
                         (replace(ok, id=rows[0].id), "or is given twice"),
                         (replace(ok, measured_in=0.0), "measured_in 0.0 is not above zero"),
                         (replace(ok, run=""), "run '' and date"),
                         (replace(ok, date="Nov 8"), "date 'Nov 8'")):
            self.fails(lambda: BL.write_measured(rows + [bad], self.plan), why)
        self.assertEqual((self.tmp / BL.MEASURED_NAME).read_text(encoding="utf-8"), self.mtext)   # nothing written

    def test_two_blocks_with_one_name_stop(self) -> None:
        from hartlib import devices
        rows = [r.cells() for r in devices.load()]
        for r in rows:
            if r["level"] == "1" and r["id"] == "block:3C-end":
                r["user_name"] = "Track W-1"
        with unittest.mock.patch.object(devices, "load", return_value=devices.as_device_rows(rows)):
            self.fails(lambda: BL.plan_blocks(self.plan), "block:3C-end is named 'Track W-1', as block:3B-end is")


class Outputs(unittest.TestCase):
    """The committed outputs take each side's length."""

    def test_tables_xml_holds_the_operating_length(self) -> None:
        held = {tables.user_name(b): float(b.get("length")) for b in tables.blocks(tables.read(paths.TABLES_XML))
                if b.get("length") and tables.user_name(b)}
        operating, measured = BL.operating_lengths(), BL.measured_lengths()
        self.assertTrue(measured)
        for name, inches in operating.items():
            self.assertAlmostEqual(held[name], round(inches * BL.MM_PER_INCH, 1), places=1, msg=name)

    def test_the_pi_reader_gives_each_sensors_length(self) -> None:
        """speedmatch/analyze.py reads the two files without hartlib (the Pi's copy), by sensor: a timed detector's
        length is its whole measured length, the operating lengths of its blocks added up; any other block's is its
        plan length."""
        sys.path.insert(0, str(paths.LAYOUT_SCRIPTS / "speedmatch"))
        import analyze
        blocks, operating, measured = BL.plan_blocks(), BL.operating_lengths(), BL.measured_lengths()
        groups = BL.detector_blocks(blocks)
        for route, loop in analyze.ROUTES.items():
            got = analyze.load_lengths(trusted=("timed", "plan"), loop=loop)
            for sensor, name in loop:
                b = blocks[name]
                want = sum(operating[n] for n in groups[(b.level, b.occupancy_sensor)]) if name in measured else b.plan_in
                self.assertAlmostEqual(got[sensor], want * BL.MM_PER_INCH, msg=f"{route} {name}")


if __name__ == "__main__":
    unittest.main()
