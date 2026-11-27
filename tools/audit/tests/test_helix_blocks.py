"""Each helix track one JMRI block from its staging switch up the helix: the plan overrides, the
detector pins, the staging map's shared blocks and the Layout Editor build's handling of them."""
from __future__ import annotations

import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
import build_device_map as bdm  # noqa: E402
from hartlib import devices, paths, tables, wiring  # noqa: E402

FIELD = devices.FIELD_FILE
import le_tables as T  # noqa: E402
from map_error import MapError  # noqa: E402
import plan_bands  # noqa: E402
import plan_tracks  # noqa: E402
import check_device_master as cdm  # noqa: E402
from hartlib import railroad, track_names  # noqa: E402


def write(text: str) -> Path:
    tmp = Path(tempfile.mkdtemp())
    p = tmp / "f.csv"
    p.write_text(text, encoding="utf-8")
    return p


def copied(edit=None) -> Path:
    """plan_overrides.json in a temporary copy of the schematic data folder (with preferences.json, and
    devices_field.csv beside it: the staging helix ends' names are its block rows', hartlib.track_names), each
    (old, new, file) of `edit` replaced once in its file."""
    import shutil
    root = Path(tempfile.mkdtemp())
    tmp = root / "schematic"
    tmp.mkdir()
    for name in ("plan_overrides.json", "preferences.json"):
        shutil.copyfile(plan_bands.HELIX_SOURCE.parent / name, tmp / name)
    shutil.copyfile(devices.field_path(plan_bands.HELIX_SOURCE.parent.parent), root / devices.FIELD_FILE)
    track_names.repo_inputs(tmp)        # the plan graphs the name store reads: the repo's, by opt-in
    for old, new, name in edit or ():
        f = (root if name == FIELD else tmp) / name
        text = f.read_text(encoding="utf-8")
        assert old in text, (old, name)
        f.write_text(text.replace(old, new, 1), encoding="utf-8")
    return tmp / "plan_overrides.json"


class HelixTracks(unittest.TestCase):
    """The helix tracks come from the plan overrides: each a staging helix end and a main_upper
    `helix` entry of one plan name, its block "Track <plan name>" by the ordinary rule, and the label drawn for it
    from the plugin's track_labels preference."""

    def test_the_committed_plan(self):
        got = plan_bands.read_helix_tracks()
        self.assertEqual(list(got), ["Helix Outer", "Helix Inner"])       # the main_upper helix map's order
        self.assertEqual({k: v["block"] for k, v in got.items()},
                         {"Helix Outer": "Track Helix Outer", "Helix Inner": "Track Helix Inner"})
        self.assertEqual((got["Helix Outer"]["staging_switch"], got["Helix Outer"]["level_switch"]), ("39", "131A"))
        self.assertEqual((got["Helix Inner"]["staging_switch"], got["Helix Inner"]["level_switch"]), ("37", "131B"))
        self.assertEqual({k: v["shown"] for k, v in got.items()},
                         {"Helix Outer": "McKees Rocks", "Helix Inner": "McKeesport"})

    def test_a_track_with_no_label_shows_its_plan_name(self):
        got = plan_bands.read_helix_tracks(copied([('"block:37B-helix": "McKeesport"', '"block:9B-end": "McKeesport"',
                                            "preferences.json")]))
        self.assertEqual(got["Helix Inner"]["shown"], "Helix Inner")

    def test_bad_plans_stop(self):
        for edit, msg in (([('"131B": "block:37B-helix"', '"131B": "block:3B-end"', "plan_overrides.json")],
                           "each helix track is one track with one name on both"),
                          ([('"131B": "block:37B-helix"', '"131B": "block:39B-helix"', "plan_overrides.json")],
                           "helix entry 131B is named 'Helix Outer'"),
                          ([("block:39B-helix", "", FIELD)],
                           "the helix at Switch 39 leg B has no named block row block:39B-helix"),
                          ([('"block:39B-helix": "McKees Rocks"', '"block:39B-helix": ""', "preferences.json")],
                           "track_labels"),
                          ([('"block:39B-helix": "McKees Rocks"', '"Helix Outer": "McKees Rocks"', "preferences.json")],
                           "track_labels key 'Helix Outer' is 'Helix Outer', not a block ID"),):
            with self.subTest(msg=msg), self.assertRaisesRegex(MapError, msg):
                plan_bands.read_helix_tracks(copied(edit))

    def staging_ends(self, change) -> Path:
        """A copy of the plan overrides whose staging `end` edit's ends are changed by `change` (a function of the
        list of ends), written back as JSON."""
        import json
        path = copied()
        whole = json.loads(path.read_text(encoding="utf-8"))
        edit = next(e for e in whole["staging"]["edits"] if e["op"] == "end")
        change(edit["ends"])
        path.write_text(json.dumps(whole, indent=1), encoding="utf-8")
        return path

    def test_a_named_end_left_in_the_hand_file_stops(self):
        """An `end` entry is [switch, leg, kind, to]: its name is the name store's (hartlib.track_names)."""
        def named(ends):
            i = next(i for i, x in enumerate(ends) if x[2] == "helix")
            ends[i] = ends[i][:2] + ["Helix Outer"] + ends[i][2:]
        with self.assertRaisesRegex(MapError, r"are not \[switch, leg, kind, to\]"):
            plan_bands.read_helix_tracks(self.staging_ends(named))

    def test_the_device_map_reads_the_helix_tracks_of_its_overrides_when_called(self):
        """build_device_map.helix_tracks reads OVERRIDES as it is then, so a patched one is honoured."""
        path = copied([(",Track Helix Inner,", ",Track Helix Lower,", FIELD)])   # one edit, both levels
        with unittest.mock.patch.object(bdm, "OVERRIDES", path):
            self.assertEqual(list(bdm.helix_tracks()), ["Helix Outer", "Helix Lower"])
            self.assertEqual(bdm.block_overrides(), path.parent / "block_overrides.csv")
        self.assertEqual(list(bdm.helix_tracks()), ["Helix Outer", "Helix Inner"])

    def test_tags_follow_the_overrides_order(self):
        helix = plan_bands.read_helix_tracks()
        over = {"helix": {"T210": "Helix Outer", "T281": "Helix Inner"}}
        self.assertEqual(plan_bands.helix_blocks(over, helix), {"H1": "Track Helix Outer", "H2": "Track Helix Inner"})
        with self.assertRaisesRegex(MapError, "the helix tracks are"):
            plan_bands.helix_blocks({"helix": {"T210": "Helix Outer"}}, helix)

    def test_a_helix_track_takes_its_block_name(self):
        found = [dict(ends=(("sw", "131"), ("helix", "H1")), trial=["Track e88"], row=0),
                 dict(ends=(("sw", "107"), ("sw", "109")), trial=["Track e1"], row=0)]
        plan_tracks.track_names(found, {"H1": "Track Helix Outer"})
        self.assertEqual([t["name"] for t in found], ["Track Helix Outer", "Track 107-109"])
        with self.assertRaisesRegex(MapError, "is no helix track of the plan overrides"):
            plan_tracks.track_names([dict(ends=(("sw", "131"), ("helix", "H2")), trial=["Track e89"], row=0)],
                           {"H1": "Track Helix Outer"})
        staging = [dict(ends=(("sw", "37"), ("helix", "H")), trial=["Track e37"], row=0)]
        plan_tracks.track_names(staging)                                  # staging's own mast rule names by the stem
        self.assertEqual(staging[0]["name"], "Track 37-H")


def track(name, a, b=None, row=0, trial=None, loop=False, helix=False, level=3):
    """An in-memory track entry, as plan_tracks.tracks gives them: ends by switch, a bumper (b None) or the helix."""
    far = ("helix", "H1") if helix else ("sw", b) if b else ("bumper", None)
    return dict(name=name, ends=(("sw", a), far), row=row, trial=trial or [f"Track {name}"], loop=loop, main=True,
                level=level)


class Pins(unittest.TestCase):
    HEAD = ",".join(wiring.COLUMNS) + "\n"
    # a helix block's detector by its id (det:<block id>; the name store names it), a track by its switches
    PINS = HEAD + "3,detector,det:block:131BB-helix,,,,,,41,1,,,planned,\n3,detector,,,227,241,,2,41,4,,,planned,\n"
    FOUND = [track("Track 227-241", "241", "227"), track("Track Helix Inner", "131", helix=True),
             track("Track Helix Outer", "131", helix=True, row=1, level=2), track("Track 241 Spur", "241")]
    SPLIT = {"Track 227-241"}

    def read(self, text):
        return bdm.read_pins(write(text), self.FOUND, self.SPLIT)

    def test_read(self):
        self.assertEqual(self.read(self.PINS), {"Track Helix Inner": (41, 0), "Track 227-241 2": (41, 3)})
        # staging's rows (level 1) are read_staging_pins': this reader passes them by
        self.assertEqual(self.read(self.PINS + "1,detector,det:block:7A-13C,,,,,,13,1,,,wired,\n"), self.read(self.PINS))
        self.assertEqual(bdm.read_pins()["Track Helix Outer"], (41, 1))        # the committed file

    def test_a_pin_by_id_finds_a_renamed_helix_track(self):
        """`ids` ({block id: name} of this build's tracks) names a helix pin's track, so a helix track the owner
        renamed is found under its new name before the device master is written again (naming-layers step 5)."""
        found = [track("Track 227-241", "241", "227"), track("Track Helix Big", "131", helix=True),
                 track("Track Helix Outer", "131", helix=True, row=1, level=2)]
        got = bdm.read_pins(write(self.PINS), found, self.SPLIT, ids={"block:131BB-helix": "Track Helix Big"})
        self.assertEqual(got, {"Track Helix Big": (41, 0), "Track 227-241 2": (41, 3)})

    def test_bad_pins_stop(self):
        outer = "det:block:131AA-helix"          # Track Helix Outer, the main level's helix track
        for text, msg in ((self.PINS + f"2,detector,{outer},,,,,,41,1,,,planned,\n", "node 41 Block 1 is line 2's as well"),
                          (self.PINS + f"2,detector,{outer},,,,,,41,4,,,planned,\n", "node 41 Block 4 is line 3's as well"),
                          (self.PINS + f"2,detector,{outer},,,,,,41,9,,,planned,\n", "a detector's index is 1 to 8, not 9"),
                          (self.PINS + "3,detector,det:block:227B-231A,,,,,,41,2,,,planned,\n", "is no helix block"),
                          (self.PINS + "3,detector,det:block:131BB-helix,,37,39,,,41,2,,,planned,\n",
                           "by its switches, not both"),
                          (self.PINS + f"2,detector,{outer},,,,,,forty,2,,,planned,\n", "node, index and ports are numbers"),
                          (self.PINS + "3,detector,,,227,241,,,41,2,,,planned,\n", "in two halves"),            # half missing
                          (self.PINS + "3,detector,,,241,,,1,41,2,,,planned,\n", "one block: no half"),          # half on a plain track
                          (self.PINS + "3,detector,,,241,227,,1,41,2,,,planned,\n", "lower first"),
                          (self.PINS + "3,detector,,,9,10,,,41,2,,,planned,\n", "no track runs Switch 9 to Switch 10"),
                          # the level: a track is looked for on its row's level only, a helix block is on one (its
                          # id is the device master's on that level alone)
                          (self.PINS + "2,detector,,,241,,,,41,2,,,planned,\n", "no track runs Switch 241 spur"),
                          (self.PINS + f"3,detector,{outer},,,,,,41,2,,,planned,\n",
                           "block:131AA-helix is no level 3 device of the device master"),
                          (self.PINS + f",detector,{outer},,,,,,41,2,,,planned,\n", "level is 1, 2 or 3, not ''"),
                          # a device by name is refused: its id names it
                          (self.PINS + "2,detector,,Track Helix Outer,,,,,41,2,,,planned,\n", "named by its id, not device"),
                          ("switch_a,switch_b,parallel,half,block,node,block_input,notes\n,,,,Track Helix Inner,41,1,\n",
                           "columns")):
            with self.subTest(msg=msg), self.assertRaisesRegex(bdm.MapError, msg):
                self.read(text)

    def test_a_helix_block_on_two_levels_stops(self):
        found = self.FOUND + [track("Track Helix Inner", "131", helix=True, row=2, level=2)]
        with self.assertRaisesRegex(bdm.MapError, "Track Helix Inner is found on levels 3 and 2"):
            bdm.read_pins(write(self.PINS), found, self.SPLIT)

    def test_the_rule_never_hands_out_a_pinned_input(self):
        nodes = bdm.Nodes([railroad.LcosNode(2, 3, "Helix", 41)])
        nodes.pin({"Track A": (41, 0), "Track B": (41, 2)})
        self.assertEqual([nodes.take(41, "block")[0] for _ in range(3)], [1, 3, 4])
        self.assertEqual(nodes.take_pinned("Track B"), (41, 2, 4102))
        self.assertIsNone(nodes.take_pinned("Track B"))         # once
        with self.assertRaisesRegex(bdm.MapError, r"Track A"):
            nodes.check_pins()                                   # Track A was never placed
        with self.assertRaisesRegex(bdm.MapError, "does not list"):
            bdm.Nodes([]).pin({"Track A": (41, 0)})

    def test_staging_nodes_are_never_handed_out_or_pinned(self):
        """lcos_nodes.csv holds staging's nodes as built: the rule neither picks one nor lets a pin take it."""
        nodes = bdm.Nodes([railroad.LcosNode(2, 1, "Helix", 11), railroad.LcosNode(3, 3, "Helix", 41)])
        self.assertEqual(nodes.pick(3, "Helix", "block"), 41)
        for pick in (lambda: nodes.pick(1, "Helix", "block"), lambda: nodes.pick_mast(1, "Helix", 1)):
            with self.assertRaisesRegex(bdm.MapError, "level 1 is staging: its nodes .* are as built"):
                pick()
        with self.assertRaisesRegex(bdm.MapError, "does not list"):
            nodes.pin({"Track A": (11, 0)})

    def test_the_committed_map_holds_the_pins(self):
        occ = {r["user_name"]: r for _n, r in devices.device_map_lines(("2", "3"), bdm.OUT) if r["layer"] == "occupancy"}
        for user, packed in (("BS Helix Inner", "M2S4100"), ("BS Helix Outer", "M2S4101"),
                             ("BS 227-241 1", "M2S4102"), ("BS 227-241 2", "M2S4103")):
            with self.subTest(user=user):
                self.assertEqual(occ[user]["system_name"], packed)
        self.assertNotIn("BS 131-H1", occ)
        self.assertNotIn("BS 131-H2", occ)


class StagingShares(unittest.TestCase):
    """A helix block is one block on two levels (check_device_master.check_rows): its staging row and its main or
    upper row, and one occupancy row on either level."""

    @staticmethod
    def row(level, layer, user, **cols):
        return dict(dict(level=level, layer=layer, user_name=user, system_name="", jmri_name="", role="", dcc="",
                         blocks="", assignment="virtual"), **cols)

    def lines(self, *extra):
        return list(enumerate([self.row("1", "block", "Track Helix Inner", system_name="IB24"),
                               self.row("3", "block", "Track Helix Inner"),
                               self.row("3", "occupancy", "BS Helix Inner", blocks="Track Helix Inner"), *extra], 2))

    def test_only_the_helix_blocks_are_on_two_levels(self):
        self.assertEqual(cdm.check_rows(self.lines(), {"Track Helix Inner"}), [])
        got = cdm.check_rows(self.lines(self.row("1", "block", "Track K-1"), self.row("3", "block", "Track K-1"),
                                        self.row("1", "occupancy", "BS K-1", blocks="Track K-1")),
                             {"Track Helix Inner"})
        self.assertTrue(any("blocks named on more than one level: ['Track Helix Inner', 'Track K-1']" in p
                            for p in got), got)
        self.assertTrue(any("exactly the helix blocks" in p for p in cdm.check_rows(self.lines(), set())))

    def test_a_helix_block_has_one_occupancy_row_on_either_level(self):
        lines = self.lines()[:2]
        self.assertEqual(cdm.check_rows(lines, {"Track Helix Inner"}),
                         ["devices_generated.csv: Track Helix Inner (level 1, block), Track Helix Inner (level 3, "
                          "block): block Track Helix Inner has 0 occupancy rows naming it (none), not one"])


class LayoutEditor(unittest.TestCase):
    def test_retired_blocks_keep_their_numbers_taken(self):
        order = T.numbered_blocks({"Track 127-131 1", "Track 201-203"} | set(T.numbering().retired))
        self.assertEqual(order.index("Track 131-H1") + 1, order.index("Track 131-H2"))
        self.assertLess(order.index("Track 127-131 1"), order.index("Track 131-H1"))
        self.assertLess(order.index("Track 131-H2"), order.index("Track 201-203"))

    def test_a_helix_blocks_detector_is_the_main_or_upper_detectors(self):
        """Staging's helix block bean is bound to the main or upper helix detector row's sensor (role helix:
        hartlib.tables_build.master_beans, naming-layers step 11), in the committed tables too."""
        root = tables.read(paths.TABLES_XML)
        full = {tables.user_name(b): b for b in tables.blocks(root)}
        layout = {tables.user_name(b): b for b in tables.layout_blocks(root)}
        for block, sensor in (("Track Helix Inner", "BS Helix Inner"), ("Track Helix Outer", "BS Helix Outer")):
            with self.subTest(block=block):
                self.assertEqual(full[block].findtext("occupancysensor"), sensor)
                self.assertEqual(layout[block].get("occupancysensor"), sensor)

if __name__ == "__main__":
    unittest.main()
