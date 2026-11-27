"""Naming-layers step 7: one row path for every level. build_device_map.master_outputs makes every level's rows from
the plan and puts the owner's values (devices_field.csv) over them the same way: a staging device with no field row
gets generated values instead of stopping the build, and a main or upper device takes the owner's name. Runs over the
committed drawing (needs the plugin; skipped without it, failing with SCHEMATIC_REQUIRED=1); every write goes to a
temporary copy of the device master's files."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_device_map as bdm  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402

devices = bdm.devices
railroad = bdm.railroad


def skip_or_fail(exc: Exception) -> None:
    if os.environ.get("SCHEMATIC_REQUIRED") == "1":
        raise AssertionError(f"the plugin is required: {exc}")
    raise unittest.SkipTest(str(exc))


class OneRowPath(RepoReadOnly, unittest.TestCase):
    """master_outputs over a copy of the device master's two files, its field file edited by hand."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import build_layout_le as bl
        try:
            cls.bands, cls.joined, runs, corners = bdm.solve()
        except bl.BuildError as exc:
            skip_or_fail(exc)
        cls.runs = staticmethod(runs)
        rr = bdm.railroad.Railroad(bdm.sources(), upto="inputs")
        _cp, cls.main_rows, cls.parts = bdm.build(cls.bands, cls.joined, runs, bdm.MapInputs.of(rr), corners)

    def copy(self, edit=None) -> devices.Files:
        """A copy of the master's files in a temporary folder, its field rows passed through `edit` (written as
        text, unchecked, as a hand edit would be)."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(os.rmdir, d)            # runs last: cleanups run in reverse
        files = devices.pair_copy(d)
        for p in (files.master, files.field, files.dictionary):
            self.addCleanup(os.remove, p)       # by full path (rmtree's relative unlinks look like repo writes)
        if edit:
            rows = edit([dict(r) for r in devices.field_rows(files)])
            files.field.write_text(devices.master_text(rows), encoding="utf-8")
        return files

    def write(self, files: devices.Files) -> dict[tuple[str, str], dict]:
        """master_outputs over `files`, written there; {(level, id): row} of the merged view read back."""
        said = []
        out = bdm.master_outputs(self.bands, self.joined, self.runs, self.main_rows, self.parts, files,
                                 warn=said.append)
        devices.write_all(files, out)
        self.said = said
        return {devices.key_of(r): dict(r) for r in devices.load(files)}

    def generated(self, files: devices.Files, level: str, ident: str) -> dict:
        return next(dict(r) for r in devices.generated_rows(files) if (r["level"], r["id"]) == (level, ident))

    def test_the_committed_files_come_back_byte_identical(self):
        files = self.copy()
        out = bdm.master_outputs(self.bands, self.joined, self.runs, self.main_rows, self.parts, files,
                                 warn=lambda line: None)
        # the generated file as it is, written again as hartlib.devices writes it
        self.assertEqual(out[files.master], devices.master_text(devices.generated_rows(files)))

    def test_a_block_with_no_plan_length_keeps_the_masts_and_writes_the_rows(self):
        """A new staging block has no plan length until plan_lengths.py adds it, which needs the block's rows: the
        device map writes them with staging's last mast rows and says why (code review of naming-layers step 12)."""
        import device_map_masts as dmm
        files = self.copy()
        real = dmm.block_cm
        short = lambda rows, path=None: {k: v for k, v in real(rows, path).items() if k != "Track Barn"}  # noqa: E731
        held = []
        with unittest.mock.patch.object(dmm, "block_cm", short):
            with self.assertRaisesRegex(dmm.MissingLengths, r"no plan length for \['Track Barn'\]"):
                dmm.staging_masts(self.bands, self.joined, self.runs, list(devices.load(files)), files)
            out = bdm.master_outputs(self.bands, self.joined, self.runs, self.main_rows, self.parts, files,
                                     warn=lambda line: None, held=held)
        self.assertEqual(out[files.master], devices.master_text(devices.generated_rows(files)))
        self.assertEqual(len(held), 1)
        self.assertIn("Track Barn", held[0])

    def test_a_staging_turnout_with_no_field_row_is_generated(self):
        """Switch 9's field row taken out: its turnout row is generated from the plan and wiring.csv (it stopped,
        "no row in devices_field.csv", before step 7), and only the owner's cells it no longer has change."""
        before = self.write(self.copy())[("1", "switch:9")]
        files = self.copy(lambda rows: [r for r in rows if (r["level"], r["id"]) != ("1", "switch:9")])
        got = self.write(files)[("1", "switch:9")]
        self.assertEqual((got["user_name"], got["role"], got["assignment"], got["system_name"], got["jmri_name"],
                          got["node"], got["wiring"], got["trial_name"]),
                         ("Switch 9", "turnout", "field", before["system_name"], before["system_name"], before["node"],
                          before["wiring"], "Switch 9"))
        # the owner's cell it had and the generator does not make: the JMRI name the panels bound it by ("Switch 9";
        # generated, its address); its DCC address stays, as its alias's field row gives it, and its place is its
        # switch's in the switch lists either way (a turnout row has no cp)
        self.assertEqual({c for c in got if got[c] != before[c]}, {"jmri_name"})
        self.assertEqual((before["jmri_name"], got["cp"], bdm.devices.place(got), got["dcc"]),
                         ("Switch 9", "", "Engine House", "119"))
        # the generated file now holds the generated values the owner's row used to blank
        mine = self.generated(files, "1", "switch:9")
        self.assertEqual((mine["role"], mine["assignment"], mine["trial_name"]), ("turnout", "field", "Switch 9"))

    def test_a_staging_block_with_no_field_row_is_generated(self):
        """Track Barn's block row taken out of the field file: the block is generated (a JMRI block of its own under
        the next free number, as a part's, its comment the generated one with its detector) instead of stopping;
        its detector keeps the owner's row."""
        files = self.copy(lambda rows: [r for r in rows if (r["level"], r["id"]) != ("1", "block:7A-13C")])
        rows = self.write(files)
        got = rows[("1", "block:7A-13C")]
        self.assertEqual((got["user_name"], got["role"], got["assignment"], got["jmri_comment"]),
                         ("Track Barn", "track", "virtual", "Track Barn; occupancy Block 13-1 / M2S1300"))
        self.assertRegex(got["jmri_name"] + " " + got["layout_block"], r"^IB:AUTO:00(\d\d) ILB\1$")
        taken = {r[c] for k, r in rows.items() if k != ("1", "block:7A-13C")
                 for c in ("system_name", "jmri_name", "layout_block") if r[c]}
        self.assertFalse({got["jmri_name"], got["layout_block"]} & taken)
        self.assertEqual(rows[("1", "det:block:7A-13C")]["blocks"], "Track Barn")
        # the next build over the written files gives the block the same numbers (the builder's name memory)
        again = self.write(files)[("1", "block:7A-13C")]
        self.assertEqual((again["jmri_name"], again["layout_block"]), (got["jmri_name"], got["layout_block"]))

    def test_a_renamed_block_with_no_bean_names_keeps_its_numbers(self):
        """Code review of step 7: a field row giving Track Barn's name but no bean names gets the builder's numbers,
        and keeps them when the owner renames it (the memory is by id)."""
        def strip(name):
            def edit(rows):
                r = next(r for r in rows if (r["level"], r["id"]) == ("1", "block:7A-13C"))
                r.update(user_name=name, system_name="", jmri_name="", layout_block="", assignment="")
                return rows
            return edit
        files = self.copy(strip("Track Barn"))
        first = self.write(files)[("1", "block:7A-13C")]
        renamed = strip("Track Barn Lead")([dict(r) for r in devices.field_rows(files)])
        files.field.write_text(devices.master_text(renamed), encoding="utf-8")
        again = self.write(files)[("1", "block:7A-13C")]
        self.assertEqual((again["user_name"], again["jmri_name"], again["layout_block"]),
                         ("Track Barn Lead", first["jmri_name"], first["layout_block"]))
        self.assertRegex(first["jmri_name"], r"^IB:AUTO:\d{4}$")

    def test_a_main_row_naming_a_staging_block_follows_its_rename(self):
        """Code review of step 7: renames are followed over every level at once. Today a main mast that faces a
        staging helix block faces main's own row of it (named from the same store), so a main row is made to name a
        staging-only block here (Mast 132RA facing Track East Ext): the owner's rename of that block reaches it."""
        def name(rows):
            next(r for r in rows if (r["level"], r["id"]) == ("1", "block:5B-7A"))["user_name"] = "Track East Spur"
            return rows
        files = self.copy(name)
        main = [dict(r, facing="Track East Ext") if r["user_name"] == "Mast 132RA" else r for r in self.main_rows]
        out = bdm.master_outputs(self.bands, self.joined, self.runs, main, self.parts, files, warn=lambda line: None)
        devices.write_all(files, out)
        mast = next(r for r in devices.load(files) if r["level"] == "2" and r["user_name"] == "Mast 132RA")
        self.assertEqual(mast["facing"], "Track East Spur")

    def test_a_main_or_upper_device_takes_the_owners_name(self):
        """A field row naming main's Track 103 Spur (block:103BB-end) "Track Coal Spur": the builder takes the name
        (before step 7 the write stopped: "does not take the owner's name"), the device master has it, and the
        cells that name the block follow it (its detector's blocks)."""
        def name(rows):
            row = dict.fromkeys(devices.COLUMNS, "")
            row.update(level="2", layer="block", id="block:103BB-end", user_name="Track Coal Spur")
            return rows + [row]
        files = self.copy(name)
        rows = self.write(files)
        got = rows[("2", "block:103BB-end")]
        self.assertEqual((got["user_name"], got["role"], got["written_by"]), ("Track Coal Spur", "spur",
                                                                               "build_device_map.py"))
        self.assertEqual(rows[("2", "det:block:103BB-end")]["blocks"], "Track Coal Spur")
        self.assertEqual(self.generated(files, "2", "block:103BB-end")["user_name"], "Track Coal Spur")
        self.assertTrue(any("Track 103 Spur" in line and "Track Coal Spur" in line for line in self.said),
                        self.said)          # the rename is said (hartlib.device_changes)
        # step 13: the railroad's device-map check reads the detector and the virtual names by id, so the renamed
        # block passes (before, read_device_map stopped: its detector BS 103 Spur is not named for Track Coal Spur)
        dm = railroad.read_device_map(files.master)
        self.assertEqual(dm.occupancy["Track Coal Spur"].user_name, "BS 103 Spur")
        owner = {(int(lv), i) for (lv, i), r in devices.field_index(files).items() if r.get("user_name")}
        self.assertEqual(railroad.check_virtual_names(dm.rows, owner), [])
        self.assertTrue(railroad.check_virtual_names(dm.rows))      # taken as generated, its sensor is wrong
        # step 8: the blocks are numbered over the generated names, so the renamed block and every other keep theirs
        before = {k: (r["jmri_name"], r["layout_block"]) for k, r in self.write(self.copy()).items()}
        self.assertEqual({k: (r["jmri_name"], r["layout_block"]) for k, r in rows.items()}, before)

    def test_a_block_rows_bean_names_come_from_block_numbering(self):
        """Step 8: build_device_map writes each main and upper block row's jmri_name and layout_block from
        block_numbering.csv (hartlib.block_numbering). In a copy of the file, Track 227-241 1 (block:227C-241B#1)
        loses the loop's old sort place (numbered_as) and is appended after the five appended blocks instead: its row
        takes the last number, the blocks after its old place move up one, and a helix block gets none."""
        bn = bdm.block_numbering
        rows = [devices.master_row(o, bdm.WRITER) for o in self.main_rows] + [dict(p) for p in self.parts]
        now = {(r["level"], r["id"]): (r["jmri_name"], r["layout_block"]) for r in bdm.block_beans(rows)
               if r["layer"] == "block"}
        committed = {(r["level"], r["id"]): (r["jmri_name"], r["layout_block"]) for r in devices.load()
                     if r["level"] in bn.LEVELS and r["layer"] == "block"}
        self.assertEqual(now, committed)
        self.assertEqual(now[("2", "block:107B-107C#1")], ("IB:C3:0041", "ILB1041"))
        self.assertEqual({v for k, v in now.items() if k[1] in ("block:131AA-helix", "block:131BB-helix")}, {("", "")})
        d = Path(tempfile.mkdtemp())
        self.addCleanup(os.rmdir, d)
        path = d / bn.PATH.name
        text = bn.PATH.read_text(encoding="utf-8")
        old = "block:227C-241B#1,Track 227-241,,,"
        self.assertIn(old, text)
        path.write_text(text.replace(old, "block:227C-241B#1,,6,,"), encoding="utf-8")
        self.addCleanup(os.remove, path)        # by full path, as copy()'s
        moved = {(r["level"], r["id"]): r["jmri_name"] for r in bdm.block_beans(rows, path)
                 if r["layer"] == "block"}
        last = max(v[0] for v in now.values())
        self.assertEqual(moved[("3", "block:227C-241B#1")], last)
        was = int(now[("3", "block:227C-241B#1")][0][-4:])
        shifted = {k for k, v in now.items() if v[0] and was < int(v[0][-4:])}
        self.assertTrue(shifted)
        for k in shifted:
            self.assertEqual(int(moved[k][-4:]), int(now[k][0][-4:]) - 1, k)


if __name__ == "__main__":
    unittest.main()
