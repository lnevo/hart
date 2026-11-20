"""Occupancy lamps are display only: a click on a panel lamp must never set a block occupied (owner, 2026-11-15)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
ROOT = next(p for p in HERE.parents if (p / "tools/hartlib/src").is_dir())
sys.path.insert(0, str(SCRIPTS))


def script_path(name):
    """The script's file: in scripts/, or in parked/ for the ones moved there."""
    here = SCRIPTS / f"{name}.py"
    return here if here.is_file() else SCRIPTS.parent / "parked" / f"{name}.py"


def load(name):
    spec = importlib.util.spec_from_file_location(name, script_path(name))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod                      # dataclasses look their module up while the class is built
    spec.loader.exec_module(mod)
    return mod


OL = load("occupancy_lamps_display_only")


class Fix(unittest.TestCase):
    def test_block_sensor_lamps_turn_display_only_and_nothing_else_changes(self):
        text = ('<a><sensoricon sensor="BS Switch 15" x="1" forcecontroloff="false" icon="yes">\n'
                '<sensoricon sensor="IS1:LEVER" x="2" forcecontroloff="false" icon="yes">\n'
                '<sensoricon sensor="BS S-1" x="3" icon="yes">\n'
                '<sensoricon sensor="BS EH-1" forcecontroloff="true" x="4"></a>')
        new, changed = OL.fix(text)
        self.assertEqual(changed, 2)
        self.assertIn('sensor="BS Switch 15" x="1" forcecontroloff="true"', new)
        self.assertIn('sensor="IS1:LEVER" x="2" forcecontroloff="false"', new)       # a lever stays clickable
        self.assertIn('<sensoricon forcecontroloff="true" sensor="BS S-1"', new)
        self.assertEqual(OL.fix(new), (new, 0))

    def test_lamps_inside_the_frozen_overlay_json_are_fixed_too(self):
        text = '{"xml": "<sensoricon sensor=\\"BS K-1\\" x=\\"1\\" forcecontroloff=\\"false\\" icon=\\"yes\\">"}'
        new, changed = OL.fix(text, escaped=True)
        self.assertEqual(changed, 1)
        self.assertIn('forcecontroloff=\\"true\\"', new)
        import json
        self.assertIn('forcecontroloff="true"', json.loads(new)["xml"])

    def test_committed_tables_have_no_clickable_lamp(self):
        self.assertEqual(OL.main(["--check"]), 0)


class Rules(unittest.TestCase):
    def test_circuit_lamps_count_whatever_their_sensor(self):
        text = ('<sensoricon sensor="MoveInProgressTrack_K-1" forcecontroloff="false"><active url="x/circuit-occupied.gif"/>'
                '</sensoricon><sensoricon sensor="MoveTo_K-1" forcecontroloff="false"><active url="x/button.gif"/></sensoricon>')
        new, changed = OL.fix(text)
        self.assertEqual(changed, 1)
        self.assertIn('sensor="MoveInProgressTrack_K-1" forcecontroloff="true"', new)
        self.assertIn('sensor="MoveTo_K-1" forcecontroloff="false"', new)           # the button stays clickable

    def test_missing_tables_fails_the_check(self):
        self.assertEqual(OL.main(["--check", "--tables", "/no/such/tables.xml"]), 2)


class Generators(unittest.TestCase):
    def test_polish_puts_an_existing_clickable_lamp_right(self):
        import xml.etree.ElementTree as ET
        polish = load("polish_hart_layout_editor")
        le = ET.fromstring('<LayoutEditor><sensoricon sensor="BS Switch 15" forcecontroloff="false"/>'
                           '<sensoricon sensor="IS1:LEVER" forcecontroloff="false"/></LayoutEditor>')
        self.assertEqual(len(polish.lamps_display_only(le, check=True)[1]), 1)
        self.assertEqual(polish.lamps_display_only(le, check=False)[0], 1)
        self.assertEqual([i.get("forcecontroloff") for i in le], ["true", "false"])

    def test_dispatcher_station_lamps_take_no_click_but_move_to_does(self):
        stations = load("reconcile_dispatcher_stations")
        for kind, want in (("occupancy", "true"), ("progress", "true"), ("move_to", "false")):
            self.assertEqual(stations.icon_element("S", "K-1", 0, 0, kind).get("forcecontroloff"), want, kind)

    def test_polish_writes_display_only_os_lamps(self):
        polish = load("polish_hart_layout_editor")
        self.assertEqual(polish._circuit_occupancy_icon("BS Switch 15", 0, 0).get("forcecontroloff"), "true")

    def test_uss_ctc_jewels_are_display_only(self):
        ctc = load("gen_ctc_track_plan")
        self.assertIn('forcecontroloff="true"', ctc.LAMP)


if __name__ == "__main__":
    unittest.main()
