"""Names that scripts used to type by hand and now look up from the data.

- speedmatch/analyze.py: each route is a running order of blocks; build_routes.py writes the
  blocks' occupancy sensors from tables.xml into routes.json, which analyze.py reads.
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
        sensors = build_routes.block_sensors(root)
        self.assertEqual({"Track A": "BS A", "OS Switch 2": "BS Switch 2 / BS A2"}, sensors)
        data = build_routes.build(root, {"r": ["OS Switch 2", "Track A"]}, {"r": "Track A"})
        self.assertEqual([["BS Switch 2 / BS A2", "OS Switch 2"], ["BS A", "Track A"]], data["routes"]["r"])
        self.assertEqual({"r": "BS A"}, data["mid"])

    def test_a_block_without_a_sensor_stops_with_its_name(self):
        with self.assertRaises(SystemExit) as cm:
            build_routes.build(ET.fromstring(MINI), {"r": ["Track A", "Track No Sensor", "Track Gone"]},
                               {"r": "Track A"})
        self.assertIn("Track Gone, Track No Sensor", str(cm.exception))

    def test_routes_json_is_current_and_matches_the_typed_order(self):
        self.assertEqual(0, build_routes.main(["--check"]))
        order, mid = build_routes.route_order()
        self.assertEqual(order, analyze.ROUTE_BLOCKS)
        self.assertEqual(mid, analyze.ROUTE_MID_BLOCK)
        for route, blocks in analyze.ROUTE_BLOCKS.items():
            with self.subTest(route):
                self.assertEqual(blocks, [b for _, b in analyze.ROUTES[route]])
        self.assertEqual([s for s, _ in analyze.LOOP], analyze.ORDER)
        sensors = dict((b, s) for s, b in analyze.LOOP + analyze.LOOP2)
        for route, block in analyze.ROUTE_MID_BLOCK.items():
            self.assertEqual(sensors[block], analyze.ROUTE_MID[route])

    def test_a_routes_json_out_of_step_with_the_order_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "routes.json"
            p.write_text(json.dumps({"routes": {"r": [["BS A", "Track A"]]}, "mid": {"r": "BS A"}}))
            routes, mid = analyze.load_routes(p, {"r": ["Track A"]}, {"r": "Track A"})
            self.assertEqual({"r": [("BS A", "Track A")]}, routes)
            with self.assertRaises(SystemExit) as cm:
                analyze.load_routes(p, {"r": ["Track A", "Track B"]}, {"r": "Track A"})
            self.assertIn("build_routes.py", str(cm.exception))

    def test_a_log_with_a_sensor_off_the_route_stops_and_names_it(self):
        good = analyze.LOOP[0][0]
        lines = ["1.0 RUN loco=CSX 1 direction=forward", "1.1 CFG route=loop1", "2.0 STEP 24",
                 f"3.0 SENS {good} ACTIVE", "4.0 SENS BS Renamed Block ACTIVE"]
        with self.assertRaises(SystemExit) as cm:
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
            nm = Path(tmp) / "devices.csv"                 # a master of four masts, two of them staging's hidden ones
            blank = dict.fromkeys(audit.devices.COLUMNS, "")

            def mast(user, role, n, level="1"):
                system = f"IF$vsm:basic:one-low(${n})" if role == "hidden" else f"IF$shsm:basic:one-low(IH{n})"
                return dict(blank, level=level, layer="mast", role=role, assignment="virtual", system_name=system,
                            jmri_name=system, written_by="build_masts.py", description="A mast of the test.",
                            user_name=user)
            rows = [mast("Mast 1A", "hidden", 1001), mast("Mast 1B", "home", 100), mast("Mast 1C", "hidden", 1002),
                    mast("Mast 9Z", "hidden", 2001, level="2")]          # a main level mast is no staging one
            nm.write_text(audit.devices.master_text(rows), encoding="utf-8")
            self.assertEqual({"Mast 1A", "Mast 1C"},
                             audit.dispatcher_virtuals({"Mast 1A", "Mast 1B", "Mast 1C", "Mast 9Z"}, nm))
            with self.assertRaisesRegex(audit.devices.DevicesError, "cannot read it"):
                audit.dispatcher_virtuals({"Mast 1A"}, Path(tmp) / "missing.csv")

    def test_repo_dispatcher_virtuals_are_the_staging_buffer_stop_masts(self):
        # Pinned on purpose: a mast or hardware change shows up here instead of moving silently. The virtual staging
        # masts (hidden, IF$vsm:) stand at buffer stops only (owner, 2026-11-20); staging_masts.csv names them.
        audit = load("audit_panel_contracts")
        with (DATA / "schematic" / "staging_masts.csv").open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        virtual = {r["mast"] for r in rows if r["system_name"].startswith("IF$vsm:")}
        self.assertTrue(virtual)
        self.assertEqual(virtual, audit.dispatcher_virtuals({r["mast"] for r in rows}))


if __name__ == "__main__":
    unittest.main()
