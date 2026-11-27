"""block_layer.py, the one block process of every level, and build_device_map.staging_rows, which writes staging's
block and occupancy rows from it: the rule, block_overrides.csv's rows and stops, and the invariants. Runs over the committed drawing (needs the plugin; skipped without it,
failing with SCHEMATIC_REQUIRED=1); every write goes to a temporary folder."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import block_layer as BL  # noqa: E402
import build_device_map as bdm  # noqa: E402
from hartlib import devices  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402

HEAD = ",".join(BL.block_override_rows.OVERRIDE_COLUMNS) + "\n"
# a piece of track at one end inside an OS block, its length given (a row OS Switch 7 no longer has); the OS block
# by its device ID
SCALE_AT_7 = "1,track,5,7,2,7,os:7:A-13C,23,,a test row\n"
# the 25 main and upper links (tracks between two switches under LINK_CM), each in the lower-numbered switch's OS
# block (LINK_CM 50 on every level; at a double crossover the corner block of its leg), but where a
# home mast stands at a switch's points facing the link: then in the OS block at its other end (125-129, 201-205,
# 227-231, 229-233 for Masts 126RB, 202R, 228RA and 230LB: the block boundary is at the mast)
MAIN_UPPER_LINKS = {
    "Track 101-103": "OS Switch 101", "Track 105-109": "OS Switch 105", "Track 109-111": "OS Switch 109",
    "Track 111-117": "OS Switch 111", "Track 113-115": "OS Switch 113", "Track 115-117": "OS Switch 115",
    "Track 117-119": "OS Switch 117", "Track 121-123": "OS Switch 121", "Track 123-125": "OS Switch 123",
    "Track 125-129": "OS Switch 129", "Track 127-131 2": "OS Switch 127", "Track 201-203": "OS Switch 201",
    "Track 201-205": "OS Switch 205", "Track 201-219": "OS Switch 201", "Track 205-209": "OS Switch 205",
    "Track 213-215": "OS Switch 213", "Track 219-221": "OS Switch 219", "Track 225-227": "OS Switch 225c",
    "Track 225-229": "OS Switch 225b", "Track 227-231": "OS Switch 231", "Track 229-233": "OS Switch 233",
    "Track 231-237": "OS Switch 231", "Track 235-243": "OS Switch 235", "Track 237-239": "OS Switch 237",
    "Track 239-245": "OS Switch 239",
}


def temp_file(name: str, text: str) -> Path:
    """`text` in a new file `name` in a new temporary folder, outside the repo."""
    p = Path(tempfile.mkdtemp()) / name
    p.write_text(text, encoding="utf-8")
    return p


def remove(p: Path) -> None:
    """The file and its folder, by full path (shutil.rmtree's relative unlinks look like repo writes to the guard)."""
    os.remove(p)
    os.rmdir(p.parent)


class OnTheDrawing(RepoReadOnly, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import build_layout_le as bl
        try:
            cls.bands, cls.joined, runs, cls.corners = bdm.solve()
        except bl.BuildError as exc:
            if os.environ.get("SCHEMATIC_REQUIRED") == "1":
                raise AssertionError(f"needs the plugin (SCHEMATIC_REQUIRED=1): {exc}")
            raise unittest.SkipTest(str(exc))
        cls.runs = staticmethod(runs)
        over = bdm.layer_files.read("plan_overrides", bdm.STAGING_SHEET, bdm.OVERRIDES.parent)
        cls.levels = bdm.band_levels(over)
        cls.found = bdm.named_tracks(cls.bands, cls.joined, cls.runs, over)
        cls.split = BL.split_edges(cls.found, cls.levels, bdm.block_overrides())
        cls.committed = BL.overrides_path().read_text(encoding="utf-8")

    def layer(self, text: str | None = None) -> BL.Layer:
        """The staging layer with block_overrides.csv's text `text` (default: the committed file)."""
        if text is None:
            return BL.layer(self.bands, self.runs, self.found, self.levels, self.split,
                            BL.read_exceptions(self.found, self.bands, self.levels))
        p = temp_file("block_overrides.csv", text)
        try:
            ex = BL.read_exceptions(self.found, self.bands, self.levels, p)
        finally:
            remove(p)
        return BL.layer(self.bands, self.runs, self.found, self.levels, self.split, ex)

    posts = None            # the home masts' places for main_upper (None: the rule's)

    def main_upper(self, text: str | None = None) -> BL.Layer:
        """The main and upper layer (build_device_map.main_upper_layer) with block_overrides.csv's text `text`
        (default: the committed file)."""
        found = bdm.named_tracks(self.bands, self.joined, self.runs)
        rr = bdm.railroad.Railroad(bdm.sources(), upto="inputs")
        switches = bdm.railroad.join_main_upper(rr.level_control_points, rr.local_switches, bdm.SWITCHES.name)
        cp_of = {s: sw.cp for s, sw in switches.items() if sw.cp}
        p = bdm.block_overrides() if text is None else temp_file("block_overrides.csv", text)
        try:                    # one file for every kind of its rows: the splits and the track pieces alike
            split, corners = bdm.split_edges(p, found=found), bdm.corner_blocks_of(self.bands, self.corners)
            _home, posts = bdm.home_and_posts(self.bands, self.joined, found, bdm.LEVELS, cp_of, corners,
                                              set(split.values()))
            self.last_posts, self.mu_found = posts, found
            return bdm.main_upper_layer(self.bands, self.runs, found, split, corners,
                                        posts if self.posts is None else self.posts, overrides=p)
        finally:
            if text is not None:
                remove(p)

    def without(self, needle: str) -> str:
        return "".join(line for line in self.committed.splitlines(True) if needle not in line)

    def stops(self, text: str, message: str):
        with self.assertRaisesRegex(BL.BlockError, message):
            self.layer(text)

    # ---------------------------------------------------------------- the rule and the rows

    def test_a_link_is_part_of_the_lower_numbered_switchs_os_block_by_rule(self):
        parts = self.layer().parts
        self.assertEqual(parts["Track 9-11"]["part_of"], "OS Switch 9")
        self.assertIn("the rule", parts["Track 9-11"]["why"])
        self.assertEqual(parts["Track 13-15"]["part_of"], "OS Switch 15")
        self.assertIn("block_overrides.csv line", parts["Track 13-15"]["why"])

    def test_without_its_row_the_rule_gives_the_lower_numbered_switch(self):
        self.assertEqual(self.layer(self.without("1,track,13,15,")).parts["Track 13-15"]["part_of"], "OS Switch 13")
        self.assertEqual(self.layer(self.without("1,track,23,31,")).parts["Track 23-31"]["part_of"], "OS Switch 23b")

    def test_pieces_at_both_ends_part_the_track_with_no_block_of_its_own(self):
        lay = self.layer()
        self.assertEqual({k: v["part_of"] for k, v in lay.parts.items() if k.startswith("Track 1-3")},
                         {"Track 1-3 at 1": "OS Switch 1", "Track 1-3 at 3": "OS Switch 3"})
        self.assertNotIn("Track 1-3", lay.tracks)

    def test_a_piece_marked_inside_stays_in_its_os_block_with_no_block_of_its_own(self):
        """block_overrides.csv's `inside`: the two halves of 35-39 stay inside OS Switch 35b and
        OS Switch 39, with no JMRI or layout block, so Mast 36RB's route to Mast 68 is 3 blocks, not 5; every other
        part follows the rule (a JMRI block of its own)."""
        lay = self.layer()
        self.assertEqual(lay.inside, {"Track 35-39 at 35": "OS Switch 35b", "Track 35-39 at 39": "OS Switch 39"})
        self.assertFalse({"Track 35-39 at 35", "Track 35-39 at 39"} & set(lay.parts))
        self.assertEqual(len(lay.parts), 14)
        bi = next(iter(lay.rows))
        self.assertIn(["OS Switch 35b", "OS Switch 39"], [sorted(v) for v in lay.rows[bi].values()])
        self.assertNotIn("Track 35-39", lay.tracks)

    def test_inside_is_yes_or_empty_and_only_for_a_track_row(self):
        self.stops(HEAD + "1,track,9,11,,,os:9,,no,\n", "inside is yes or empty")
        self.stops(HEAD + "1,crossover_half,7,13,1,,os:7:A-13C,,yes,\n", "with no end, cm or inside")

    def test_a_piece_at_one_end_leaves_the_rest_its_own_block(self):
        lay = self.layer(self.committed + SCALE_AT_7)
        self.assertEqual(lay.parts["Track Scale at 7"]["part_of"], "OS Switch 7a")  # generated; the field name wins
        self.assertIn("Track Scale", lay.tracks)

    def test_os_switch_7_ends_at_the_switch(self):
        # Track Scale is one block, none of it inside OS Switch 7
        lay = self.layer()
        self.assertNotIn("Track Scale at 7", lay.parts)
        scale = next(t for t, _h in lay.tracks.values() if t["name"] == "Track Scale")
        self.assertEqual(lay.cm["Track Scale"], scale["cm"])

    def test_a_crossover_without_rows_is_one_os_block(self):
        lay = self.layer(self.without("1,crossover_half,7,"))
        bi = next(iter(lay.bands))
        os_ = {b for n, b in lay.bands[bi]["os"].items() if self.bands[bi][1]["nodes"][n]["label"] == "7"}
        self.assertEqual(os_, {"OS Switch 7"})

    def test_every_level_folds_its_links(self):
        self.assertFalse(hasattr(BL, "FOLD_LINKS"))      # one rule for every level
        lay = self.main_upper()
        self.assertEqual({k: v["part_of"] for k, v in lay.parts.items()}, MAIN_UPPER_LINKS)
        for name in MAIN_UPPER_LINKS:
            self.assertNotIn(name, lay.tracks)
        self.assertIn("Track 127-131 1", lay.tracks)    # 73.6 cm: over LINK_CM, a block of its own

    def test_a_mast_at_a_links_end_puts_the_boundary_at_the_mast(self):
        ends = {"125": "OS Switch 125", "129": "OS Switch 129"}
        t = {"name": "Track 125-129"}
        bad = []
        self.assertEqual(BL.masted_block(t, ends, {}, 2, "x.csv", bad)[0], "OS Switch 125")
        block, why = BL.masted_block(t, ends, {"125": "126RB"}, 2, "x.csv", bad)
        self.assertEqual(block, "OS Switch 129")
        self.assertIn("Mast 126RB", why)
        self.assertEqual(BL.masted_block(t, ends, {"129": "130L"}, 2, "x.csv", bad)[0], "OS Switch 125")
        self.assertEqual(bad, [])

    def test_a_link_with_a_mast_facing_it_at_both_ends_stops(self):
        bad = []
        got = BL.masted_block({"name": "Track 125-129"}, {"125": "OS Switch 125", "129": "OS Switch 129"},
                              {"125": "126RB", "129": "130L"}, 2, "x.csv", bad)
        self.assertEqual(got, (None, None))
        self.assertEqual(len(bad), 1)
        self.assertIn("Mast 126RB at Switch 125, Mast 130L at Switch 129", bad[0])
        # and through the layer: a mast placed at Switch 129's points facing 125-129 too
        lay = self.main_upper()
        self.posts = dict(self.last_posts)
        t = next(t for t in self.mu_found if t["name"] == "Track 125-129")
        far = next((n, p) for (n, p), (k, v) in zip(t["legs"], t["ends"]) if v == "129")
        self.posts[(t["band"], *far)] = "130X"
        try:
            with self.assertRaisesRegex(BL.BlockError, "Track 125-129 has a home mast facing it at both ends "
                                                       r"\(Mast 126RB at Switch 125, Mast 130X at Switch 129\)"):
                self.main_upper()
        finally:
            self.posts = None
        self.assertIn("Track 125-129", lay.parts)

    def test_a_link_drawn_to_a_connector_takes_the_os_block_at_its_end_on_the_band(self):
        # {end switch: its OS block on the link's band, None for a switch across a connector}
        self.assertEqual(BL.link_block({"121": None, "127": "OS Switch 127"}), "OS Switch 127")
        self.assertEqual(BL.link_block({"121": "OS Switch 121", "127": "OS Switch 127"}), "OS Switch 121")
        self.assertIsNone(BL.link_block({"121": None, "127": None}))

    # ---------------------------------------------------------------- the stops

    def test_columns_kinds_and_shapes(self):
        self.stops("level,switch_a\n", "columns")
        self.stops(HEAD + "1,spur,9,11,,,OS Switch 9,,,\n", "kind one of split, track, crossover_half")
        self.stops(HEAD + "4,track,9,11,,,OS Switch 9,,,\n", "level is 1, 2 or 3")
        self.stops(HEAD + "1,track,9,11,,,Track Barn,,,\n", "is no OS block")
        self.stops(HEAD + "1,track,11,9,,,os:9,,,\n", "lower first")
        self.stops(HEAD + "1,track,9,11,,13,os:9,,,\n", "its end empty or one of them")
        self.stops(HEAD + "1,crossover_half,7,13,1,7,os:7:A-13C,,,\n", "with no end, cm or inside")
        self.stops(HEAD + "1,crossover_half,7,13,,,os:7:A-13C,,,\n", r"parallel 1 or 2 \(its letter a or b\)")
        self.stops(HEAD + "1,crossover_half,7,13,1,,OS Switch 7,,,\n", "is no crossover half's OS block ID")
        self.stops(HEAD + "1,crossover_half,7,13,1,,os:7:A-5B,,,\n", "as its block ID has them")

    def test_a_row_that_matches_no_track_or_half_stops(self):
        self.stops(self.committed + "1,track,2,4,,,os:2,,,\n", "no track runs Switch 2 to Switch 4")
        self.stops(self.without("1,crossover_half,7,13,") + "1,crossover_half,7,9,1,,os:7:A-9B,,,\n",
                   "no crossover half of Switch 7 has its leg A track running to Switch 9")

    def test_a_track_rows_block_is_an_os_block_id(self):
        """A track row gives its OS block's device ID (os:<n>, a crossover half's
        os:<n>:A-<end>), which comes back as the generated name; a name, or a half no crossover_half row has, stops."""
        rows = BL.block_override_rows.read_block_overrides(bdm.block_overrides(), ("track",))
        got = {(r["switch_a"], r["switch_b"], r["end"]): (r["id"], r["block"]) for r in rows if r["level"] == "1"}
        self.assertEqual(got[("13", "15", "")], ("os:15", "OS Switch 15"))
        self.assertEqual(got[("35", "37", "")], ("os:35:A-33A", "OS Switch 35a"))
        self.stops(self.without("1,track,13,15,") + "1,track,13,15,,,OS Switch 15,,,\n", "is no OS block ID")
        self.stops(self.committed + "1,track,9,11,,,os:9:A-99A,,,\n",
                   "no crossover_half row of Switch 9 whose leg A runs to Switch 99")

    def test_a_row_given_twice_stops(self):
        self.stops(self.committed + "1,track,13,15,,,os:15,,,\n", "Track 13-15 is given a block on line")
        self.stops(self.committed + "1,crossover_half,7,13,1,,os:7:A-13C,,,\n", "Switch 7's half a is given on line")
        self.stops(self.without("1,crossover_half,7,5,") + "1,crossover_half,7,13,2,,os:7:A-13C,,,\n",
                   "given its block on line")

    def test_a_block_that_is_not_the_os_block_at_its_end_stops(self):
        self.stops(self.without("1,track,13,15,") + "1,track,13,15,,,os:17,,,\n",
                   "Track 13-15 is given OS Switch 17, the OS block of neither")
        self.stops(self.without("1,track,1,3,,1,") + "1,track,1,3,,1,os:3,,,\n",
                   "the piece of Track 1-3 at Switch 1 is given OS Switch 3, not that switch's OS block OS Switch 1")

    def test_one_crossover_half_alone_stops(self):
        self.stops(self.without("1,crossover_half,7,5,"), "crossover 7: give both halves")

    def test_a_split_track_with_rows_stops(self):
        self.stops(self.committed + "1,track,37,39,,,os:37,,,\n", "split in halves and given to OS blocks")

    def test_a_split_comes_from_the_same_file_as_the_other_rows_on_staging(self):
        """staging_layer reads every kind of block_overrides.csv from the one file it is given: without the Princess
        split, K-1 and K-2 are one track carrying two plan names, which stops."""
        p = temp_file("block_overrides.csv", self.without("1,split,37,39,"))
        try:
            with self.assertRaisesRegex(bdm.MapError, r"Track 37-39 carries plan names \['K-1', 'K-2'\]"):
                bdm.staging_layer(self.bands, self.joined, self.runs, p)
            lay, _bi, _found = bdm.staging_layer(self.bands, self.joined, self.runs, BL.overrides_path())
            self.assertIn("Track K-1", lay.tracks)
        finally:
            remove(p)

    def test_a_split_comes_from_the_same_file_as_the_other_rows_on_main_and_upper(self):
        self.assertIn("Track 227-241 1", self.main_upper().tracks)
        lay = self.main_upper(self.without("3,split,227,241,"))
        self.assertIn("Track 227-241", lay.tracks)
        self.assertNotIn("Track 227-241 1", lay.tracks)

    def test_a_main_or_upper_row_applies_on_its_level(self):
        lay = self.main_upper(self.committed + "2,track,113,115,,,os:115,,,\n")
        self.assertEqual(lay.parts["Track 113-115"]["part_of"], "OS Switch 115")
        self.assertIn("block_overrides.csv line", lay.parts["Track 113-115"]["why"])
        with self.assertRaisesRegex(BL.BlockError, r"\(level 3\): no track runs Switch 113 to Switch 115"):
            self.main_upper(self.committed + "3,track,113,115,,,os:115,,,\n")

    # ---------------------------------------------------------------- lengths

    def test_a_piece_at_one_end_takes_its_length_off_the_rest(self):
        lay = self.layer(self.committed + SCALE_AT_7)
        scale = next(t for t, _h in lay.tracks.values() if t["name"] == "Track Scale")
        self.assertEqual(lay.parts["Track Scale at 7"]["cm"], 23.0)
        self.assertEqual(lay.cm["Track Scale"], round(scale["cm"] - 23.0, 1))

    def test_pieces_at_both_ends_share_the_track_evenly(self):
        lay = self.layer()
        self.assertEqual(lay.parts["Track 1-3 at 1"]["cm"], lay.parts["Track 1-3 at 3"]["cm"])
        self.assertEqual(lay.parts["Track 9-11"]["cm"], 38.7)

    def test_a_piece_at_one_end_needs_its_length(self):
        self.stops(self.committed + SCALE_AT_7.replace(",23,", ",,"), "Track Scale at 7: give its cm")
        self.stops(self.committed + SCALE_AT_7.replace(",23,", ",500,"), "is not under the track's")
        self.stops(self.committed + SCALE_AT_7.replace(",23,", ",x,"), "cm 'x' is a length")
        self.stops(self.without("1,track,13,15,") + "1,track,13,15,,,os:15,10,,\n", "only a piece at one end")

    # ---------------------------------------------------------------- halves

    def renamed(self, names: dict):
        """(bands, found) with the name store's names of staging strands changed ({strand: name}): each strand's
        owner row, by its ID (staging_device_map.band_refs), renamed; the drawing is left as it is."""
        import staging_device_map as sdm
        from hartlib import device_ids, track_names
        bi = next(i for i, (t, _b, _o) in enumerate(self.bands) if self.levels.get(t) == 1)
        refs = sdm.band_refs(self.bands, self.joined, bi)
        owner = track_names.owner_names()
        for sid, name in names.items():
            owner[("1", device_ids.block_id([device_ids.strand_key(refs[sid][0])]))] = name
        over = bdm.layer_files.read("plan_overrides", bdm.STAGING_SHEET, bdm.OVERRIDES.parent)
        return self.bands, bdm.named_tracks(self.bands, self.joined, self.runs, over, owner=owner)

    def test_a_track_is_named_by_its_id_not_by_the_drawing(self):
        """The drawn strand names are not read: a strand renamed on the drawing keeps the store's name, and a rename
        in the store is the block's name."""
        import copy
        bands = copy.deepcopy(self.bands)
        bi = next(i for i, (t, _b, _o) in enumerate(bands) if self.levels.get(t) == 1)
        for s in bands[bi][1]["strands"].values():
            s["name"] = "Drawn"
        over = bdm.layer_files.read("plan_overrides", bdm.STAGING_SHEET, bdm.OVERRIDES.parent)
        names = {t["name"] for t in bdm.named_tracks(bands, self.joined, self.runs, over)}
        self.assertEqual(names, {t["name"] for t in self.found})
        self.assertIn("Track S-1", names)
        _bands, found = self.renamed({"e22": "S-9"})
        self.assertIn("Track S-9", {t["name"] for t in found})
        self.assertNotIn("Track S-1", {t["name"] for t in found})

    def halves_layer(self, names: dict) -> BL.Layer:
        bands, found = self.renamed(names)
        return BL.layer(bands, self.runs, found, self.levels, BL.split_edges(found, self.levels, bdm.block_overrides()),
                        BL.read_exceptions(found, bands, self.levels))

    def test_halves_with_one_plan_name_are_numbered_not_merged(self):
        lay = self.halves_layer({"e15.0": "K", "e15.1": "K"})
        self.assertIn("Track K 1", lay.tracks)
        self.assertIn("Track K 2", lay.tracks)
        self.assertNotIn("Track K", lay.tracks)

    def test_a_half_named_like_another_block_stops(self):
        with self.assertRaisesRegex(BL.BlockError, "Track Barn names two blocks"):
            self.halves_layer({"e15.0": "Barn"})

    def test_a_helix_track_its_plan_name_does_not_name_stops(self):
        with self.assertRaisesRegex(BL.BlockError, "which is not a helix track of plan_overrides.json"):
            BL.name_tracks([dict(t) for t in self.found], {})

    def test_a_track_cut_by_the_level_split_is_one_block_by_the_ordinary_rule(self):
        """A helix track arrives as two pieces, staging's and main or upper's, cut at the level split; both carry its
        one plan name, so the ordinary rule names them one block, "Track <plan name>"."""
        found = bdm.named_tracks(self.bands, self.joined, self.runs)
        by_name = {}
        for t in self.found + found:
            if any(k == "helix" for k, _v in t["ends"]):
                by_name.setdefault(t["name"], set()).add(t["level"])
        self.assertEqual(by_name, {"Track Helix Outer": {1, 2}, "Track Helix Inner": {1, 3}})

    def test_a_track_with_two_plan_names_must_be_split(self):
        with self.assertRaisesRegex(BL.BlockError, r"Track 37-39 carries plan names \['K-1', 'K-2'\] but is one "
                                                   "block"):
            BL.layer(self.bands, self.runs, self.found, self.levels, {},
                     BL.read_exceptions(self.found, self.bands, self.levels))


class Drawings(RepoReadOnly, unittest.TestCase):
    """A band's drawing (the plan input its edge ids belong to) is the plan-overrides section that holds its level,
    not a level number written in the code."""

    def test_each_level_is_on_the_section_that_holds_it(self):
        self.assertEqual(BL.drawings(), {1: "staging", 2: "main_upper", 3: "main_upper"})

    def test_a_level_no_section_holds_stops(self):
        with self.assertRaisesRegex(BL.BlockError, "no band level 4"):
            BL.drawing(4)

    def test_a_level_in_two_sections_stops(self):
        whole = bdm.layer_files.read_file("plan_overrides", bdm.OVERRIDES.parent)
        whole["more"] = {"level_title": "Another main", "level": 2}
        folder = Path(tempfile.mkdtemp())
        p = folder / "plan_overrides.json"
        p.write_text(bdm.layer_files.dumps(whole), encoding="utf-8")
        try:
            with self.assertRaisesRegex(BL.BlockError, "level 2 is in sections main_upper and more"):
                BL.drawings(folder)
        finally:
            remove(p)

    def test_an_unreadable_file_is_a_block_error(self):
        folder = Path(tempfile.mkdtemp())
        try:
            with self.assertRaises(BL.BlockError):
                BL.drawings(folder)
            with self.assertRaisesRegex(BL.BlockError, "plan_overrides"):    # the store's lookup too
                BL.store_names([], [], {}, {}, folder)
        finally:
            os.rmdir(folder)

    def test_a_missing_level_names_its_band(self):
        with self.assertRaisesRegex(BL.BlockError, "level 4 \\(band 'Attic'\\)"):
            BL.drawing(4, title="Attic")

    def test_the_drawing_follows_the_section_not_the_level_number(self):
        with unittest.mock.patch.object(BL, "drawings", return_value={1: "a", 2: "b", 3: "b"}):
            self.assertEqual(BL.drawing(1), "a")
            self.assertEqual(BL.drawing(3), "b")


class TheCommand(RepoReadOnly, unittest.TestCase):
    """A data error from staging's rows ends main() with its one-line message and exit 2, as the others do."""

    def test_data_errors_exit_2(self):
        import contextlib
        import io
        import staging_device_map as sdm
        try:
            bdm.solve()
        except Exception as exc:  # noqa: BLE001  no plugin: nothing to run
            raise unittest.SkipTest(str(exc))
        for exc in (sdm.StagingMapError("staging: bad"), bdm.railroad.FactsError("facts: bad")):
            with self.subTest(exc=type(exc).__name__), \
                    unittest.mock.patch.object(bdm, "staging_rows", side_effect=exc), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(bdm.main(["--check"]), 2)
            self.assertIn("bad", err.getvalue())


class StagingRows(RepoReadOnly, unittest.TestCase):
    """build_device_map.staging_rows over a copy of the two files: the owner's cells come from devices_field.csv, the
    rest is the builder's, and a block with no field row, or a field row with no block, stops."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import build_layout_le as bl
        try:
            cls.bands, cls.joined, runs, _corners = bdm.solve()
        except bl.BuildError as exc:
            raise unittest.SkipTest(str(exc))
        cls.runs = staticmethod(runs)

    def pair(self, edit=None) -> devices.Files:
        """A copy of the master's two files in a temporary folder, its field file's rows `edit`ed (the owner's hand:
        written as text, unchecked, as a hand edit would be)."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(os.rmdir, d)            # runs last: cleanups run in reverse
        files = devices.pair_copy(d)
        for p in (files.master, files.field, files.dictionary):
            self.addCleanup(os.remove, p)       # by full path (rmtree's relative unlinks look like repo writes)
        if edit:
            rows = edit([dict(r) for r in devices.field_rows(files)])
            files.field.write_text(devices.master_text(rows), encoding="utf-8")
        return files

    def rows(self, edit=None, extra_exception="", pins=None, places=None, files=None):
        """staging_rows over a copy of the two files (the field file `edit`ed), of block_overrides.csv (plus
        `extra_exception`) and of wiring.csv (`pins`: a function of its text)."""
        self.files = files or self.pair(edit)
        ex = temp_file("block_overrides.csv", BL.overrides_path().read_text(encoding="utf-8") + extra_exception)
        self.addCleanup(remove, ex)
        text = bdm.WIRING.read_text(encoding="utf-8")
        pf = temp_file("wiring.csv", pins(text) if pins else text)
        self.addCleanup(remove, pf)
        return bdm.staging_rows(self.bands, self.joined, self.runs, self.files, exceptions=ex, pins=pf, places=places)

    @staticmethod
    def by(got):
        return {(r["layer"], r["user_name"]): r for r in got}

    @staticmethod
    def field(rows, name):
        return next(r for r in rows if r["level"] == "1" and r["user_name"] == name)

    def test_the_wiring_comes_from_the_pins(self):
        """Track Barn and Track EH-1 swap inputs in wiring.csv: both detectors' node, sensor and wiring, and both
        blocks' node and comment, follow; nothing else changes, and no hand file is edited."""
        def swap(text):
            return (text.replace("1,detector,det:block:7A-13C,,,,,,13,1,,,wired,", "1,detector,det:block:7A-13C,,,,,,13,7,,,wired,")
                        .replace("1,detector,det:block:11B-end,,,,,,13,7,,,wired,", "1,detector,det:block:11B-end,,,,,,13,1,,,wired,"))
        got = self.by(self.rows(pins=swap))
        want = self.by(self.rows())
        occ, blk = got[("occupancy", "BS Barn")], got[("block", "Track Barn")]
        self.assertEqual((occ["system_name"], occ["jmri_name"], occ["wiring"]),
                         ("M2S1306", "M2S1306", "Node: 13 Block: 7"))
        self.assertEqual(blk["node"], "13")
        self.assertEqual(blk["jmri_comment"], "Lead Switch 7 to Switch 13; occupancy Block 13-7 / M2S1306")
        self.assertEqual(got[("occupancy", "BS EH-1")]["system_name"], "M2S1300")
        changed = {k for k in want if got[k] != want[k]}
        self.assertEqual(changed, {("occupancy", "BS Barn"), ("block", "Track Barn"),
                                   ("occupancy", "BS EH-1"), ("block", "Track EH-1")})
        self.assertEqual(self.field(devices.field_rows(self.files), "Track Barn")["jmri_comment"],
                         "Lead Switch 7 to Switch 13; {occupancy}")      # the owner's words, as they were

    def test_a_parts_cells_follow_its_rewired_block(self):
        """OS Switch 9 and OS Switch 11 swap inputs in wiring.csv: their parts (Track 9-11 and Track 11-13) take the
        rewired block's detector (the occupancy part of its comment) on the same build."""
        def swap(text):
            return (text.replace("1,detector,det:os:9,,,,,,13,8,", "1,detector,det:os:9,,,,,,13,2,")
                        .replace("1,detector,det:os:11,,,,,,13,2,", "1,detector,det:os:11,,,,,,13,8,"))
        got, want = self.by(self.rows(pins=swap)), self.by(self.rows())
        for part, block in (("Track 9-11", "OS Switch 9"), ("Track 11-13", "OS Switch 11")):
            p, b = got[("block", part)], got[("block", block)]
            self.assertNotEqual(b["jmri_comment"], want[("block", block)]["jmri_comment"])
            self.assertEqual(re.search("occupancy .*$", p["jmri_comment"]).group(0),
                             re.search("occupancy .*$", b["jmri_comment"]).group(0), part)

    def test_a_line_blocks_cp_is_the_rule_not_the_owners(self):
        """A line block's cp (and its sensor's, its block's) lists the stations of the switches at its ends, plus a
        station whose tracks name it: written by the rule on every build, so a cp in its field
        row does not stand (and the write would refuse to override it: devices.unmerge)."""
        def edit(rows):
            for r in rows:
                if r["level"] == "1" and r["user_name"] in ("Track Barn", "BS Barn"):
                    r["cp"] = "Plane"
            return rows
        by = self.by(self.rows(edit))
        self.assertEqual((by[("block", "Track Barn")]["cp"], by[("occupancy", "BS Barn")]["cp"]),
                         ("Barn;Engine House", "Barn;Engine House"))
        self.assertEqual(by[("block", "Track 9-11")]["cp"], "Barn;Engine House")      # a part: its own ends
        self.assertEqual(by[("block", "Track East Ext")]["cp"], "Plane;Barn")
        self.assertEqual(by[("block", "Track W-1")]["cp"], "Brick;West Yard")
        self.assertEqual(by[("block", "OS Switch 1")]["cp"], "Brick")                  # an OS block keeps the owner's

    def test_a_station_that_lists_a_track_adds_itself(self):
        places = bdm.read_places()
        more = places._replace(tracks={**places.tracks, "Track Barn": ["Princess"]})
        self.assertEqual(self.by(self.rows(places=more))[("block", "Track Barn")]["cp"],
                         "Barn;Engine House;Princess")
        with self.assertRaisesRegex(bdm.MapError, "Princess lists Nowhere in its tracks, which is no staging block"):
            self.rows(places=places._replace(tracks={"Track Nowhere": ["Princess"]}))

    def test_wiring_cells_in_the_field_file_are_overwritten_by_the_pins(self):
        stale = {"BS Barn": dict(node="4", system_name="M2S498", jmri_name="M2S498"),
                 "Track Barn": dict(node="4")}

        def edit(rows):
            for r in rows:
                if r["level"] == "1" and r["user_name"] in stale:
                    r.update(stale[r["user_name"]])
            return rows
        self.assertEqual(self.rows(edit), self.rows())

    def test_pins_that_do_not_fit_stop(self):
        for pins, msg in (
                (lambda t: t.replace("1,detector,det:block:7A-13C,,,,,,13,1,,,wired,\n", ""),
                 "staging block Track Barn: its detector BS Barn has no level 1 row"),
                # wiring.csv keys a pin by its block's id: an id staging draws no block for, and one the master lacks
                (lambda t: t + "1,detector,det:mast:5:B:west,,,,,,5,1,,,wired,\n",
                 r"staging has no block Mast 6LB \(mast:5:B:west\)"),
                (lambda t: t + "1,detector,det:block:99Z-end,,,,,,5,1,,,wired,\n",
                 "block:99Z-end is no level 1 device of the device master"),
                (lambda t: t.replace("1,detector,det:block:7A-13C,,,,,,13,1,,,wired,", "1,detector,det:block:37B-helix,,,,,,13,1,,,wired,"),
                 "Track Helix Inner is a helix block"),
                (lambda t: t.replace("2,detector,det:block:131AA-helix,,,,,,41,2,,,planned,", "2,detector,det:block:131AA-helix,,,,,,41,x,,,planned,"),
                 "node, index and ports are numbers")):
            with self.subTest(msg=msg), self.assertRaisesRegex(bdm.MapError, msg):
                self.rows(pins=pins)

    def test_a_block_swapped_onto_a_spare_input_moves_the_spare(self):
        """Track Barn moves to the spare input 2-2 in wiring.csv alone: BS Barn follows, 13-1 becomes a new
        spare row and the old spare row of 2-2 goes: a spare is wiring.csv's alone, so nothing stops."""
        got = self.rows(pins=lambda t: t.replace("1,detector,det:block:7A-13C,,,,,,13,1,,,wired,", "1,detector,,,,,,,13,1,,,wired,")
                        .replace("1,detector,,,,,,,2,2,,,wired,", "1,detector,det:block:7A-13C,,,,,,2,2,,,wired,"))
        by = self.by(got)
        self.assertEqual(by[("occupancy", "BS Barn")]["system_name"], "M2S201")
        spare = by[("occupancy", "unused Block 13-1")]
        self.assertEqual((spare["role"], spare["system_name"], spare["wiring"], spare["cp"]),
                         ("spare", "M2S1300", "Node: 13 Block: 1", ""))
        self.assertNotIn(("occupancy", "unused Block 2-2"), by)

    def test_a_block_that_becomes_a_part_stops_until_its_field_rows_go(self):
        """East Lead given to OS Switch 33: its field rows (the owner's names and comment) would be lost, so the build
        stops and names them. Once the owner removes them, its block row is a part, its detector's input a spare, and
        the part, a JMRI block of its own, takes its OS block's control point and detector; the next build over that
        output gives the same rows."""
        extra = "1,track,33,35,,,os:33,,,\n"
        with self.assertRaisesRegex(bdm.MapError, r"staging block Track East Lead is now part of OS Switch 33 .* still "
                                                  r"has its block row Track East Lead and occupancy row BS East Lead: "
                                                  r"remove them"):
            self.rows(extra_exception=extra)
        gone = ("Track East Lead", "BS East Lead")
        files = self.pair(lambda rows: [r for r in rows if r["user_name"] not in gone])
        got = self.rows(extra_exception=extra, files=files)
        by = self.by(got)
        part = by[("block", "Track East Lead")]
        self.assertEqual((part["role"], part["part_of"], part["assignment"]), ("part", "OS Switch 33", "virtual"))
        self.assertEqual(part["cp"], "East End;Princess")                  # its ends, Switches 33 and 35
        # a JMRI block of its own under new names, the next free number: not the old block's
        self.assertRegex(part["jmri_name"] + " " + part["layout_block"], r"^IB:AUTO:00(\d\d) ILB\1$")
        self.assertNotIn(("occupancy", "BS East Lead"), by)
        spare = by[("occupancy", "unused Block 1-7")]
        self.assertEqual((spare["role"], spare["assignment"], spare["system_name"], spare["blocks"]),
                         ("spare", "spare", "M2S106", ""))
        # the master takes it and reads it back as written, and the next build over it gives the same rows
        wired = bdm.staging_wired_rows(files)
        # staging's masts and heads are the builder's too: kept as they are here
        field = devices.field_index(files)          # the owner's cells over them (the merged view is broken here)
        masts = [{**r, **{c: v for c, v in field.get(devices.key_of(r), {}).items() if c in devices.FIELD_COLUMNS and v}}
                 for r in devices.generated_rows(files) if r["level"] == "1" and r["layer"] in ("mast", "head")
                 and r["written_by"] == "build_device_map.py"]
        out = devices.outputs_after("build_device_map.py", [], files, master_rows=got + wired + masts,
                                    warn=lambda line: None)     # main and upper's rows are left out: gone
        self.assertIn("unused Block 1-7", out[files.master])
        devices.write_all(files, out)
        self.assertEqual(self.rows(extra_exception=extra, files=files), got)

    def test_a_block_comment_with_no_occupancy_mark_stops(self):
        def edit(rows):
            self.field(rows, "Track Barn")["jmri_comment"] = "Lead Switch 7 to Switch 13; stop"
            return rows
        with self.assertRaisesRegex(bdm.MapError, r"Track Barn: its jmri_comment .* has no \{occupancy\} for its "
                                                  r"detector's \"occupancy Block 13-1"):
            self.rows(edit)

    def test_an_owner_rename_is_kept_by_the_rows_id(self):
        """The field file is keyed by id, so a user name the owner changes there renames the
        block (OS Switch 9, id os:9); its part (Track 9-11) and its detector's blocks cell follow, and its beans and
        wiring stay."""
        def edit(rows):
            next(r for r in rows if r["id"] == "os:9")["user_name"] = "OS Engine House West"
            return rows
        got, want = self.by(self.rows(edit)), self.by(self.rows())
        new, old = got[("block", "OS Engine House West")], want[("block", "OS Switch 9")]
        self.assertEqual({c: new[c] for c in new if new[c] != old[c]},
                         {"user_name": "OS Engine House West",
                          "description": "Block OS Engine House West: the track through the points of its switch."})
        self.assertNotIn(("block", "OS Switch 9"), got)
        self.assertEqual(got[("block", "Track 9-11")]["part_of"], "OS Engine House West")
        self.assertEqual(got[("occupancy", "BS Switch 9")]["blocks"], "OS Engine House West")

    def test_a_field_row_whose_id_is_gone_stops_naming_the_row(self):
        """Decision 3: a field row whose id the plan no longer gives names no row; the build stops and lists it
        (the drawn block with no field row of its id is generated)."""
        def edit(rows):
            next(r for r in rows if r["id"] == "os:9")["id"] = "os:99"
            return rows
        with self.assertRaises(bdm.MapError) as cm:
            self.rows(edit)
        self.assertEqual(str(cm.exception), f"staging rows of {devices.FIELD_FILE} the drawing has no block for: "
                                            "block OS Switch 9 (id os:99)")

    def test_the_committed_rows_come_back_as_they_are(self):
        got = self.rows()
        want = [r.cells() for r in devices.load() if r.level == 1 and r.layer in ("block", "occupancy")]
        self.assertEqual(got, want)

    def test_a_block_with_no_field_rows_is_generated(self):
        """Track Barn's block and detector rows taken out of the field file are generated, as
        main and upper's are, instead of stopping; only the owner's cells they had change."""
        drop = lambda rows: [r for r in rows if not (r["level"] == "1" and r["id"].endswith("block:7A-13C"))]  # noqa
        got, want = self.by(self.rows(drop)), self.by(self.rows())
        new, old = got[("block", "Track Barn")], want[("block", "Track Barn")]
        # its layout block may come back as it was: the next free number can be the one the owner's row held
        self.assertEqual({c for c in new if new[c] != old[c]} - {"layout_block"},
                         {"assignment", "system_name", "jmri_name", "jmri_comment", "cats_discipline"})
        self.assertEqual((new["assignment"], new["system_name"], new["jmri_comment"]),
                         ("virtual", "", "Track Barn; occupancy Block 13-1 / M2S1300"))
        self.assertRegex(new["jmri_name"] + " " + new["layout_block"], r"^IB:AUTO:00(\d\d) ILB\1$")
        self.assertEqual(got[("occupancy", "BS Barn")], want[("occupancy", "BS Barn")])

    def test_a_block_whose_field_row_gives_no_bean_names_is_numbered(self):
        """A field row with the owner's name and words but no bean names (jmri_name,
        layout_block) gets the builder's numbers; a row with one of the two stops."""
        def edit(rows):
            r = self.field(rows, "Track Barn")
            r.update(user_name="Track Barn Lead", system_name="", jmri_name="", layout_block="", assignment="")
            return rows
        files = self.pair(edit)
        got = self.by(self.rows(files=files))[("block", "Track Barn Lead")]
        self.assertEqual(got["assignment"], "virtual")
        self.assertRegex(got["jmri_name"] + " " + got["layout_block"], r"^IB:AUTO:00(\d\d) ILB\1$")
        self.assertTrue(got["jmri_comment"].startswith("Lead Switch 7 to Switch 13; occupancy Block 13-1"))

        def half(rows):
            self.field(rows, "Track Barn")["layout_block"] = ""
            return rows
        with self.assertRaisesRegex(bdm.MapError, r"Track Barn \(id block:7A-13C\): it gives jmri_name but not "
                                                  "layout_block"):
            self.rows(half)

    def test_a_field_row_the_drawing_has_no_block_for_stops(self):
        def add(rows):
            extra = dict(self.field(rows, "Track Barn"), user_name="Track Nowhere", system_name="IB:AUTO:9999",
                         jmri_name="IB:AUTO:9999", layout_block="ILB999", id="test:nowhere")
            at = next(i for i, r in enumerate(rows) if r["level"] == "1" and r["layer"] == "block")
            return rows[:at] + [extra] + rows[at:]
        with self.assertRaisesRegex(bdm.MapError, "the drawing has no block for: block Track Nowhere"):
            self.rows(add)

    def test_a_spare_in_the_field_file_stops(self):
        """A spare detector is wiring.csv's: a field row for one is refused, naming it."""
        def add(rows):
            occ = next(i for i, r in enumerate(rows) if r["level"] == "1" and r["layer"] == "occupancy")
            spare = dict.fromkeys(devices.COLUMNS, "")
            spare.update(level="1", layer="occupancy", user_name="unused Block 2-2", role="spare", assignment="spare",
                         id="spare:M2S201")
            return rows[:occ] + [spare] + rows[occ:]
        with self.assertRaisesRegex(bdm.MapError, "occupancy unused Block 2-2 is a spare input .* remove the field "
                                                  "row"):
            self.rows(add)

    def test_a_spare_in_the_field_file_with_no_name_is_found_by_its_id(self):
        """A field row's user name may be empty (the generated one stands), so a spare's
        field row is found by its id too: one error for it, not a second "no block for" one."""
        def add(rows):
            occ = next(i for i, r in enumerate(rows) if r["level"] == "1" and r["layer"] == "occupancy")
            spare = dict.fromkeys(devices.COLUMNS, "")
            spare.update(level="1", layer="occupancy", role="spare", assignment="spare", id="spare:M2S201")
            return rows[:occ] + [spare] + rows[occ:]
        with self.assertRaises(bdm.MapError) as cm:
            self.rows(add)
        self.assertIn("occupancy unused Block 2-2 is a spare input", str(cm.exception))
        self.assertNotIn("the drawing has no block for", str(cm.exception))


class StagingWiredRows(RepoReadOnly, unittest.TestCase):
    """build_device_map.staging_wired_rows: staging's turnout, LCC alias and feedback rows take their wiring cells
    from wiring.csv."""

    def rows(self, edit=None):
        text = bdm.WIRING.read_text(encoding="utf-8")
        p = temp_file("wiring.csv", edit(text) if edit else text)
        self.addCleanup(remove, p)
        return bdm.staging_wired_rows(path=p)

    def test_the_committed_rows_come_back_as_they_are(self):
        got = self.rows()
        want = [r.cells() for r in devices.load() if r.level == 1 and r.layer in ("turnout", "fb")]
        self.assertEqual(got, want)
        self.assertEqual(len(got), 80)

    def test_the_wiring_comes_from_wiring_csv(self):
        """Switches 1 and 3 swap their LCOS numbers and ports: both turnouts and their aliases follow; the alias keeps
        its MTT name and Switch 23 keeps the JMRI name the panel binds ("Switch 23")."""
        def swap(t):
            return (t.replace('1,turnout,switch:1,,,,,,4,0,OU1,"1,2"', "1,turnout,switch:1,,,,,,4,9,OU1,X")
                     .replace('1,turnout,switch:3,,,,,,4,1,OU1,"3,4"', '1,turnout,switch:3,,,,,,4,0,OU1,"1,2"')
                     .replace("1,turnout,switch:1,,,,,,4,9,OU1,X", '1,turnout,switch:1,,,,,,4,1,OU1,"3,4"'))
        by = {r["user_name"]: r for r in self.rows(swap)}
        self.assertEqual((by["Switch 1"]["system_name"], by["Switch 1"]["jmri_name"], by["Switch 1"]["wiring"]),
                         ("M2T409", "M2T409", "Node: 4 Turnout: 1 | OU: 1 Ports: 3,4"))
        self.assertEqual((by["DCC Switch 1"]["system_name"], by["DCC Switch 1"]["wiring"]),
                         ("MTT100", "Node: 4 Turnout: 1 | OU: 1 Ports: 3,4"))
        self.assertEqual(by["Switch 3"]["system_name"], "M2T408")
        self.assertEqual(by["Switch 23"]["jmri_name"], "Switch 23")
        self.assertEqual(by["DCC Switch 1"]["dcc"], "100")              # the alias keeps its address
        self.assertEqual(by["DCC Switch 1"]["notes"], "LCC alias of Switch 1 (M2T409)")    # and names its turnout's
        self.assertEqual(by["DCC Switch 3"]["notes"], "LCC alias of Switch 3 (M2T408)")

    def test_the_description_names_the_new_node(self):
        got = {r["user_name"]: r for r in self.rows(lambda t: t.replace('1,turnout,switch:13,,,,,,4,3,OU1,"7,8"',
                                                                        '1,turnout,switch:13,,,,,,13,5,OU3,"1,2"'))}
        self.assertEqual(got["Switch 13"]["system_name"], "M2T1313")
        self.assertIn("LCOS node 13", got["Switch 13"]["description"])

    def test_a_turnout_renamed_by_the_owner_keeps_its_wiring(self):
        """A staging turnout renamed in its field row (id switch:1) keeps its wiring.csv row,
        which knows it by its id."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(os.rmdir, d)
        files = devices.pair_copy(d)
        for p in (files.master, files.field, files.dictionary):
            self.addCleanup(os.remove, p)
        rows = [dict(r) for r in devices.field_rows(files)]
        next(r for r in rows if r["id"] == "switch:1")["user_name"] = "Switch Brick West"
        files.field.write_text(devices.master_text(rows), encoding="utf-8")
        got = {r["id"]: r for r in bdm.staging_wired_rows(files)}
        want = {r["id"]: r for r in self.rows()}
        self.assertEqual(got["switch:1"]["user_name"], "Switch Brick West")
        self.assertEqual({c for c in got["switch:1"] if got["switch:1"][c] != want["switch:1"][c]},
                         {"user_name", "description"})

    def field_copy(self, edit) -> devices.Files:
        """A copy of the master's two files with its field rows `edit`ed ({id: {column: value}})."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(os.rmdir, d)
        files = devices.pair_copy(d)
        for p in (files.master, files.field, files.dictionary):
            self.addCleanup(os.remove, p)
        rows = [dict(r) for r in devices.field_rows(files)]
        for r in rows:
            r.update(edit.get(r["id"], {}))
        files.field.write_text(devices.master_text(rows), encoding="utf-8")
        return files

    def test_an_alias_note_names_its_turnout_as_readers_see_it(self):
        """The alias's note follows its turnout's owner name, by the switch number."""
        got = {r["id"]: r for r in bdm.staging_wired_rows(self.field_copy({"switch:1": {"user_name": "Switch Brick"}}))}
        self.assertEqual(got["dcc:1"]["notes"], "LCC alias of Switch Brick (M2T408)")

    def test_a_turnout_bound_by_its_name_is_renamed_with_its_binding(self):
        """Switch 23's panels bind it by its user name (its field
        jmri_name), so a rename of the user name alone stops, naming both cells; both together pass."""
        with self.assertRaisesRegex(bdm.MapError, r"staging turnout Switch East \(id switch:23\): its jmri_name "
                                                  r"'Switch 23' binds it by its old user name; change jmri_name and "
                                                  r"user_name together"):
            bdm.staging_wired_rows(self.field_copy({"switch:23": {"user_name": "Switch East"}}))
        got = {r["id"]: r for r in bdm.staging_wired_rows(
            self.field_copy({"switch:23": {"user_name": "Switch East", "jmri_name": "Switch East"}}))}
        self.assertEqual((got["switch:23"]["user_name"], got["switch:23"]["jmri_name"]), ("Switch East", "Switch East"))

    def test_a_feedback_bound_by_its_old_name_stops(self):
        """The binding check holds a feedback row too, after the owner's values go over it."""
        with self.assertRaisesRegex(bdm.MapError, r"staging fb FB Switch 1 N \(id fb:1:N\): its jmri_name 'FB Old' "
                                                  r"binds it by its old user name"):
            bdm.staging_wired_rows(self.field_copy({"fb:1:N": {"jmri_name": "FB Old"}}))

    def test_an_alias_with_no_dcc_address_stops(self):
        """An alias field row whose switch has no DCC address anywhere stops (it would be a
        broken alias, system name MTT)."""
        with self.assertRaisesRegex(bdm.MapError, r"\(id dcc:1\): an LCC alias needs a DCC address"):
            bdm.staging_wired_rows(self.field_copy({"dcc:1": {"dcc": "", "system_name": "", "jmri_name": ""},
                                                    "switch:1": {"dcc": ""}}))

    def test_rows_that_do_not_match_stop(self):
        for edit, msg in ((lambda t: t.replace('1,turnout,switch:1,,,,,,4,0,OU1,"1,2",wired,\n', ""),
                           "staging turnout Switch 1: no turnout row for switch:1 in wiring.csv"),
                          # wiring.csv keys a turnout by its id: one the device master lacks is refused as it is read
                          (lambda t: t + '1,turnout,switch:999,,,,,,5,0,OU1,"1,2",wired,\n',
                           "switch:999 is no level 1 device of the device master"),
                          (lambda t: t.replace('1,turnout,switch:13,,,,,,4,3,', '1,turnout,switch:13,,,,,,41,3,'),
                           "turnout Switch 13 is on node 41, no staging node")):
            with self.subTest(msg=msg), self.assertRaisesRegex(bdm.MapError, msg):
                self.rows(edit)


class StagingPins(unittest.TestCase):
    """read_staging_pins: staging's detectors as wired, the level 1 rows of wiring.csv."""
    HEAD = ",".join(bdm.wiring.COLUMNS) + "\n"

    def read(self, text):
        p = temp_file("wiring.csv", self.HEAD + text)
        self.addCleanup(remove, p)
        return bdm.read_staging_pins(p, {1, 2, 13})

    def test_read(self):
        got = self.read("1,detector,det:block:7A-13C,,,,,,13,1,,,wired,\n1,detector,,,,,,,2,2,,,wired,spare\n"
                        "3,detector,det:block:131BB-helix,,,,,,41,1,,,planned,\n")
        self.assertEqual([(p.block, p.id, p.sensor, p.wiring, p.input) for p in got],
                         [("Track Barn", "block:7A-13C", "M2S1300", "Node: 13 Block: 1", "Block 13-1"),
                          ("", "", "M2S201", "Node: 2 Block: 2", "Block 2-2")])
        self.assertEqual(len(bdm.read_staging_pins()), 45)                       # the committed file: 43 and 2 spares

    def test_bad_rows_stop(self):
        barn, eh1 = "1,detector,det:block:7A-13C,", "1,detector,det:block:11B-end,"
        for text, msg in ((barn + ",7,13,,,13,1,,,wired,\n", "named by its block's id alone"),
                          (barn + ",,,,,41,1,,,wired,\n", "node 41 is no staging node"),
                          (barn + ",,,,,13,9,,,wired,\n", "a detector's index is 1 to 8, not 9"),
                          (barn + ",,,,,13,x,,,wired,\n", "node, index and ports are numbers"),
                          (barn + ",,,,,13,1,,,wired,\n" + eh1 + ",,,,,13,1,,,wired,\n", "node 13 Block 1 is line 2's as well"),
                          (barn + ",,,,,13,1,,,wired,\n" + barn + ",,,,,13,2,,,wired,\n",
                           "det:block:7A-13C is line 2's as well"),
                          ("1,detector,,Track Barn,,,,,13,1,,,wired,\n", "a detector is named by its id, not device"),
                          ("1,detector,block:7A-13C,,,,,,13,1,,,wired,\n", "a detector's id starts det:")):
            with self.subTest(msg=msg), self.assertRaisesRegex(bdm.MapError, msg):
                self.read(text)

    def test_the_main_and_upper_reader_leaves_staging_rows_alone(self):
        self.assertNotIn("Track Barn", bdm.read_pins())

if __name__ == "__main__":
    unittest.main()
