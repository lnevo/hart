"""The masts of every level, pinned mast by mast (archive/history/wiki/projects/level-unification-handoff.md, Masts). Two views:

- the committed mast file (masts.csv, every level with its `level` column: hartlib.level_masts.FIELDS), read as plain CSV,
  so the pins do not depend on how the device maps are laid out;
- the one mast process's own output over the committed plan, under RepoReadOnly: build_masts.build() (staging's
  masts by device_map_masts, with the owner's names) for staging and build_device_map.plan_masts (mast_plan.plan, the
  function build() calls) for main and upper.

A change here is a change to where masts stand or what they show, which needs the owner's approval of the panel. The
one mast process changed exactly these entries from the per-level processes before it, and no
others:
  staging 6LA and 8RA: one-low -> one-searchlight (Scale is running track by rule);
  staging virtual masts: 8LC, 10RA, 10RB, 12R and 14R went (virtual masts only as destinations);
  main and upper: 24 virtual bumper masts came (10 main, 14 upper).
Step 5 part 2 changed only staging 8RA, from an anchor mast on Scale to a turnout mast at Switch 7
(OS Switch 7 ends at the switch). Main and upper's links are parts of OS blocks but still JMRI blocks of their own, so
the masts facing them keep their facing blocks.
Naming-layers step 12 (2026-11-25, my call under the owner's rule of 2026-11-25) letters two masts of one number and
direction in the plan order of the tracks they face (plan_tracks.letter_order), not by drawn row: upper level 204R,
212L, 218R, 222L, 230L and the virtual 210L, 216L, 244R, 246L traded their A and B (Mast 210LA now faces Track 209
Spur 1). Staging's 6L and 8R pairs would too; the owner's names in the field file keep them.
"""
from __future__ import annotations

import contextlib
import csv
import re
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_device_map as bdm  # noqa: E402
import build_masts as bsm  # noqa: E402
import mast_rule  # noqa: E402  reaches_signal, patched out to see every mast the rule would place
from hartlib import level_masts  # noqa: E402
from plugin_needed import skip_or_fail  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402

# (mast without "Mast ", kind, heads, switch, facing, protects, dir) of the visible masts; heads 2 means Top and Bottom
STAGING_VISIBLE = (
    ("2L", "two-searchlight", 2, "1", "Track Main West", "OS Switch 1", "west"),
    ("2R", "one-searchlight", 1, "1", "Track Brick-Plane", "OS Switch 1", "east"),
    ("4RA", "one-low", 1, "3", "Track W-1", "OS Switch 3", "east"),
    ("4RB", "one-low", 1, "3", "Track W-2", "OS Switch 3", "east"),
    ("6LA", "one-searchlight", 1, "5", "Track Scale", "OS Switch 5", "west"),
    ("6LB", "one-searchlight", 1, "5", "Track East Ext", "OS Switch 5", "west"),
    ("6R", "two-searchlight", 2, "5", "Track Brick-Plane", "OS Switch 5", "east"),
    ("8LA", "two-low", 2, "7", "Track Barn", "OS Switch 7", "west"),
    ("8LB", "one-searchlight", 1, "7", "Track Main East", "OS Switch 7b", "west"),
    ("8RA", "one-searchlight", 1, "7", "Track Scale", "OS Switch 7", "east"),
    ("8RB", "two-searchlight", 2, "7", "Track East Ext", "OS Switch 7b", "east"),
    ("24L", "one-searchlight", 1, "23", "Track West Ext", "OS Switch 23a", "west"),
    ("24RA", "two-searchlight", 2, "23", "Track Main West", "OS Switch 23a", "east"),
    ("24RB", "one-low", 1, "23", "Track S-R", "OS Switch 23b", "east"),
    ("32R", "one-low", 1, "31", "Track 29-31", "OS Switch 31", "east"),     # a part, its own JMRI block (2026-11-20)
    ("34L", "two-searchlight", 2, "33", "Track East Lead", "OS Switch 33", "west"),
    ("34R", "one-searchlight", 1, "33", "Track Main East", "OS Switch 33", "east"),
    ("36RA", "two-searchlight", 2, "35", "Track West Ext", "OS Switch 35b", "east"),
    ("36RB", "two-searchlight", 2, "35", "Track East Lead", "OS Switch 35a", "east"),
    ("38LA", "one-searchlight", 1, "37", "Track Helix Inner", "OS Switch 37", "west"),
    ("38LB", "one-searchlight", 1, "37", "Track K-2", "OS Switch 37", "west"),
    ("40LA", "two-searchlight", 2, "39", "Track K-1", "OS Switch 39", "west"),
    ("40LB", "two-searchlight", 2, "39", "Track Helix Outer", "OS Switch 39", "west"),
    ("67", "one-searchlight", 1, "", "Track K-2", "Track K-1", "west"),
    ("68", "one-searchlight", 1, "", "Track K-1", "Track K-2", "east"),
)
# (mast, switch, facing, protects, dir) of the virtual masts (IF$vsm, one-low, no heads)
STAGING_VIRTUAL = (
    ("4LA", "", "Track W-1", "", "west"),
    ("4LB", "", "Track W-2", "", "west"),
    ("10LA", "", "Track EH-2", "", "west"),
    ("10LB", "", "Track EH-3", "", "west"),
    ("12L", "", "Track EH-1", "", "west"),
)
MAIN_UPPER_VISIBLE = (
    ("A83", "one-searchlight", 1, "", "Track 107 Loop 2", "Track 107 Loop 1", "west"),
    ("A84", "one-searchlight", 1, "", "Track 107 Loop 1", "Track 107 Loop 2", "east"),
    ("108LA", "two-searchlight", 2, "107", "Track 107 Loop 1", "OS Switch 107", "west"),
    ("108LB", "two-searchlight", 2, "107", "Track 107 Loop 2", "OS Switch 107", "west"),
    ("110L", "two-low", 2, "109", "Track 105-109", "OS Switch 109", "west"),
    ("112L", "two-low", 2, "111", "Track 101-111", "OS Switch 111", "west"),
    ("118L", "two-low", 2, "117", "Track 115-117", "OS Switch 117", "west"),
    ("120RA", "two-searchlight", 2, "119", "Track 119-123", "OS Switch 119", "east"),
    ("120RB", "two-searchlight", 2, "119", "Track 119-121", "OS Switch 119", "east"),
    ("124LA", "two-searchlight", 2, "123", "Track 119-123", "OS Switch 123", "west"),
    ("124LB", "two-searchlight", 2, "123", "Track 121-123", "OS Switch 123", "west"),
    ("126RA", "two-searchlight", 2, "125", "Track 125-127", "OS Switch 125", "east"),
    ("126RB", "two-low", 2, "125", "Track 125-129", "OS Switch 125", "east"),
    ("128LA", "two-searchlight", 2, "127", "Track 125-127", "OS Switch 127", "west"),
    ("128LB", "two-searchlight", 2, "127", "Track 127-221", "OS Switch 127", "west"),
    ("132RA", "two-searchlight", 2, "131", "Track Helix Outer", "OS Switch 131", "east"),
    ("132RB", "two-searchlight", 2, "131", "Track Helix Inner", "OS Switch 131", "east"),
    ("B92", "one-searchlight", 1, "", "Track 227-241 2", "Track 227-241 1", "east"),
    ("B93", "one-searchlight", 1, "", "Track 227-241 1", "Track 227-241 2", "west"),
    ("202R", "two-low", 2, "201", "Track 201-205", "OS Switch 201", "east"),
    ("204RA", "two-searchlight", 2, "203", "Track 203-211", "OS Switch 203", "east"),
    ("204RB", "two-low", 2, "203", "Track 203-207", "OS Switch 203", "east"),
    ("212LA", "one-searchlight", 1, "211", "Track 203-211", "OS Switch 211", "west"),
    ("212LB", "two-low", 2, "211", "Track 207-211", "OS Switch 211", "west"),
    ("212RA", "one-searchlight", 1, "211", "Track 211-217 1", "OS Switch 211", "east"),
    ("212RB", "two-searchlight", 2, "211", "Track 211-217 2", "OS Switch 211", "east"),
    ("218LA", "one-searchlight", 1, "217", "Track 211-217 1", "OS Switch 217", "west"),
    ("218LB", "two-searchlight", 2, "217", "Track 211-217 2", "OS Switch 217", "west"),
    ("218RA", "one-searchlight", 1, "217", "Track 217-221", "OS Switch 217", "east"),
    ("218RB", "two-searchlight", 2, "217", "Track 217-219", "OS Switch 217", "east"),
    ("220R", "two-searchlight", 2, "219", "Track 217-219", "OS Switch 219", "east"),
    ("222LA", "one-searchlight", 1, "221", "Track 217-221", "OS Switch 221", "west"),
    ("222LB", "two-searchlight", 2, "221", "Track 221-223", "OS Switch 221", "west"),
    ("222R", "two-searchlight", 2, "221", "Track 127-221", "OS Switch 221", "east"),
    ("224LA", "one-searchlight", 1, "223", "Track 223-225 1", "OS Switch 223", "west"),
    ("224LB", "one-searchlight", 1, "223", "Track 223-225 2", "OS Switch 223", "west"),
    ("224R", "two-searchlight", 2, "223", "Track 221-223", "OS Switch 223", "east"),
    ("226RA", "two-searchlight", 2, "225", "Track 223-225 1", "OS Switch 225a", "east"),
    ("226RB", "two-searchlight", 2, "225", "Track 223-225 2", "OS Switch 225d", "east"),
    ("228RA", "two-low", 2, "227", "Track 227-231", "OS Switch 227", "east"),
    ("228RB", "two-searchlight", 2, "227", "Track 227-241 1", "OS Switch 227", "east"),
    ("230LA", "two-low", 2, "229", "Track 229-233", "OS Switch 229", "west"),
    ("230LB", "two-searchlight", 2, "229", "Track 229-241", "OS Switch 229", "west"),
    ("242L", "one-low", 1, "241", "Track 241 Spur", "OS Switch 241", "west"),
)
MAIN_UPPER_VIRTUAL = (
    # main (10)
    ("102RA", "", "Track 101 Spur 1", "", "east"),
    ("102RB", "", "Track 101 Spur 2", "", "east"),
    ("104R", "", "Track 103 Spur", "", "east"),
    ("114RA", "", "Track 113 Spur 1", "", "east"),
    ("114RB", "", "Track 113 Spur 2", "", "east"),
    ("116R", "", "Track 115 Spur", "", "east"),
    ("120RC", "", "Track 119 Spur", "", "east"),
    ("122R", "", "Track 121 Spur", "", "east"),
    ("130LA", "", "Track 129 Spur 1", "", "west"),
    ("130LB", "", "Track 129 Spur 2", "", "west"),
    # upper (14)
    ("206L", "", "Track 205 Spur", "", "west"),
    ("210LA", "", "Track 209 Spur 1", "", "west"),
    ("210LB", "", "Track 209 Spur 2", "", "west"),
    ("214L", "", "Track 213 Spur", "", "west"),
    ("216LA", "", "Track 215 Spur 1", "", "west"),
    ("216LB", "", "Track 215 Spur 2", "", "west"),
    ("232L", "", "Track 231 Spur", "", "west"),
    ("236R", "", "Track 235 Spur", "", "east"),
    ("240L", "", "Track 239 Spur", "", "west"),
    ("242R", "", "Track 241 Spur", "", "east"),
    ("244RA", "", "Track 243 Spur 1", "", "east"),
    ("244RB", "", "Track 243 Spur 2", "", "east"),
    ("246LA", "", "Track 245 Spur 1", "", "west"),
    ("246LB", "", "Track 245 Spur 2", "", "west"),
)
INTERMEDIATES = {"67", "68", "A83", "A84", "B92", "B93"}
# masts the rule must not place: 126L faces Track 121-125 into Switch 125, and every route it would clear ends at
# Switch 129's spur bumpers (mast_routes.reaches_signal)
DROPPED = {"126L"}

SYSTEM = re.compile(r"IF\$(shsm|vsm):basic:([\w-]+)\(")


STAGING, MAIN_UPPER = {"1"}, {"2", "3"}


def file_masts(path: Path, levels: set) -> tuple[list, list]:
    """(visible, virtual) pins of the committed mast file's rows of `levels`, one per row (a duplicated row shows), in
    the shape of the tables above. Fails on a system name
    that is no basic SignalHeadSignalMast or VirtualSignalMast."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != list(level_masts.FIELDS):
            raise AssertionError(f"{path.name}: columns {reader.fieldnames}, not {list(level_masts.FIELDS)}")
        rows = [r for r in reader if r["level"] in levels]
    visible, virtual = [], []
    for r in rows:
        hit = SYSTEM.match(r["system_name"])
        if not hit:
            raise AssertionError(f"{path.name}: {r['mast']} has system name {r['system_name']!r}")
        name = r["mast"].removeprefix("Mast ")
        heads = len([h for h in r["head_system_names"].split(";") if h])
        if hit.group(1) == "vsm":
            if (hit.group(2), heads) != ("one-low", 0):
                raise AssertionError(f"{path.name}: virtual {r['mast']} is {hit.group(2)} with {heads} heads")
            virtual.append((name, r["switch"], r["facing"], r["protects"], r["dir"]))
        else:
            visible.append((name, hit.group(2), heads, r["switch"], r["facing"], r["protects"], r["dir"]))
    return visible, virtual


class CommittedMastFiles(unittest.TestCase):
    """The committed mast files hold exactly the pinned masts (no plugin needed)."""

    def test_staging(self):
        visible, virtual = file_masts(level_masts.PATH, STAGING)
        self.assertEqual(sorted(visible), sorted(STAGING_VISIBLE))
        self.assertEqual(sorted(virtual), sorted(STAGING_VIRTUAL))

    def test_main_and_upper(self):
        visible, virtual = file_masts(level_masts.PATH, MAIN_UPPER)
        self.assertEqual(sorted(visible), sorted(MAIN_UPPER_VISIBLE))
        self.assertEqual(sorted(virtual), sorted(MAIN_UPPER_VIRTUAL))

    def test_mast_names_are_unique_on_every_level(self):
        names = [r[0] for part in file_masts(level_masts.PATH, STAGING | MAIN_UPPER) for r in part]
        self.assertEqual(len(names), len(set(names)), "masts.csv: a mast name is given twice")

    def test_virtual_mast_counts_per_level(self):
        self.assertEqual(len(file_masts(level_masts.PATH, STAGING)[1]), 5)
        levels = [level_masts.virtual_level(r["system_name"]) for r in level_masts.read(levels=(2, 3))
                  if r["system_name"].startswith("IF$vsm:")]
        self.assertEqual((levels.count(2), levels.count(3)), (10, 14))      # by each level's ordinal thousand

    def test_the_intermediates_stand_at_no_switch_and_show_high(self):
        for table in (STAGING_VISIBLE, MAIN_UPPER_VISIBLE):
            for name, kind, heads, switch, *_ in table:
                if name in INTERMEDIATES:
                    self.assertEqual((kind, heads, switch), ("one-searchlight", 1, ""), name)
        got = {r[0] for t in (STAGING_VISIBLE, MAIN_UPPER_VISIBLE) for r in t if r[0] in INTERMEDIATES}
        self.assertEqual(got, INTERMEDIATES)

    def test_dropped_masts_are_in_no_file(self):
        names = {r[0] for part in file_masts(level_masts.PATH, STAGING | MAIN_UPPER) for r in part}
        self.assertFalse(names & DROPPED)


def main_upper_rule(no_pruning: bool = False) -> dict:
    """mast_plan.plan's main and upper masts over the committed plan, through build_device_map.plan_masts, the
    function build() calls. `no_pruning` turns reaches_signal off, to show what it leaves out."""
    import build_layout_le as bl
    try:
        bands, joined, runs, corners = bdm.solve()
    except bl.BuildError as exc:
        skip_or_fail(exc, "the rule pins")
    rr = bdm.railroad.Railroad(bdm.sources(), upto="inputs")
    found = bdm.named_tracks(bands, joined, runs, rr.plan_overrides.data)
    switches = bdm.railroad.join_main_upper(rr.level_control_points, rr.local_switches, bdm.SWITCHES.name)
    cp_of = {s: sw.cp for s, sw in switches.items() if sw.cp}
    with contextlib.ExitStack() as stack:
        if no_pruning:
            stack.enter_context(unittest.mock.patch.object(mast_rule, "reaches_signal", lambda *a, **k: True))
        planned, _corners, _split, _layer = bdm.plan_masts(bands, joined, runs, found, cp_of, corners)
    return planned


class SignalsNameTracksAsTheDeviceMap(RepoReadOnly, unittest.TestCase):
    def test_build_signals_takes_the_device_maps_named_tracks(self):
        """build_signals.main_upper_rows names its tracks with build_device_map.named_tracks (the name store, then the
        rule), so a stored main or upper name cannot give the signals other track names than the device map's."""
        import build_layout_le as bl
        import build_signals as bs
        try:
            bdm.solve()
        except bl.BuildError as exc:
            skip_or_fail(exc, "the rule pins")
        calls = []
        real = bdm.named_tracks

        def spy(*a, **k):
            calls.append(a)
            return real(*a, **k)
        with unittest.mock.patch.object(bdm, "named_tracks", spy):
            rows = bs.main_upper_rows()
        self.assertTrue(calls)
        self.assertTrue(rows)


class RuleOutput(RepoReadOnly, unittest.TestCase):
    """The rule over the committed plan gives the pinned masts (needs the plugin at its pinned commit; skipped
    without it). Data checks: a failure can mean the plan changed, not the code."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            bsm.sdm.lc.plugin()
        except bsm.sdm.lc.BuildError as exc:
            skip_or_fail(exc, "the rule pins")
        _want, cls.gen, cls.virtual = bsm.build()
        cls.planned = main_upper_rule()
        cls.mu = cls.planned["home"] + cls.planned["intermediates"]

    def test_staging_visible(self):
        got = [(m["mast"].removeprefix("Mast "), m["kind"], m["heads"], m["switch"], m["facing"], m["protects"],
                m["dir"]) for m in self.gen]
        self.assertEqual(sorted(got), sorted(STAGING_VISIBLE))

    def test_staging_virtual(self):
        got = [(m["mast"].removeprefix("Mast "), m["switch"], m["facing"], m["protects"], m["dir"])
               for m in self.virtual]
        self.assertEqual(sorted(got), sorted(STAGING_VIRTUAL))

    def test_main_and_upper_visible(self):
        # a home mast's facing is its track's block (half), its protects the switch's OS block or, at a double
        # crossover, its corner block; an intermediate names both blocks
        got = [(m["name"], m["kind"], m["heads"], m["switch"], m["facing"],
                m["protects"] or f"OS Switch {m['switch']}", m["dir"]) for m in self.planned["home"]]
        got += [(m["name"], "one-searchlight", 1, "", m["facing"], m["protects"], m["dir"])
                for m in self.planned["intermediates"]]
        self.assertEqual(sorted(got), sorted(MAIN_UPPER_VISIBLE))

    def test_main_and_upper_virtual(self):
        got = [(m["name"], "", m["facing"], "", m["dir"]) for m in self.planned["virtual"]]
        self.assertEqual(sorted(got), sorted(MAIN_UPPER_VIRTUAL))

    def test_each_virtual_mast_is_a_destination_of_a_visible_mast(self):
        visible = {m["name"] for m in self.mu}
        for m in self.planned["virtual"]:
            self.assertTrue(m["needed_by"] and set(m["needed_by"]) <= visible, m["name"])

    def test_the_rule_gives_no_name_twice(self):
        for names in ([m["name"] for m in self.mu + self.planned["virtual"]],
                      [m["mast"] for m in self.gen + self.virtual]):
            self.assertEqual(len(names), len(set(names)), "a mast name is given twice")

    def test_126L_is_left_out_only_by_the_reaches_signal_pruning(self):
        self.assertNotIn("126L", {m["name"] for m in self.mu})
        unpruned = {m["name"]: m for m in main_upper_rule(no_pruning=True)["home"]}
        self.assertIn("126L", unpruned)
        self.assertEqual(unpruned["126L"]["track"], "Track 121-125")


if __name__ == "__main__":
    unittest.main()
