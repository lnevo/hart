"""check_name_copies.py passes on the repo and catches a hand-kept copy left behind by a rename.

The 16R rename (PR #441) touched 13 files. Each test below renames in a temporary copy
of devices.csv the way ADR-005 does it (the row takes the new name; the master keeps no alias row, so the
old name is simply no longer anything's) and expects every copy of the old name to fail.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/audit"))
import check_name_copies as check  # noqa: E402

sys.path.insert(0, str(ROOT / "tools/hartlib/tests"))
from master_edit import drop  # noqa: E402
from hartlib import devices  # noqa: E402

MAP = ROOT / check.DEVICES_REL
TABLES = ROOT / check.TABLES_REL


def renamed_map(path: Path, renames: dict[str, str]) -> str:
    """The text of the master at `path` after renaming each old user name to its new one (ADR-005)."""
    rows = [dict(r.cells(), user_name=renames.get(r.user_name, r.user_name)) for r in devices.load(path)]
    return devices.master_text(rows)


class NameCopiesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.map = (self.tmp / check.DEVICES_REL).with_name(devices.ONE_FILE)     # a one-file copy of the master
        self.map.parent.mkdir(parents=True)
        devices.one_file_copy(self.map)          # the master as one file (no field file beside it)
        self.tables = self.tmp / check.TABLES_REL
        self.tables.parent.mkdir(parents=True)
        self.tables.write_text(TABLES.read_text(encoding="utf-8"), encoding="utf-8")

    def write(self, rel: str, text: str) -> str:
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return rel

    def rename(self, **renames: tuple[str, str]) -> None:
        """Rename in the map copy (ADR-005) and, for a block, in the tables.xml copy (PanelPro)."""
        pairs = dict(renames.values())
        self.map.write_text(renamed_map(self.map, pairs), encoding="utf-8")
        text = self.tables.read_text(encoding="utf-8")
        for old, new in pairs.items():
            text = text.replace(f"<userName>{old}</userName>", f"<userName>{new}</userName>")
        self.tables.write_text(text, encoding="utf-8")

    def stale(self, files: list[str], allow=None) -> list[str]:
        hits, _counts, _used = check.run(self.tmp, files, allow=allow or {}, devices_csv=self.map)
        return [str(h) for h in hits]

    def test_repo_is_clean(self):
        hits, counts, used = check.run(ROOT)
        self.assertEqual([], [str(h) for h in hits])
        self.assertEqual([], check.unused_allow(check.ALLOW, used))
        self.assertGreater(len(counts), 50, "the scan read almost nothing; is the file list right?")

    def test_current_names_pass(self):
        f = self.write("tools/x.py", 'M = "Mast 32R"\nT = ("Track Scale", "Track S-R", "OS Switch 23a")\n')
        self.assertEqual([], self.stale([f]))

    def test_renamed_mast_and_track_fail_where_copied(self):
        f = self.write("tools/x.py", 'M = "Mast 32R"\n# runs on Track Scale\n')
        self.rename(mast=("Mast 32R", "Mast 32RX"), track=("Track Scale", "Track Weigh"))
        # the master keeps no alias row, so a renamed track's old name is no longer anything's and is not matched
        # (the module text); a mast is matched by its shape, renamed or never there
        self.assertEqual(["tools/x.py:1: 'Mast 32R' is not a current name"], self.stale([f]))
        # The new names are current.
        g = self.write("tools/y.py", 'M = "Mast 32RX"\nT = "Track Weigh"\n')
        self.assertEqual([], self.stale([g]))

    def test_rename_in_a_copy_of_the_repo_names_the_hand_kept_copies(self):
        """Step 3 of the hand-off: rename one mast and one track; every copy is found."""
        renamed = self.tmp / "renamed.csv"
        renamed.write_text(renamed_map(MAP, {"Mast 24RB": "Mast 24RBX", "Track Scale": "Track Weigh"}),
                           encoding="utf-8")
        # PanelPro renames the block in tables.xml too (then make tables-pull).
        tables_xml = self.tmp / "tables.xml"
        text = TABLES.read_text(encoding="utf-8")
        self.assertIn(">Track Scale<", text)
        tables_xml.write_text(text.replace(">Track Scale<", ">Track Weigh<"), encoding="utf-8")
        hits, _counts, _used = check.run(ROOT, devices_csv=renamed, tables_xml=tables_xml)
        files = {h.path for h in hits}
        # No hand-kept copy of a mast name is left: masts.csv, which held the staging masts' copies as
        # staging_masts.csv did, is generated (build_masts.py --check names a stale one). (A renamed track's old name
        # is no longer matched, the master having no alias rows.)
        self.assertEqual(set(), {h.name for h in hits}, files)
        # Generated files under their own --check and the map itself are not read.
        self.assertFalse(any(f.startswith(check.SKIP_PREFIXES) for f in files), files)

    def test_a_block_with_no_identity_row_is_current_through_tables_xml(self):
        """A block with no identity row in the map (as the hidden yard throats had until 2026-11-17) is current while
        tables.xml holds it."""
        drop(self.map, ("1", "block", "Track Barn"))
        f = self.write("tools/x.py", 'T = "Track Barn"\n')
        self.assertNotIn("Track Barn", check.load_names(self.map)[0], "its identity row is removed for this test")
        self.assertEqual([], self.stale([f]))

    def test_unknown_mast_or_os_fails_outside_tests(self):
        f = self.write("tools/x.py", 'M = "Mast 99X"\nO = "OS Switch 98"\n')
        self.assertEqual(2, len(self.stale([f])))
        t = self.write("tools/tests/test_x.py", 'M = "Mast 99X"\n')
        self.assertEqual([], self.stale([t]))

    def test_numbered_tracks_and_jmri_default_masts_are_not_names(self):
        f = self.write("tools/x.py", '"Yard Track 1", "Track 7", "Signal Mast 1"\n')
        self.assertEqual([], self.stale([f]))

    def test_markdown_and_generated_files_are_not_read(self):
        md = self.write("wiki/x.md", "Mast 32L was renamed.\n")
        gen = self.write("www/data/x.json", '{"m": "Mast 32L"}\n')
        self.assertEqual([], self.stale([md, gen]))

    def test_frozen_schematic_files_are_read_and_generated_ones_not(self):
        sch = "jmri/layouts/hart/data/schematic/"
        for rel in ("staging_le/masts.csv", "staging_le/overlay.json", "plan_overrides.json"):
            self.assertTrue(check.readable(sch + rel), rel)
        for rel in ("signals.json", "masts.csv", "inputs/staging.json"):
            self.assertFalse(check.readable(sch + rel), rel)
        hand = self.write(sch + "staging_le/masts.csv", "mast\nMast 32L\n")
        self.assertEqual([f"{hand}:2: 'Mast 32L' is not a current name"], self.stale([hand]))

    def test_a_master_that_cannot_be_read_stops_the_check(self):
        with self.assertRaisesRegex(devices.DevicesError, "cannot read it"):
            check.run(self.tmp, [], devices_csv=self.tmp / "missing.csv")

    def test_a_folder_that_is_not_a_checkout_stops_instead_of_walking_it(self):
        with self.assertRaises(check.NameCopiesError) as cm:
            check.tracked_files(self.tmp)
        self.assertIn("needs git", str(cm.exception))
        self.assertIsInstance(cm.exception.__cause__, check.files.GitError)

    def test_allow_covers_only_its_names_and_reports_unused(self):
        f = self.write("tools/x.py", '"Mast 32L", "Mast 99Z"\n')
        allow = {"tools/x.py": (frozenset({"Mast 32L", "Mast 31L"}), "dated record")}
        self.assertEqual(["tools/x.py:1: 'Mast 99Z' is not a current name"], self.stale([f], allow))
        _hits, _counts, used = check.run(self.tmp, [f], allow=allow, devices_csv=self.map)
        self.assertEqual(["ALLOW tools/x.py: 'Mast 31L' is no longer there; remove it"],
                         check.unused_allow(allow, used))


if __name__ == "__main__":
    unittest.main()
