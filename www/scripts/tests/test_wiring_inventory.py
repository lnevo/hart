"""wiring_inventory.py: Inventory reads small inventory sheets into the viewer's records and warns where they disagree.

The sheets here are made in the test; the real model's build is tested in test_wiring_json_check.py.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wiring_inventory as WI  # noqa: E402

NODES = [["Node ID", "Address", "Location", "Type", "DNOU8", "DNIN8", "Signal Names"],
         ["C1", "0x01", "Fascia", "LCOS", "OU1", "IN1, IN2", "12 upper"]]
DNOU8 = [["Output Port ID", "Parent Node ID", "Connected Device", "Device Type", "Voltage Rail (12V/5V)",
          "Board Location", "Notes"],
         ["C1-OU1-1", "C1", "Switch 3 N", "Turnout motor", "12V", "Fascia (east)", "renamed for linear6"],
         ["C1-OU1-2", "C1", "Head 12 upper R", "Signal lamp", "12V", "", "CP1 | A → B"],
         ["C1-OU1-2", "C1", "Switch 3 R", "Turnout motor", "12V", "", ""],
         ["C9-OU1-1", "C1", "", "", "5V", "", ""]]
DNIN8 = [["Input Port ID", "Connected Device", "Device Type (Sensor/Switch/etc.)", "Board Location", "Notes"],
         ["C1-IN1-1", "Switch 3 BTN", "Button", "Fascia", ""]]


def inventory(**sheets: list[list[str]]) -> WI.Inventory:
    return WI.Inventory({"Nodes": NODES, "DNOU8": DNOU8, "DNIN8": DNIN8, **sheets}, "test_v7.xlsx", WI.BuildLog())


class Boards(unittest.TestCase):
    def setUp(self) -> None:
        self.inv = inventory()
        self.inv.read_nodes()
        self.inv.read_outputs()
        self.inv.read_inputs()

    def test_pins_go_onto_their_node_s_boards(self) -> None:
        c1 = self.inv.nodes["C1"]
        self.assertEqual([b["board"] for b in c1["outputs"]], ["OU1"])
        self.assertEqual(c1["outputs"][0]["rail"], "12V")
        self.assertEqual(c1["outputs"][0]["place"], "Fascia (east)")
        motor, lamp = c1["outputs"][0]["pins"]
        self.assertEqual((motor["kind"], "note" in motor), ("motor", False))    # rename history is not published
        self.assertEqual((lamp["kind"], lamp["head"], lamp["color"]), ("lamp", "12 upper", "R"))
        self.assertEqual(dict(self.inv.device_ports), {"Switch 3 N": ["C1-OU1-1"], "Head 12 upper R": ["C1-OU1-2"]})

    def test_disagreements_are_warnings(self) -> None:
        self.assertEqual(self.inv.log.warnings, [
            "DNOU8: port C1-OU1-2 listed twice",
            "DNOU8: C9-OU1-1 has Parent Node C1",
            "DNOU8: C1-OU1 has no row for pin(s) [3, 4, 5, 6, 7, 8]",
            "DNOU8: C9-OU1 has no row for pin(s) [2, 3, 4, 5, 6, 7, 8]",
            "DNOU8: C9-OU1 names node C9, which is not on the Nodes sheet",
            "DNIN8: C1-IN1 has no row for pin(s) [2, 3, 4, 5, 6, 7, 8]",
        ])

    def test_declared_boards_are_compared_then_dropped(self) -> None:
        self.inv.check_declared_boards()
        self.assertIn("Nodes: C1 declares DNIN8 ['IN1', 'IN2'] but the DNIN8 sheet has ['IN1']", self.inv.log.warnings)
        self.assertNotIn("declared", self.inv.nodes["C1"])

    def test_data_drops_the_working_fields(self) -> None:
        data = self.inv.data()
        self.assertEqual(data["source"], {"file": "test_v7.xlsx", "version": "v7"})
        pins = data["nodes"][0]["outputs"][0]["pins"]
        self.assertFalse(any("_note" in p for p in pins))
        self.assertTrue(all("_locs" not in b for b in self.inv.out_boards.values()))


class Signals(unittest.TestCase):
    def test_a_digicon_sheet_with_no_header_is_an_error(self) -> None:
        inv = inventory(DigiconSignals=[["something else"]])
        with self.assertRaisesRegex(WI.WiringDataError, "test_v7.xlsx: the DigiconSignals sheet has no port_id"):
            inv.digicon_tables()

    def test_an_led_head_takes_its_cp_and_route_from_its_note(self) -> None:
        inv = inventory()
        inv.read_nodes()
        inv.read_outputs()
        inv.read_led_heads()
        head = inv.heads["12 upper"]
        self.assertEqual((head["type"], head["cp"], head["route"], head["lamps"]),
                         ("RGB LED", "CP1", "A → B", {"R": "C1-OU1-2"}))
        self.assertIn("Signals: head 12 upper has no Y/G pin", inv.log.warnings)


class Log(unittest.TestCase):
    def test_two_logs_with_the_same_findings_are_equal(self) -> None:
        a, b = WI.BuildLog(), WI.BuildLog()
        a.warn("x")
        self.assertNotEqual(a, b)
        b.warn("x")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
