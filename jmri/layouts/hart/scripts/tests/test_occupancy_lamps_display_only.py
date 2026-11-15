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


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
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


class Generators(unittest.TestCase):
    def test_polish_writes_display_only_os_lamps(self):
        polish = load("polish_hart_layout_editor")
        self.assertEqual(polish._circuit_occupancy_icon("BS Switch 15", 0, 0).get("forcecontroloff"), "true")

    def test_uss_ctc_jewels_are_display_only(self):
        ctc = load("gen_ctc_track_plan")
        self.assertIn('forcecontroloff="true"', ctc.LAMP)


if __name__ == "__main__":
    unittest.main()
