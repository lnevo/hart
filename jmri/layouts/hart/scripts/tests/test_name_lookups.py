"""Names that scripts used to type by hand and now look up from the data.

- speedmatch/analyze.py: each route is a running order of blocks; the sensors come from the
  blocks' occupancy sensors in tables.xml.
- infer_block_lengths.py: the lap reference is loop1's first block.
- audit_panel_contracts.py: the Dispatcher virtual masts are the boundary masts whose
  name-map hardware is virtual.
- validate_le_signalling.py: the CATS oracle pairs are read from data/sml_cats_oracle.csv.
"""
from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[3]
DATA = REPO / "jmri/layouts/hart/data"
sys.path.insert(0, str(SCRIPTS / "speedmatch"))
sys.path.insert(0, str(SCRIPTS))
import analyze  # noqa: E402


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MINI = """<layout-config><blocks>
  <block systemName="IB1"><systemName>IB1</systemName><userName>Track A</userName></block>
  <block systemName="IB1"><systemName>IB1</systemName><userName>Track A</userName>
    <occupancysensor>BS A</occupancysensor></block>
  <block systemName="IB2"><systemName>IB2</systemName><userName>OS Switch 2</userName>
    <occupancysensor>BS Switch 2 / BS A2</occupancysensor></block>
  <block systemName="IB3"><systemName>IB3</systemName><userName>Track No Sensor</userName></block>
</blocks></layout-config>"""


class RouteLookupTest(unittest.TestCase):
    def test_sensors_come_from_the_full_block(self):
        root = ET.fromstring(MINI)
        sensors = analyze.block_sensors(root)
        self.assertEqual({"Track A": "BS A", "OS Switch 2": "BS Switch 2 / BS A2"}, sensors)
        self.assertEqual([("BS Switch 2 / BS A2", "OS Switch 2"), ("BS A", "Track A")],
                         analyze.route_pairs(["OS Switch 2", "Track A"], sensors))

    def test_a_block_without_a_sensor_stops_with_its_name(self):
        sensors = analyze.block_sensors(ET.fromstring(MINI))
        with self.assertRaises(SystemExit) as cm:
            analyze.route_pairs(["Track A", "Track No Sensor", "Track Gone"], sensors)
        self.assertIn("Track No Sensor, Track Gone", str(cm.exception))

    def test_routes_follow_their_running_order(self):
        for route, blocks in analyze.ROUTE_BLOCKS.items():
            with self.subTest(route):
                self.assertEqual(blocks, [b for _, b in analyze.ROUTES[route]])
                self.assertEqual(analyze.ROUTES[route][0][0], analyze.route_loop(route)[0][0])
        self.assertEqual([s for s, _ in analyze.LOOP], analyze.ORDER)
        sensors = dict((b, s) for s, b in analyze.LOOP + analyze.LOOP2)
        for route, block in analyze.ROUTE_MID_BLOCK.items():
            self.assertEqual(sensors[block], analyze.ROUTE_MID[route])

    def test_lap_reference_is_loop1s_first_block(self):
        infer = load("infer_block_lengths")
        self.assertEqual(analyze.LOOP[0][0].removeprefix("BS "), infer.REF_BLOCK)
        self.assertEqual(infer.REF_BLOCK, infer.route_ref("loop1"))


class DispatcherVirtualsTest(unittest.TestCase):
    def test_virtual_boundary_masts_are_the_dispatcher_ones(self):
        audit = load("audit_panel_contracts")
        with tempfile.TemporaryDirectory() as tmp:
            nm = Path(tmp) / "map.csv"
            with nm.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["layer", "current", "proposed", "cp", "hardware", "dcc", "comment", "notes"])
                w.writerow(["mast", "Mast 1A", "Mast 1A", "", "virtual $1001", "", "", ""])
                w.writerow(["mast", "Mast 1B", "Mast 1B", "", "IH100", "", "", ""])
                w.writerow(["mast", "Old 1C", "Mast 1C", "", "virtual $1002", "", "", "alias"])
                w.writerow(["mast", "Mast 9Z", "Mast 9Z", "", "virtual $1009", "", "", "not a boundary"])
            self.assertEqual({"Mast 1A"},
                             audit.dispatcher_virtuals({"Mast 1A", "Mast 1B", "Mast 1C"}, nm))

    def test_repo_has_nine_dispatcher_virtuals(self):
        audit = load("audit_panel_contracts")
        with (DATA / "le_signal_boundaries.csv").open(newline="", encoding="utf-8") as f:
            boundary = {r["mast_user_name"] for r in csv.DictReader(f)}
        self.assertEqual(9, len(audit.dispatcher_virtuals(boundary)))


class OracleTest(unittest.TestCase):
    def test_oracle_rows_parse_into_lists(self):
        val = load("validate_le_signalling")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "o.csv"
            p.write_text("source,dest,blocks,turnouts\n"
                         "Mast 1A,Mast 2A,Track A | OS Switch 2,Switch 2=closed | Switch 4=thrown\n"
                         "Mast 2A,Mast 1A,,\n", encoding="utf-8")
            self.assertEqual(
                [("Mast 1A", "Mast 2A", ["Track A", "OS Switch 2"], [("Switch 2", "closed"), ("Switch 4", "thrown")]),
                 ("Mast 2A", "Mast 1A", [], [])],
                val.load_oracle(p))

    def test_repo_oracle_has_its_33_pairs(self):
        pairs = load("validate_le_signalling").load_oracle()
        self.assertEqual(33, len(pairs))
        self.assertTrue(all(state in ("closed", "thrown") for *_, ts in pairs for _, state in ts))


if __name__ == "__main__":
    unittest.main()
