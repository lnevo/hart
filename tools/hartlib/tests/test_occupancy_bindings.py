"""hartlib.occupancy_bindings (ADR-039 lane L12): the blocks the CATS desks bind come from the cats_discipline cells of
devices_field.csv, reach the CATS desk builder (digicon_lib.load_disciplines), and a bad cell fails both the master's
check and the sidecar check."""
from __future__ import annotations

import csv
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
sys.path.insert(0, str(ROOT / "cats/scripts"))

from hartlib import devices, occupancy_bindings, track_names  # noqa: E402
import digicon_lib  # noqa: E402

SPEC = importlib.util.spec_from_file_location("check_data", ROOT / "tools/ops/check_data.py")
check_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_data)


def set_field_cell(files: devices.Files, block_id: str, value: str) -> None:
    """Set the cats_discipline of the level 1 field row `block_id` by text, so no check runs before the test's."""
    text = files.field.read_text(encoding="utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    col, idc = rows[0].index("cats_discipline"), rows[0].index("id")
    hit = [r for r in rows[1:] if r[0] == "1" and r[idc] == block_id]
    assert len(hit) == 1, block_id
    hit[0][col] = value
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    files.field.write_text(buf.getvalue(), encoding="utf-8")


class TheRepo(unittest.TestCase):
    def test_the_45_blocks_with_their_names_and_sensors(self):
        rows = occupancy_bindings.rows()
        self.assertEqual(len(rows), 45)
        self.assertEqual(sorted({r["level"] for r in rows}), ["1"])
        self.assertEqual(sum(r["cats_discipline"] == "YARD" for r in rows), 12)
        names = track_names.names_by_id([r["block_id"] for r in rows])
        self.assertEqual({r["block_id"]: r["block_user_name"] for r in rows}, names)
        users = {r.user_name for r in devices.load()}
        self.assertEqual([r for r in rows if r["occupancy_sensor_user_name"] not in users], [])
        by_name = {r["block_user_name"]: r for r in rows}
        self.assertEqual(by_name["Track W-1"]["occupancy_sensor_user_name"], "BS W-1")
        self.assertEqual(by_name["OS Switch 23a"]["occupancy_sensor_user_name"], "BS Switch 23a")
        self.assertEqual(by_name["Track Helix Inner"]["occupancy_sensor_user_name"], "BS Helix Inner")

    def test_only_block_rows_have_one(self):
        self.assertEqual([devices.row_text(r) for r in devices.load()
                          if r.cats_discipline and r.layer != "block"], [])


class OnACopy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.files = devices.pair_copy(Path(self._tmp.name))

    def test_a_discipline_reaches_the_cats_builder(self):
        before = digicon_lib.load_disciplines(self.files.master)
        self.assertEqual(before["Track Main West"], "CTC")
        self.assertEqual(before["Track W-1"], "CTC")          # YARD is written to the desks as CTC
        set_field_cell(self.files, "block:1A-23A", "")         # Track Main West
        set_field_cell(self.files, "block:3B-end", "CTC")      # Track W-1
        after = digicon_lib.load_disciplines(self.files.master)
        self.assertNotIn("Track Main West", after)
        self.assertEqual(len(after), 44)
        got = {r["block_user_name"]: r["cats_discipline"] for r in occupancy_bindings.rows(self.files.master)}
        self.assertEqual(got["Track W-1"], "CTC")
        self.assertEqual(got["Track W-2"], "YARD")

    def test_a_bad_value_fails_the_master_check(self):
        set_field_cell(self.files, "block:3B-end", "ABS")
        with self.assertRaisesRegex(devices.DevicesError, "cats_discipline 'ABS'"):
            devices.load(self.files)

    def test_a_bad_value_fails_the_sidecar_check(self):
        self.assertEqual(check_data.Checker().check(self.files.dictionary), [])
        set_field_cell(self.files, "block:3B-end", "yard")
        found = " | ".join(check_data.Checker().check(self.files.dictionary))
        self.assertIn("cats_discipline", found)
        self.assertIn("yard", found)


if __name__ == "__main__":
    unittest.main()
