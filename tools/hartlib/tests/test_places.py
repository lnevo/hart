"""hartlib.places and hartlib.occupancy_bindings (ADR-039 lane L4c): place ids in the cp cells, block ids in the
occupancy bindings, each read back to the names the builders used before."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import devices, level_masts, occupancy_bindings, places, track_names  # noqa: E402
from hartlib.railroad_facts import FactsError  # noqa: E402

CP_FILES = (devices.FIELD, devices.MASTER, level_masts.PATH)


def cp_cells(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [r["cp"] for r in csv.DictReader(fh)]


class PlacesTest(unittest.TestCase):
    def test_every_cp_item_of_the_repo_files_is_a_known_id(self):
        known = places.table().by_id
        for path in CP_FILES:
            items = {p for c in cp_cells(path) for p in c.split(places.LIST) if c}
            self.assertTrue(items, path.name)
            self.assertEqual(sorted(i for i in items if i not in known), [], path.name)

    def test_the_cells_read_back_as_they_are(self):
        # ids -> names -> ids is the identity on every cell, so a rebuild writes the same bytes (staging's names that
        # are also a staging interlocking's go to the station, as every cell has them)
        for path in CP_FILES:
            for cell in cp_cells(path):
                self.assertEqual(places.ids(places.names(cell)), cell, path.name)

    def test_names(self):
        self.assertEqual(places.names("st:barn;st:engine-house"), "Barn;Engine House")
        self.assertEqual(places.names("st:princess;cp:127"), "Princess;CP 127")
        self.assertEqual(places.names(""), "")
        self.assertEqual(places.ids("Brick;West Yard"), "st:brick;st:west-yard")
        self.assertEqual(places.ids("CP 225"), "cp:225")

    def test_a_staging_interlocking_keeps_its_id_and_name(self):
        t = places.table()
        self.assertEqual(t.by_id["cp:brick"], "Brick")
        self.assertEqual(t.by_name["Brick"], "st:brick")

    def test_an_unknown_id_stops_and_a_plain_name_is_kept(self):
        with self.assertRaises(FactsError):
            places.names("st:nowhere", "x line 2")
        self.assertEqual(places.names("CP 1"), "CP 1")        # a test's own place name
        self.assertEqual(places.ids("CP 1"), "CP 1")

    def test_readers_see_names(self):
        rows = devices.load()
        self.assertIn("Barn;Engine House", {r["cp"] for r in rows})
        self.assertFalse([r for r in rows if r["cp"].startswith(("st:", "cp:"))])
        masts = level_masts.read()
        self.assertIn("CP 107", {r["cp"] for r in masts})
        self.assertFalse([r for r in masts if r["cp"].startswith(("st:", "cp:"))])

    def test_the_master_writes_ids(self):
        text = devices.master_text([dict(dict.fromkeys(devices.COLUMNS, ""), cp="Barn;CP 107")])
        self.assertIn("st:barn;cp:107", text)

    def test_a_bad_id_column_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "stations.csv"
            bad.write_text("station_id,level,station\nBarn,1,Barn\n", encoding="utf-8")
            with self.assertRaises(FactsError):
                places._table(bad.read_bytes(), places.INTERLOCKINGS.read_bytes())
            bad.write_text("station_id,level,station\nst:a,1,A\nst:a,1,B\n", encoding="utf-8")
            with self.assertRaises(FactsError):
                places._table(bad.read_bytes(), places.INTERLOCKINGS.read_bytes())


class OccupancyBindingsTest(unittest.TestCase):
    def test_every_block_id_is_named(self):
        rows = occupancy_bindings.rows()
        self.assertEqual(len(rows), 45)
        names = track_names.names_by_id([r["block_id"] for r in rows])
        self.assertEqual({r["block_id"]: r["block_user_name"] for r in rows}, names)
        self.assertIn("Track W-1", names.values())

    def test_a_bad_file_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "occupancy_bindings.csv"
            p.write_text("block_user_name,occupancy_sensor_user_name,cats_discipline\nTrack W-1,BS W-1,CTC\n")
            with self.assertRaises(FactsError):
                occupancy_bindings.rows(p)
            p.write_text("block_id,occupancy_sensor_user_name,cats_discipline\nblock:nowhere,BS X,CTC\n")
            with self.assertRaises(FactsError):
                occupancy_bindings.rows(p)
            p.write_text("block_id,occupancy_sensor_user_name,cats_discipline\nos:1,a,CTC\nos:1,b,CTC\n")
            with self.assertRaises(FactsError):
                occupancy_bindings.rows(p)


if __name__ == "__main__":
    unittest.main()
