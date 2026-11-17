"""check_name_copies.py passes on the repo and catches a hand-kept copy left behind by a rename.

The 16R rename (PR #441) touched 13 files. Each test below renames in a temporary copy
of public_name_map.csv the way ADR-005 does it (the identity row takes the new name and
an alias row keeps the old one) and expects every copy of the old name to fail.
"""
from __future__ import annotations

import csv
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/audit"))
import check_name_copies as check  # noqa: E402

MAP = ROOT / check.NAME_MAP_REL
TABLES = ROOT / check.TABLES_REL


def renamed_map(text: str, renames: dict[str, str]) -> str:
    """public_name_map.csv text after renaming each old name to its new one (ADR-005)."""
    rows = list(csv.reader(io.StringIO(text)))
    head, body = rows[0], rows[1:]
    cur, prop = head.index("current"), head.index("proposed")
    out, aliases = [head], []
    for row in body:
        if row[prop] in renames:
            old = row[prop]
            row = list(row)
            if row[cur] == old:
                alias = list(row)
                alias[prop] = renames[old]
                alias[-1] = "historical alias; test rename"
                aliases.append(alias)
                row[cur] = renames[old]
            row[prop] = renames[old]
        out.append(row)
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(out + aliases)
    return buf.getvalue()


class NameCopiesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.map = self.tmp / check.NAME_MAP_REL
        self.map.parent.mkdir(parents=True)
        self.map.write_text(MAP.read_text(encoding="utf-8"), encoding="utf-8")
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
        self.map.write_text(renamed_map(self.map.read_text(encoding="utf-8"), pairs), encoding="utf-8")
        text = self.tables.read_text(encoding="utf-8")
        for old, new in pairs.items():
            text = text.replace(f"<userName>{old}</userName>", f"<userName>{new}</userName>")
        self.tables.write_text(text, encoding="utf-8")

    def stale(self, files: list[str], allow=None) -> list[str]:
        hits, _counts, _used = check.run(self.tmp, files, allow=allow or {})
        return [str(h) for h in hits]

    def test_repo_is_clean(self):
        hits, counts, used = check.run(ROOT)
        self.assertEqual([], [str(h) for h in hits])
        self.assertEqual([], check.unused_allow(check.ALLOW, used))
        self.assertGreater(len(counts), 50, "the scan read almost nothing; is the file list right?")

    def test_current_names_pass(self):
        f = self.write("tools/x.py", 'M = "Mast 16R"\nT = ("Track Scale", "Track S-R West", "OS Switch 23a")\n')
        self.assertEqual([], self.stale([f]))

    def test_renamed_mast_and_track_fail_where_copied(self):
        f = self.write("tools/x.py", 'M = "Mast 16R"\n# runs on Track Scale\nE = "Track Scale East"\n')
        self.rename(mast=("Mast 16R", "Mast 16RX"), track=("Track Scale", "Track Weigh"))
        self.assertEqual(
            ["tools/x.py:1: 'Mast 16R' is not a current name",
             "tools/x.py:2: 'Track Scale' is not a current name"],
            self.stale([f]),
        )
        # The new names are current, and Track Scale East (its own block) still is.
        g = self.write("tools/y.py", 'M = "Mast 16RX"\nT = "Track Weigh"\nE = "Track Scale East"\n')
        self.assertEqual([], self.stale([g]))

    def test_rename_in_a_copy_of_the_repo_names_the_hand_kept_copies(self):
        """Step 3 of the hand-off: rename one mast and one track; every copy is found."""
        renamed = self.tmp / "renamed.csv"
        renamed.write_text(renamed_map(MAP.read_text(encoding="utf-8"),
                                       {"Mast 16R": "Mast 16RX", "Track Scale": "Track Weigh"}),
                           encoding="utf-8")
        # PanelPro renames the block in tables.xml too (then make tables-pull).
        tables_xml = self.tmp / "tables.xml"
        text = TABLES.read_text(encoding="utf-8")
        self.assertIn(">Track Scale<", text)
        tables_xml.write_text(text.replace(">Track Scale<", ">Track Weigh<"), encoding="utf-8")
        hits, _counts, _used = check.run(ROOT, name_map=renamed, tables_xml=tables_xml)
        files = {h.path for h in hits}
        self.assertEqual({"Mast 16R", "Track Scale"}, {h.name for h in hits})
        # Known hand-kept copies today: the throat split spec and the desk generator.
        self.assertIn("jmri/layouts/hart/scripts/apply_yard_throat_blocks.py", files)
        self.assertIn("cats/scripts/wire_digicon.py", files)
        # Generated files under their own --check and the map itself are not read.
        self.assertFalse(any(f.startswith(check.SKIP_PREFIXES) for f in files), files)

    def test_throat_blocks_are_current_through_tables_xml(self):
        """A block with only alias rows in the map (Track S-R West before it got its identity row, 2026-11-17)
        is current while tables.xml holds it, and stale when tables.xml does not."""
        text = self.map.read_text(encoding="utf-8")
        row = "block,Track S-R West,Track S-R West,"
        self.assertIn(row, text)
        self.map.write_text("".join(l for l in text.splitlines(keepends=True) if not l.startswith(row)),
                            encoding="utf-8")
        f = self.write("tools/x.py", 'T = "Track S-R West"\n')
        self.assertNotIn("Track S-R West", check.load_names(self.map)[0], "its identity row is removed for this test")
        self.assertEqual([], self.stale([f]))
        # Without a block of that name in tables.xml, the alias row's proposed name is stale.
        empty = self.write("empty_tables.xml", "<layout-config><blocks/></layout-config>\n")
        self.assertEqual(["tools/x.py:1: 'Track S-R West' is not a current name"],
                         [str(h) for h in check.run(self.tmp, [f], allow={}, tables_xml=self.tmp / empty)[0]])

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
        for rel in ("staging_le/masts.csv", "staging_le/overlay.json", "staging.plan_overrides.json"):
            self.assertTrue(check.readable(sch + rel), rel)
        for rel in ("staging.signals.json", "hands.csv", "device_map_main_upper.csv", "inputs/staging.json"):
            self.assertFalse(check.readable(sch + rel), rel)
        hand = self.write(sch + "staging_le/masts.csv", "mast\nMast 32L\n")
        self.assertEqual([f"{hand}:2: 'Mast 32L' is not a current name"], self.stale([hand]))

    def test_a_folder_that_is_not_a_checkout_stops_instead_of_walking_it(self):
        with self.assertRaises(SystemExit) as cm:
            check.tracked_files(self.tmp)
        self.assertIn("needs git", str(cm.exception))

    def test_allow_covers_only_its_names_and_reports_unused(self):
        f = self.write("tools/x.py", '"Mast 32L", "Mast 99Z"\n')
        allow = {"tools/x.py": (frozenset({"Mast 32L", "Mast 31L"}), "dated record")}
        self.assertEqual(["tools/x.py:1: 'Mast 99Z' is not a current name"], self.stale([f], allow))
        _hits, _counts, used = check.run(self.tmp, [f], allow=allow)
        self.assertEqual(["ALLOW tools/x.py: 'Mast 31L' is no longer there; remove it"],
                         check.unused_allow(allow, used))


if __name__ == "__main__":
    unittest.main()
