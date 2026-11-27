"""device_map_master.py: the device-map rows in the master's form, and the checks that hold them to the drawing
and the name grammar (no plugin; files in a temporary folder)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[2] / "tools/hartlib/src")]
import device_map_master as master  # noqa: E402
import device_map_plant as plant  # noqa: E402
import device_map_records as rec  # noqa: E402
from hartlib import block_numbering, devices  # noqa: E402
from map_error import MapError  # noqa: E402


def device_rows() -> list[rec.DeviceMapRow]:
    """A virtual mast's and a helix block's device-map rows, as the row makers give them."""
    blank = rec.MapBuild(*[None] * len(rec.MapBuild._fields))
    st = blank._replace(rows=[], block_ids={})
    plant.add(st, 2, "", "mast", "Mast 2001", role="hidden", ident="mast:v", system="IF$vsm:basic:one-low($2001)",
              jmri="IF$vsm:basic:one-low($2001)", comment="Yard | buffer stop", facing="Track 201 Spur", dir="east")
    plant.add(st, 3, "", "block", "Track Helix Outer", role="helix", ident="block:h", trial="e1", notes="900 cm")
    return st.rows


class MasterForm(unittest.TestCase):
    def test_master_rows_are_text_written_by_the_builder(self):
        mast, block = master.master_rows(device_rows())
        self.assertEqual(set(mast), set(devices.COLUMNS))
        self.assertEqual((mast["level"], mast["written_by"], mast["assignment"], mast["id"], mast["role"]),
                         ("2", master.WRITER, "virtual", "mast:v", "hidden"))
        self.assertEqual((block["level"], block["user_name"]), ("3", "Track Helix Outer"))

    def test_a_missing_field_file_stops_naming_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = devices.Files.under(Path(tmp))
            with self.assertRaisesRegex(devices.DevicesError, f"{files.field.name}: cannot read it"):
                master.owned_rows(device_rows(), [], files)

    def test_a_helix_block_and_a_staging_block_are_not_numbered(self):
        row = {"layer": "block", "level": "2", "role": "track"}
        self.assertTrue(master.is_numbered(row))
        for change in ({"layer": "occupancy"}, {"level": "1"}, {"role": "helix"}):
            with self.subTest(change=change):
                self.assertFalse(master.is_numbered({**row, **change}))

    def test_a_numbering_problem_is_a_map_error(self):
        row = {c: "" for c in devices.COLUMNS} | {"layer": "block", "level": "2", "role": "track", "id": "block:x",
                                                 "user_name": "Track 1-3"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / block_numbering.PATH.name
            path.write_text("not,the,header\n", encoding="utf-8")
            with self.assertRaises(MapError) as stop:
                master.block_beans([row], path)
        self.assertIsInstance(stop.exception.__cause__, block_numbering.NumberingError)


class Checks(unittest.TestCase):
    def test_every_staging_switch_id_names_a_drawn_switch(self):
        rows = [{"layer": "block", "id": "os:9"}, {"layer": "block", "id": "os:23:A"}, {"layer": "block", "id": "block:x"},
                {"layer": "turnout", "id": "switch:9"}, {"layer": "turnout", "id": "dcc:23"}, {"layer": "fb", "id": "fb:9:N"}]
        master.check_switch_ids(rows)
        with self.assertRaisesRegex(MapError, "staging device IDs fb:11:R, switch:11 name a switch the plan does not draw"):
            master.check_switch_ids(rows + [{"layer": "turnout", "id": "switch:11"}, {"layer": "fb", "id": "fb:11:R"}])

    def test_a_switch_whose_main_route_is_leg_c_starts_thrown(self):
        def switch(label, main_leg):
            return {"kind": "switch", "label": label, "ins": {}, "outs": {"B": f"{label}b", "C": f"{label}c"},
                    "main": main_leg}

        def band(*switches):
            strands = {f"{d['label']}{leg.lower()}": {"main": d["main"] == leg} for d in switches for leg in "BC"}
            nodes = {d["label"]: d for d in switches} | {"x": {"kind": "dx", "label": "225"}}
            return {"nodes": nodes, "strands": strands}

        bands = [("Staging level", band(switch("9", "C")), {"level": 1}), ("Main level", band(switch("227A", "C"), switch("201", "B")), {"level": 2})]
        self.assertEqual(master.startup_thrown(bands), frozenset({"227"}))


if __name__ == "__main__":
    unittest.main()
