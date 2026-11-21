"""block_layer.py, the one block process of every level, and build_device_map.staging_rows, which writes staging's
block and occupancy rows from it: the rule, block_exceptions.csv's rows and stops, and the invariants (level
unification step 5 part 1, owner 2026-11-20). Runs over the committed drawing (needs the plugin; skipped without it,
failing with SCHEMATIC_REQUIRED=1); every write goes to a temporary folder."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import block_layer as BL  # noqa: E402
import build_device_map as bdm  # noqa: E402
devices = bdm.devices
from repo_read_only import RepoReadOnly  # noqa: E402

HEAD = ",".join(BL.EXCEPTION_COLUMNS) + "\n"
# a piece of track at one end inside an OS block, its length given (the row OS Switch 7 had until step 5 part 2)
SCALE_AT_7 = "1,track,5,7,1,7,OS Switch 7,23,,a test row\n"
# the 25 main and upper links (tracks between two switches under LINK_CM), each in the lower-numbered switch's OS
# block (owner, 2026-11-20: LINK_CM 50 on every level; at a double crossover the corner block of its leg), but where a
# home mast stands at a switch's points facing the link: then in the OS block at its other end (125-129, 201-205,
# 227-231, 229-233 for Masts 126RB, 202R, 228RA and 230LB; owner, 2026-11-20: the block boundary is at the mast)
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
        cls.split = BL.split_edges(cls.found, cls.levels, bdm.SPLIT)
        cls.committed = BL.exceptions_path().read_text(encoding="utf-8")

    def layer(self, text: str | None = None) -> BL.Layer:
        """The staging layer with block_exceptions.csv's text `text` (default: the committed file)."""
        if text is None:
            return BL.layer(self.bands, self.runs, self.found, self.levels, self.split,
                            BL.read_exceptions(self.found, self.bands, self.levels))
        p = temp_file("block_exceptions.csv", text)
        try:
            ex = BL.read_exceptions(self.found, self.bands, self.levels, p)
        finally:
            remove(p)
        return BL.layer(self.bands, self.runs, self.found, self.levels, self.split, ex)

    posts = None            # the home masts' places for main_upper (None: the rule's)

    def main_upper(self, text: str | None = None) -> BL.Layer:
        """The main and upper layer (build_device_map.main_upper_layer) with block_exceptions.csv's text `text`
        (default: the committed file)."""
        found = bdm.named_tracks(self.bands, self.joined, self.runs)
        rr = bdm.railroad.Railroad(bdm.sources(), upto="inputs")
        switches = bdm.railroad.join_main_upper(rr.level_control_points, rr.local_switches, bdm.LOCAL.name)
        cp_of = {s: sw.cp for s, sw in switches.items() if sw.cp}
        split, corners = bdm.split_edges(found=found), bdm.corner_blocks_of(self.bands, self.corners)
        _home, posts = bdm.home_and_posts(self.bands, self.joined, found, bdm.LEVELS, cp_of, corners,
                                          set(split.values()))
        self.last_posts, self.mu_found = posts, found
        args = (self.bands, self.runs, found, split, corners, posts if self.posts is None else self.posts)
        if text is None:
            return bdm.main_upper_layer(*args)
        p = temp_file("block_exceptions.csv", text)
        try:
            with unittest.mock.patch.object(BL, "exceptions_path", return_value=p):
                return bdm.main_upper_layer(*args)
        finally:
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
        self.assertIn("block_exceptions.csv line", parts["Track 13-15"]["why"])

    def test_without_its_row_the_rule_gives_the_lower_numbered_switch(self):
        self.assertEqual(self.layer(self.without("1,track,13,15,")).parts["Track 13-15"]["part_of"], "OS Switch 13")
        self.assertEqual(self.layer(self.without("1,track,23,31,")).parts["Track 23-31"]["part_of"], "OS Switch 23b")

    def test_pieces_at_both_ends_part_the_track_with_no_block_of_its_own(self):
        lay = self.layer()
        self.assertEqual({k: v["part_of"] for k, v in lay.parts.items() if k.startswith("Track 1-3")},
                         {"Track 1-3 at 1": "OS Switch 1", "Track 1-3 at 3": "OS Switch 3"})
        self.assertNotIn("Track 1-3", lay.tracks)

    def test_a_piece_marked_inside_stays_in_its_os_block_with_no_block_of_its_own(self):
        """block_exceptions.csv's `inside` (owner, 2026-11-20): the two halves of 35-39 stay inside OS Switch 35b and
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
        self.stops(HEAD + "1,track,9,11,,,OS Switch 9,,no,\n", "inside is yes or empty")
        self.stops(HEAD + "1,crossover_half,7,13,,,OS Switch 7,,yes,\n", "with no parallel, end, cm or inside")

    def test_a_piece_at_one_end_leaves_the_rest_its_own_block(self):
        lay = self.layer(self.committed + SCALE_AT_7)
        self.assertEqual(lay.parts["Track Scale at 7"]["part_of"], "OS Switch 7")
        self.assertIn("Track Scale", lay.tracks)

    def test_os_switch_7_ends_at_the_switch(self):
        # owner, 2026-11-20 (step 5 part 2): Track Scale is one block, none of it inside OS Switch 7
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
        self.assertFalse(hasattr(BL, "FOLD_LINKS"))      # one rule for every level (step 5 part 2)
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
        self.stops(HEAD + "1,spur,9,11,,,OS Switch 9,\n", "kind one of track, crossover_half")
        self.stops(HEAD + "4,track,9,11,,,OS Switch 9,\n", "level is 1, 2 or 3")
        self.stops(HEAD + "1,track,9,11,,,Track Barn,\n", "is no OS block")
        self.stops(HEAD + "1,track,11,9,,,OS Switch 9,\n", "lower first")
        self.stops(HEAD + "1,track,9,11,,13,OS Switch 9,\n", "its end empty or one of them")
        self.stops(HEAD + "1,crossover_half,7,13,,7,OS Switch 7,\n", "with no parallel, end, cm or inside")

    def test_a_row_that_matches_no_track_or_half_stops(self):
        self.stops(self.committed + "1,track,2,4,,,OS Switch 2,\n", "no track runs Switch 2 to Switch 4")
        self.stops(self.committed + "1,crossover_half,7,9,,,OS Switch 7c,\n",
                   "no crossover half of Switch 7 has its leg A track running to Switch 9")

    def test_a_row_given_twice_stops(self):
        self.stops(self.committed + "1,track,13,15,,,OS Switch 15,\n", "Track 13-15 is given a block on line")
        self.stops(self.committed + "1,crossover_half,7,13,,,OS Switch 7,\n", "given its block on line")

    def test_a_block_that_is_not_the_os_block_at_its_end_stops(self):
        self.stops(self.without("1,track,13,15,") + "1,track,13,15,,,OS Switch 17,\n",
                   "Track 13-15 is given OS Switch 17, the OS block of neither")
        self.stops(self.without("1,track,1,3,,1,") + "1,track,1,3,,1,OS Switch 3,\n",
                   "the piece of Track 1-3 at Switch 1 is given OS Switch 3, not that switch's OS block OS Switch 1")

    def test_one_crossover_half_alone_stops(self):
        self.stops(self.without("1,crossover_half,7,5,"), "crossover 7: give both halves")

    def test_a_split_track_with_rows_stops(self):
        self.stops(self.committed + "1,track,37,39,,,OS Switch 37,\n", "split in halves and given to OS blocks")

    def test_a_main_or_upper_row_applies_on_its_level(self):
        lay = self.main_upper(self.committed + "2,track,113,115,,,OS Switch 115,,\n")
        self.assertEqual(lay.parts["Track 113-115"]["part_of"], "OS Switch 115")
        self.assertIn("block_exceptions.csv line", lay.parts["Track 113-115"]["why"])
        with self.assertRaisesRegex(BL.BlockError, r"\(level 3\): no track runs Switch 113 to Switch 115"):
            self.main_upper(self.committed + "3,track,113,115,,,OS Switch 115,,\n")

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
        self.stops(self.without("1,track,13,15,") + "1,track,13,15,,,OS Switch 15,10,\n", "only a piece at one end")

    # ---------------------------------------------------------------- halves

    def renamed(self, names: dict):
        """(bands, found) with the staging strands' plan names changed ({strand: name})."""
        import copy
        bands = copy.deepcopy(self.bands)
        bi = next(i for i, (t, _b, _o) in enumerate(bands) if self.levels.get(t) == 1)
        for sid, name in names.items():
            bands[bi][1]["strands"][sid]["name"] = name
        over = bdm.layer_files.read("plan_overrides", bdm.STAGING_SHEET, bdm.OVERRIDES.parent)
        return bands, bdm.named_tracks(bands, self.joined, self.runs, over)

    def halves_layer(self, names: dict) -> BL.Layer:
        bands, found = self.renamed(names)
        return BL.layer(bands, self.runs, found, self.levels, BL.split_edges(found, self.levels, bdm.SPLIT),
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
        with self.assertRaisesRegex(BL.BlockError, "helix_tracks.csv does not name"):
            BL.name_tracks([dict(t) for t in self.found], self.bands, {})

    def test_a_track_with_two_plan_names_must_be_split(self):
        with self.assertRaisesRegex(BL.BlockError, r"Track 37-39 carries plan names \['K-1', 'K-2'\] but is one "
                                                   "block"):
            BL.layer(self.bands, self.runs, self.found, self.levels, {},
                     BL.read_exceptions(self.found, self.bands, self.levels))


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
    """build_device_map.staging_rows over a copy of the master: the field facts ride along, the rest is the
    builder's, and a block with no row, or a row with no block, stops."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import build_layout_le as bl
        try:
            cls.bands, cls.joined, runs, _corners = bdm.solve()
        except bl.BuildError as exc:
            raise unittest.SkipTest(str(exc))
        cls.runs = staticmethod(runs)

    def rows(self, edit=None, extra_exception=""):
        """staging_rows over a copy of the master (`edit`ed) and of block_exceptions.csv (plus `extra_exception`)."""
        rows = [dict(r) for r in devices.load()]
        if edit:
            rows = edit(rows)
        p = temp_file("devices.csv", devices.master_text(rows))
        self.addCleanup(remove, p)
        ex = temp_file("block_exceptions.csv", BL.exceptions_path().read_text(encoding="utf-8") + extra_exception)
        self.addCleanup(remove, ex)
        self.files = devices.Files.under(p.parent)
        return bdm.staging_rows(self.bands, self.joined, self.runs, self.files, exceptions=ex)

    def test_the_committed_rows_come_back_as_they_are(self):
        got, adopts, drops = self.rows()
        self.assertEqual(drops, set())
        want = [r for r in devices.load() if r["level"] == "1" and r["layer"] in ("block", "occupancy")]
        self.assertEqual(got, [dict(r) for r in want])
        self.assertEqual(adopts, {("1", r["layer"], r["user_name"]) for r in want})

    def test_a_block_that_becomes_a_part_frees_its_detector_as_a_spare(self):
        """East Lead given to OS Switch 33: its block row becomes a part (no name-map columns), its detector a spare
        row named by its node input, and both old keys are dropped from the name map on purpose."""
        got, adopts, drops = self.rows(extra_exception="1,track,33,35,,,OS Switch 33,,\n")
        by = {(r["layer"], r["user_name"]): r for r in got}
        part = by[("block", "Track East Lead")]
        self.assertEqual((part["role"], part["part_of"], part["pnm_order"], part["assignment"]),
                         ("part", "OS Switch 33", "", "virtual"))
        # a JMRI block of its own (owner, 2026-11-20) under new names, the next free number: not the old block's
        self.assertRegex(part["jmri_name"] + " " + part["layout_block"], r"^IB:AUTO:00(\d\d) ILB\1$")
        self.assertNotIn(("occupancy", "BS East Lead"), by)
        spare = by[("occupancy", "unused Block 1-7")]
        self.assertEqual((spare["role"], spare["assignment"], spare["system_name"], spare["blocks"]),
                         ("spare", "spare", "M2S106", ""))
        self.assertEqual(drops, {("1", "block", "Track East Lead"), ("1", "occupancy", "BS East Lead")})
        # the master takes it and reads it back as written
        out = devices.outputs_after("build_device_map.py", [], self.files, drops=drops, master_rows=got,
                                    adopts=adopts)
        self.assertIn("unused Block 1-7", out[self.files.master])

    def test_a_block_with_no_row_to_carry_its_field_facts_from_stops(self):
        drop = lambda rows: [r for r in rows if not (r["level"] == "1" and r["user_name"] == "Track Barn")]  # noqa
        with self.assertRaisesRegex(bdm.MapError, "staging block Track Barn: no row in devices.csv"):
            self.rows(drop)

    def test_a_staging_row_the_drawing_has_no_block_for_stops(self):
        def add(rows):
            extra = dict(next(r for r in rows if r["level"] == "1" and r["user_name"] == "Track Barn"),
                         user_name="Track Nowhere", system_name="IB:AUTO:9999", jmri_name="IB:AUTO:9999",
                         layout_block="ILB999", pnm_order="", pnm_cp="", pnm_hardware="", pnm_comment="",
                         written_by="")
            at = next(i for i, r in enumerate(rows) if r["level"] == "1" and r["layer"] == "block")
            return rows[:at] + [extra] + rows[at:]          # a hand-kept row: before the writers' rows
        with self.assertRaisesRegex(bdm.MapError, "the drawing has no block for: block Track Nowhere"):
            self.rows(add)


if __name__ == "__main__":
    unittest.main()
