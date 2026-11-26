"""Names that scripts used to type by hand and now look up from the data.

- speedmatch/analyze.py: each route is a running order of blocks by staging device ID; build_routes.py
  writes the blocks' names from the name store and their occupancy sensors from tables.xml into
  routes.json, which analyze.py reads.
- infer_block_lengths.py: the lap reference is loop1's first block.
- audit_panel_contracts.py: the Dispatcher virtual masts are staging's hidden masts
  (role hidden) in devices.csv.
"""
from __future__ import annotations

import csv
import importlib.util
import json
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
import build_routes  # noqa: E402
from hartlib import devices  # noqa: E402


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


# the name store's answer for MINI's blocks ({(level, id): user name}, as hartlib.devices.user_names gives it)
NAMES = {("1", "block:A"): "Track A", ("1", "os:2"): "OS Switch 2", ("1", "block:NS"): "Track No Sensor",
         ("1", "block:G"): "Track Gone"}


class RouteLookupTest(unittest.TestCase):
    def test_sensors_come_from_the_full_block(self):
        root = ET.fromstring(MINI)
        sensors = build_routes.block_sensors(root)
        self.assertEqual({"Track A": "BS A", "OS Switch 2": "BS Switch 2 / BS A2"}, sensors)
        data = build_routes.build(root, {"r": ["os:2", "block:A"]}, {"r": "block:A"}, NAMES)
        self.assertEqual([["BS Switch 2 / BS A2", "OS Switch 2"], ["BS A", "Track A"]], data["routes"]["r"])
        self.assertEqual({"r": ["os:2", "block:A"]}, data["ids"])
        self.assertEqual({"r": "BS A"}, data["mid"])

    def test_a_block_without_a_sensor_stops_with_its_name(self):
        with self.assertRaises(SystemExit) as cm:
            build_routes.build(ET.fromstring(MINI), {"r": ["block:A", "block:NS", "block:G"]}, {"r": "block:A"},
                               NAMES)
        self.assertIn("Track Gone, Track No Sensor", str(cm.exception))

    def test_an_id_the_device_master_lacks_stops_with_the_id(self):
        with self.assertRaises(SystemExit) as cm:
            build_routes.build(ET.fromstring(MINI), {"r": ["block:A", "block:X"]}, {"r": "block:A"}, NAMES)
        self.assertIn("block:X", str(cm.exception))
        with self.assertRaises(SystemExit) as cm:       # a main level block of the same id is not staging's
            build_routes.build(ET.fromstring(MINI), {"r": ["block:A"]}, {"r": "block:A"}, {("2", "block:A"): "A"})
        self.assertIn("block:A", str(cm.exception))

    def test_a_rename_in_the_name_store_reaches_the_routes(self):
        """naming-layers step 6: the routes are typed by ID, so an owner's new name for a block (devices_field.csv,
        here the name store's answer) changes the name and sensor build_routes writes, and no line of analyze.py."""
        root = ET.fromstring(MINI.replace("Track A<", "Track Renamed<"))
        data = build_routes.build(root, {"r": ["block:A"]}, {"r": "block:A"}, {**NAMES, ("1", "block:A"): "Track Renamed"})
        self.assertEqual([["BS A", "Track Renamed"]], data["routes"]["r"])
        self.assertEqual({"r": ["block:A"]}, data["ids"])

    def test_routes_json_is_current_and_matches_the_typed_order(self):
        self.assertEqual(0, build_routes.main(["--check"]))
        order, mid = build_routes.route_order()
        self.assertEqual(order, analyze.ROUTE_BLOCKS)
        self.assertEqual(mid, analyze.ROUTE_MID_BLOCK)
        names = devices.user_names()
        for route, blocks in analyze.ROUTE_BLOCKS.items():
            with self.subTest(route):
                self.assertEqual([names[("1", b)] for b in blocks], [b for _, b in analyze.ROUTES[route]])
        self.assertEqual([s for s, _ in analyze.LOOP], analyze.ORDER)
        for route, block in analyze.ROUTE_MID_BLOCK.items():
            sensors = dict(zip(analyze.ROUTE_BLOCKS[route], (s for s, _ in analyze.ROUTES[route])))
            self.assertEqual(sensors[block], analyze.ROUTE_MID[route])

    def test_a_routes_json_out_of_step_with_the_order_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "routes.json"
            p.write_text(json.dumps({"routes": {"r": [["BS A", "Track A"]]}, "ids": {"r": ["block:A"]},
                                     "mid": {"r": "BS A"}}))
            routes, mid = analyze.load_routes(p, {"r": ["block:A"]}, {"r": "block:A"})
            self.assertEqual({"r": [("BS A", "Track A")]}, routes)
            for order, mid_block in (({"r": ["block:A", "block:B"]}, "block:A"),     # a block more
                                     ({"r": ["block:B"]}, "block:B"),                 # another block
                                     ({"r": ["block:A"]}, "block:B")):                # a mid block off the route
                with self.subTest(order=order, mid=mid_block), self.assertRaises(analyze.RoutesError) as cm:
                    analyze.load_routes(p, order, {"r": mid_block})
                self.assertIn("build_routes.py", str(cm.exception))
            p.write_text(json.dumps({"routes": {"r": [["BS A", "Track A"]]}, "mid": {"r": "BS A"}}))
            with self.assertRaises(analyze.RoutesError):        # a routes.json from before the ids
                analyze.load_routes(p, {"r": ["block:A"]}, {"r": "block:A"})

    def test_a_log_with_a_sensor_off_the_route_stops_and_names_it(self):
        good = analyze.LOOP[0][0]
        lines = ["1.0 RUN loco=CSX 1 direction=forward", "1.1 CFG route=loop1", "2.0 STEP 24",
                 f"3.0 SENS {good} ACTIVE", "4.0 SENS BS Renamed Block ACTIVE"]
        with self.assertRaises(analyze.LogError) as cm:
            analyze.parse_log(lines, source="old.log")
        self.assertIn("old.log logs sensor(s) not on route loop1: BS Renamed Block", str(cm.exception))
        self.assertEqual(1, len(analyze.parse_log(lines[:-1], source="ok.log")))

    def test_lap_reference_is_loop1s_first_block(self):
        infer = load("infer_block_lengths")
        self.assertEqual(analyze.LOOP[0][0].removeprefix("BS "), infer.REF_BLOCK)
        self.assertEqual(infer.REF_BLOCK, infer.route_ref("loop1"))


class DispatcherVirtualsTest(unittest.TestCase):
    def test_virtual_masts_are_the_dispatcher_ones(self):
        audit = load("audit_panel_contracts")
        with tempfile.TemporaryDirectory() as tmp:
            nm = Path(tmp) / devices.ONE_FILE                 # a master of four masts, two of them staging's hidden ones
            blank = dict.fromkeys(audit.devices.COLUMNS, "")

            def mast(user, role, n, level="1"):
                system = f"IF$vsm:basic:one-low(${n})" if role == "hidden" else f"IF$shsm:basic:one-low(IH{n})"
                return dict(blank, level=level, layer="mast", role=role, assignment="virtual", system_name=system,
                            jmri_name=system, written_by="build_device_map.py", description="A mast of the test.",
                            user_name=user, id=f"test:mast:{user}")
            rows = [mast("Mast 1A", "hidden", 1001), mast("Mast 1B", "home", 100), mast("Mast 1C", "hidden", 1002),
                    mast("Mast 9Z", "hidden", 2001, level="2")]          # a main level mast is no staging one
            nm.write_text(audit.devices.master_text(rows), encoding="utf-8")
            self.assertEqual({"Mast 1A", "Mast 1C"},
                             audit.dispatcher_virtuals({"Mast 1A", "Mast 1B", "Mast 1C", "Mast 9Z"}, nm))
            with self.assertRaisesRegex(audit.devices.DevicesError, "cannot read it"):
                audit.dispatcher_virtuals({"Mast 1A"}, Path(tmp) / "missing.csv")

    def test_repo_dispatcher_virtuals_are_the_staging_buffer_stop_masts(self):
        # Pinned on purpose: a mast or hardware change shows up here instead of moving silently. The virtual staging
        # masts (hidden, IF$vsm:) stand at buffer stops only (owner, 2026-11-20); masts.csv's staging rows name them.
        audit = load("audit_panel_contracts")
        with (DATA / "schematic" / "masts.csv").open(newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["level"] == "1"]
        virtual = {r["mast"] for r in rows if r["system_name"].startswith("IF$vsm:")}
        self.assertTrue(virtual)
        self.assertEqual(virtual, audit.dispatcher_virtuals({r["mast"] for r in rows}))


if __name__ == "__main__":
    unittest.main()
