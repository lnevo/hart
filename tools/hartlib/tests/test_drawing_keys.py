"""hartlib.drawing_keys: the one reader of the device master's drawing keys, keyed by device ID (naming-layers step 13).

The committed master's keys, per level set as the Layout Editor build, the staging device map and the CATS desks read
them; a rename in a copy's field file changes the name a key gives and nothing else; and the rows it stops on.
"""
from __future__ import annotations

import csv
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from hartlib import devices, drawing_keys  # noqa: E402


class Committed(unittest.TestCase):
    def test_every_level_reads_one_device_per_key(self) -> None:
        staging, main_upper = drawing_keys.read(("1",)), drawing_keys.read(("2", "3"))
        self.assertEqual(staging.name("Switch 7"), "Switch 7")
        self.assertEqual(staging.id("OS 35 A-39A"), "os:35:A-39A")
        self.assertEqual(staging.id("Track 35A-39A 1/2"), "os:35:A-39A")      # an OS block holds a track piece
        self.assertEqual(staging.keys("block:1C-5A#1+1C-5A#2"), {"Track 1C-5A #1", "Track 1C-5A #2"})
        self.assertEqual(main_upper.id("Switch 101A"), main_upper.id("Switch 101B"))     # one crossover turnout
        self.assertEqual(main_upper.name("Track 107B-107C #1"), "Track 107 Loop 1")      # a loop half
        self.assertEqual(main_upper.row("Track 101AB-103AA")["role"], "part")
        self.assertIn("Track 101-103", main_upper.parts())
        self.assertFalse(any(r["role"] == "lcc_alias" for r in main_upper.rows.values()))
        # every turnout and block row of the master is read, by its id
        want = {(r.level_cell, r.id) for r in devices.load()
                if r.level and r.layer in drawing_keys.LAYERS and r.role != "lcc_alias"}
        got = {i for k in (staging, main_upper) for i in k.rows}
        self.assertEqual(got, want)

    def test_of_selects_by_layer_role_and_part(self) -> None:
        k = drawing_keys.read(("2", "3"))
        self.assertEqual(k.of("turnout")["Switch 101A"], "Switch 101")
        self.assertTrue(all(n.startswith("OS Switch") for n in k.of("block", role="os").values()))
        self.assertEqual(set(k.of("block", parts=True).values()), set(k.parts()))
        self.assertFalse(set(k.of("block", parts=False).values()) & set(k.parts()))


class Renamed(unittest.TestCase):
    """An owner's name in a copy's field file reaches the key's name by ID; the keys and IDs stay."""

    def test_a_field_rename_moves_only_the_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            here = devices.Files.here()
            for src in (here.master, here.dictionary, here.field):
                shutil.copy(src, data / src.name)
            field = devices.field_path(data)
            rows = list(csv.DictReader(io.StringIO(field.read_text(encoding="utf-8"))))
            row = dict.fromkeys(rows[0], "")
            row.update(level="2", layer="block", id="block:103BB-end", user_name="Track Coal Spur")
            field.write_text(devices.master_text(rows + [row]), encoding="utf-8")
            files = devices.Files.under(data)
            before, after = drawing_keys.read(("2", "3")), drawing_keys.read(("2", "3"), files)
        self.assertEqual(dict(before.ids), dict(after.ids))
        self.assertEqual(after.name("Track 103BB-end"), "Track Coal Spur")
        self.assertEqual(before.name("Track 103BB-end"), "Track 103 Spur")


class Stops(unittest.TestCase):
    def rows(self, *extra: dict) -> list[dict]:
        base = [dict(level="2", layer="block", role="track", id="block:1A-2B", user_name="Track 1-2",
                     trial_name="Track 1A-2B", part_of=""),
                dict(level="2", layer="turnout", role="turnout", id="switch:1", user_name="Switch 1",
                     trial_name="Switch 1A, Switch 1B*", part_of=""),
                dict(level="2", layer="turnout", role="lcc_alias", id="dcc:1", user_name="DCC Switch 1",
                     trial_name="", part_of=""),
                dict(level="1", layer="block", role="track", id="block:9A-end", user_name="Track Barn",
                     trial_name="Track 1A-2B", part_of="")]
        return base + list(extra)

    def test_a_good_set(self) -> None:
        k = drawing_keys.read(("2",), rows=self.rows())
        self.assertEqual(dict(k.ids), {"Track 1A-2B": ("2", "block:1A-2B"), "Switch 1A": ("2", "switch:1"),
                                       "Switch 1B": ("2", "switch:1")})   # the "*" left off; level 1 not read
        self.assertEqual(k.id("Switch 1B"), "switch:1")
        self.assertIsNone(k.row("Track 9A-end"))

    def test_an_id_is_unique_on_its_level_only(self) -> None:
        """The master's key is (level, id): the same id on two levels is two devices."""
        k = drawing_keys.read(("2", "3"), rows=self.rows(
            dict(level="3", layer="block", role="track", id="block:1A-2B", user_name="Track 1-2 Upper",
                 trial_name="Track 201A-202B", part_of="")))
        self.assertEqual(k.name("Track 201A-202B"), "Track 1-2 Upper")
        self.assertEqual(k.name("Track 1A-2B"), "Track 1-2")
        self.assertEqual(k.keys("block:1A-2B", "3"), {"Track 201A-202B"})

    def test_each_problem_stops(self) -> None:
        for extra, why in (
                (dict(level="2", layer="turnout", role="lcc_alias", id="dcc:3", user_name="DCC Switch 3",
                      trial_name="Switch 3", part_of=""), "is an LCC alias, which holds no piece"),
                (dict(level="3", layer="block", role="part", id="block:5A-6B", user_name="Track 5-6",
                      trial_name="Track 5A-6B", part_of="Track 1-2"),
                 "is part of 'Track 1-2', no block row of level 3"),
                (dict(level="2", layer="block", role="track", id="block:3A-end", user_name="Track Coal",
                      trial_name="Track 3A-end*", part_of=""), None),       # main and upper: the "*" is bare
                (dict(level="1", layer="block", role="track", id="block:3A-end", user_name="Track Coal",
                      trial_name="Track 3A-end*", part_of=""), r"staging keys are written exactly.*Track 3A-end\*"),
                (dict(level="2", layer="block", role="track", id="block:3A-4B", user_name="Track 3-4",
                      trial_name="", part_of=""), r"Track 3-4 \(level 2, block\) has no trial_name"),
                (dict(level="2", layer="block", role="track", id="block:3A-4B", user_name="Track 3-4",
                      trial_name="Track 1A-2B", part_of=""),
                 r"trial_name Track 1A-2B is given to Track 1-2 \(level 2, block\) and Track 3-4"),
                (dict(level="2", layer="block", role="part", id="block:5A-6B", user_name="Track 5-6",
                      trial_name="Track 5A-6B", part_of="OS Switch 9"), "is part of 'OS Switch 9', no block row"),
                (dict(level="2", layer="block", role="track", id="block:1A-2B", user_name="Track 7-8",
                      trial_name="Track 7A-8B", part_of=""), "id block:1A-2B is Track 1-2"),
                (dict(level="2", layer="block", role="track", id="", user_name="Track 7-8",
                      trial_name="Track 7A-8B", part_of=""), "has no id")):
            levels = ("1", "2", "3")
            base = [r for r in self.rows() if r["level"] != "1"]        # Track Barn's key is main's Track 1A-2B
            with self.subTest(why=why):
                if why is None:
                    self.assertEqual(drawing_keys.read(levels, rows=base + [extra]).name("Track 3A-end"),
                                     "Track Coal")
                    continue
                with self.assertRaisesRegex(drawing_keys.DrawingKeyError, why):
                    drawing_keys.read(levels, rows=base + [extra])


if __name__ == "__main__":
    unittest.main()
