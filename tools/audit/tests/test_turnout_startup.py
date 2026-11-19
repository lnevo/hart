"""The main and upper virtual turnouts' startup positions: build_layout_le.startup_thrown picks the switches whose main
route runs through the diverging leg, le_tables.add_level_clear writes an ActionTurnout per turnout into the startup
LogixNG, and hartlib.level_devices reads them back and refuses anything else (owner, 2026-11-19)."""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
import le_tables as T  # noqa: E402
from hartlib import level_devices as L  # noqa: E402

SENSORS = [L.SENSOR_PREFIX + "107-109", L.SENSOR_PREFIX + "OS225a"]


def tables_root() -> ET.Element:
    root = ET.Element("layout-config")
    for tag in ("LogixNGs", "LogixNGConditionalNGs", "LogixNGDigitalActions"):
        ET.SubElement(root, tag)
    return root


class StartupActions(unittest.TestCase):
    def test_round_trip(self):
        root = tables_root()
        want = {L.TURNOUT_PREFIX + "109": "Closed", L.TURNOUT_PREFIX + "227": "Thrown"}
        T.add_level_clear(root, SENSORS, want)
        self.assertEqual(L.turnout_states(root), want)
        self.assertEqual(L.clear_sensors(root), sorted(SENSORS))       # the turnout actions do not break the reader

    def test_a_state_other_than_closed_or_thrown_stops_the_build(self):
        with self.assertRaises(T.BuildError):
            T.add_level_clear(tables_root(), SENSORS, {L.TURNOUT_PREFIX + "109": "Toggle"})

    def test_a_toggle_or_a_field_turnout_is_refused_on_read(self):
        for turnout, state in ((L.TURNOUT_PREFIX + "109", "Toggle"), ("MT408", "Closed")):
            root = tables_root()
            T.add_level_clear(root, SENSORS, {L.TURNOUT_PREFIX + "109": "Closed"})
            act = next(a for a in root.find("LogixNGDigitalActions") if a.tag == "ActionTurnout")
            act.find("namedBean/name").text = turnout
            act.find("state/enum").text = state
            with self.subTest(turnout=turnout, state=state):
                with self.assertRaises(ValueError):
                    L.turnout_states(root)
                with self.assertRaises(ValueError):
                    L.clear_sensors(root)


class StartupThrown(unittest.TestCase):
    def test_227_and_229_line_the_peninsula_loop(self):
        import build_device_map as bdm
        import build_layout_le as bl
        try:
            bands, _joined, _runs, _corners = bdm.solve()
        except Exception as exc:        # the schematic-maps plugin is not checked out here
            self.skipTest(f"no schematic: {exc}")
        self.assertEqual(bl.startup_thrown(bands), {"Switch 227", "Switch 229"})


if __name__ == "__main__":
    unittest.main()
