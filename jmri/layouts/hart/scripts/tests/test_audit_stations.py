"""audit_panel_contracts.audit_stations: the stations' block comments, and one MoveTo and one move-in-progress sensor
and icon per station (none while the Dispatcher System is parked). Built from small XML roots; the station list is
passed in through a patched station_comments."""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_panel_contracts as apc  # noqa: E402

STATIONS = {"Track A": "a; stop", "Track B": "b; stop"}


def tables(blocks, sensors):
    root = ET.Element("layout-config")
    b = ET.SubElement(root, "blocks")
    for name, comment in blocks:
        block = ET.SubElement(b, "block")
        ET.SubElement(block, "userName").text = name
        ET.SubElement(block, "comment").text = comment
    s = ET.SubElement(root, "sensors")
    for name in sensors:
        ET.SubElement(ET.SubElement(s, "sensor"), "userName").text = name
    return root


def panel(icons):
    p = ET.Element("LayoutEditor", name="HART")
    for name in icons:
        ET.SubElement(p, "sensoricon", sensor=name)
    return p


def pair(key):
    return [f"MoveTo{key}_stored", f"MoveInProgress{key}"]


def run(root, lay, *, parked=frozenset(), required=True):
    audit = apc.Audit("test", Path("tables.xml"))
    with mock.patch.object(apc, "station_comments", return_value=dict(STATIONS)), \
            mock.patch.object(apc.parked, "parked_in", return_value=parked):
        apc.audit_stations(root, lay, audit, required=required)
    return audit


class Stations(unittest.TestCase):
    def test_complete_stations_pass_and_are_recorded(self):
        names = pair("Track_A") + pair("Track_B")
        audit = run(tables([("Track A", "a; stop"), ("Track B", "b; stop")], names), panel(names))
        self.assertEqual((audit.errors, audit.warnings), ([], []))
        self.assertEqual(audit.facts["stations"], (("Track A", "a; stop"), ("Track B", "b; stop")))
        self.assertEqual(audit.facts["station_sensors"], tuple(sorted(names)))
        self.assertEqual(audit.facts["station_icons"], tuple(sorted(names)))

    def test_each_kind_of_problem_is_named_in_order(self):
        sensors = pair("Track_A") + ["MoveInProgressTrack_A", "Other sensor"]
        icons = pair("Track_A") + ["MoveToTrack_C_stored"]
        root = tables([("Track A", "a; stop"), ("Track B", "b"), ("Track C", "c; stop")], sensors)
        audit = run(root, panel(icons))
        self.assertEqual(audit.errors, [
            "Dispatcher station block names differ; missing=['Track B'], extra=['Track C']",
            "Dispatcher station 'Track B': expected block comment 'b; stop', found ['b']",
            "Dispatcher station sensor pairs differ; missing=['MoveInProgressTrack_B', 'MoveToTrack_B_stored'], "
            "extra=none, duplicates=['MoveInProgressTrack_A']",
            "Dispatcher station sensor icons are not exactly one paired icon per station; "
            "missing=['MoveInProgressTrack_B', 'MoveToTrack_B_stored'], extra=['MoveToTrack_C_stored'], "
            "duplicates=none",
        ])
        self.assertEqual(audit.facts["stations"], (("Track A", "a; stop"), ("Track B", "")))
        self.assertEqual(audit.facts["station_sensors"], ("MoveInProgressTrack_A", "MoveToTrack_A_stored"))

    def test_not_required_gives_warnings(self):
        audit = run(tables([], []), None, required=False)
        self.assertEqual(audit.errors, [])
        self.assertEqual(len(audit.warnings), 5)       # names, two comments, sensors, icons
        self.assertEqual(audit.facts["station_icons"], ())

    def test_parked_dispatcher_wants_no_sensor_or_icon(self):
        root = tables([("Track A", "a; stop"), ("Track B", "b; stop")], pair("Track_A"))
        audit = run(root, panel([]), parked=frozenset({"dispatcher"}))
        self.assertEqual(audit.errors, [
            "Dispatcher station sensor pairs differ; missing=none, "
            "extra=['MoveInProgressTrack_A', 'MoveToTrack_A_stored'], duplicates=none",
        ])


if __name__ == "__main__":
    unittest.main()
