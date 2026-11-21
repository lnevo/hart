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
            cls.bands, cls.joined, runs, _corners = bdm.solve()
        except bl.BuildError as exc:
            if os.environ.get("SCHEMATIC_REQUIRED") == "1":
                raise AssertionError(f"needs the plugin (SCHEMATIC_REQUIRED=1): {exc}")
            raise unittest.SkipTest(str(exc))
        cls.runs = staticmethod(runs)
        over = bdm.layer_files.read("plan_overrides", bdm.STAGING_SHEET, bdm.OVERRIDES.parent)
        cls.levels = bdm.band_levels(over)
        cls.found = bdm.named_tracks(cls.bands, cls.joined, cls.runs, over)
        cls.split = BL.split_edges(cls.found, cls.levels, bdm.SPLIT)
        cls.committed = BL.EXCEPTIONS.read_text(encoding="utf-8")

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

    def test_a_piece_at_one_end_leaves_the_rest_its_own_block(self):
        lay = self.layer()
        self.assertEqual(lay.parts["Track Scale at 7"]["part_of"], "OS Switch 7")
        self.assertIn("Track Scale", lay.tracks)

    def test_a_crossover_without_rows_is_one_os_block(self):
        lay = self.layer(self.without("1,crossover_half,7,"))
        bi = next(iter(lay.bands))
        os_ = {b for n, b in lay.bands[bi]["os"].items() if self.bands[bi][1]["nodes"][n]["label"] == "7"}
        self.assertEqual(os_, {"OS Switch 7"})

    def test_links_stay_blocks_of_their_own_where_the_level_does_not_fold(self):
        with unittest.mock.patch.dict(BL.FOLD_LINKS, {1: False}):
            lay = self.layer()
        self.assertIn("Track 9-11", lay.tracks)
        self.assertNotIn("Track 9-11", lay.parts)
        self.assertIn("Track 13-15", lay.parts)         # an owner's row still applies

    # ---------------------------------------------------------------- the stops

    def test_columns_kinds_and_shapes(self):
        self.stops("level,switch_a\n", "columns")
        self.stops(HEAD + "1,spur,9,11,,,OS Switch 9,\n", "kind one of track, crossover_half")
        self.stops(HEAD + "4,track,9,11,,,OS Switch 9,\n", "level is 1, 2 or 3")
        self.stops(HEAD + "1,track,9,11,,,Track Barn,\n", "is no OS block")
        self.stops(HEAD + "1,track,11,9,,,OS Switch 9,\n", "lower first")
        self.stops(HEAD + "1,track,9,11,,13,OS Switch 9,\n", "its end empty or one of them")
        self.stops(HEAD + "1,crossover_half,7,13,,7,OS Switch 7,\n", "with no parallel or end")

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

    def test_a_row_of_a_level_not_drawn_is_checked_for_shape_only(self):
        self.layer(self.committed + "3,track,2,4,,,OS Switch 2,\n")

    def test_a_helix_track_its_plan_name_does_not_name_stops(self):
        with self.assertRaisesRegex(BL.BlockError, "helix_tracks.csv does not name"):
            BL.name_tracks([dict(t) for t in self.found], self.bands, {})

    def test_a_track_with_two_plan_names_must_be_split(self):
        with self.assertRaisesRegex(BL.BlockError, r"Track 37-39 carries plan names \['K-1', 'K-2'\] but is one "
                                                   "block"):
            BL.layer(self.bands, self.runs, self.found, self.levels, {},
                     BL.read_exceptions(self.found, self.bands, self.levels))


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

    def rows(self, edit=None):
        rows = [dict(r) for r in devices.load()]
        if edit:
            rows = edit(rows)
        p = temp_file("devices.csv", devices.master_text(rows))
        self.addCleanup(remove, p)
        return bdm.staging_rows(self.bands, self.joined, self.runs, devices.Files.under(p.parent))

    def test_the_committed_rows_come_back_as_they_are(self):
        got, adopts = self.rows()
        want = [r for r in devices.load() if r["level"] == "1" and r["layer"] in ("block", "occupancy")]
        self.assertEqual(got, [dict(r) for r in want])
        self.assertEqual(adopts, {("1", r["layer"], r["user_name"]) for r in want})

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
