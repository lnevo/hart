"""wiring_sheet.py: how the wiring viewer reads one inventory sheet's cells (tables, notes, port ids, pin kinds)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wiring_sheet as WS  # noqa: E402


class Tables(unittest.TestCase):
    def test_rows_under_the_header_are_keyed_by_it(self) -> None:
        rows = [["Node ID", "Address", ""], ["C1", "0x01", "x"], ["", ""], ["C2"]]
        self.assertEqual(WS.table(rows, 0), [{"Node ID": "C1", "Address": "0x01"}, {"Node ID": "C2", "Address": ""}])

    def test_stop_ends_the_table(self) -> None:
        rows = [["a"], ["1"], ["mast_user_name"], ["2"]]
        self.assertEqual(WS.table(rows, 0, stop=lambda r: r[0] == "mast_user_name"), [{"a": "1"}])


class Cells(unittest.TestCase):
    def test_rename_history_is_dropped(self) -> None:
        self.assertEqual(WS.strip_history("Main lamp (was S3-6 G); was C1-OU1-2 | renamed for linear6"), "Main lamp")
        self.assertEqual(WS.strip_history("Route A | Route B"), "Route A; Route B")

    def test_version_and_lists(self) -> None:
        self.assertEqual(WS.version_of(Path("LCOS_Layout_Inventory_v86.xlsx")), "v86")
        self.assertEqual(WS.version_of(Path("inventory.xlsx")), "inventory")
        self.assertEqual(WS.split_list(" Switch 1, ,Switch 3 "), ["Switch 1", "Switch 3"])
        self.assertEqual(WS.split_list(""), [])


class Ports(unittest.TestCase):
    def test_a_port_id_gives_node_board_and_pin(self) -> None:
        self.assertEqual(WS.parse_port("C13-OU2-5"), ("C13", "OU2", 5))
        self.assertEqual(WS.parse_port("M2-B1-2"), ("M2", "B1", 2))
        self.assertIsNone(WS.parse_port("C13-OU2"))

    def test_nodes_sort_m_c_d_then_others_and_boards_by_number(self) -> None:
        self.assertEqual(sorted(["X1", "D1", "C10", "C2", "M1", "?"], key=WS.node_sort), ["M1", "C2", "C10", "D1", "X1", "?"])
        self.assertEqual(sorted(["OU10", "IN1", "OU2"], key=WS.board_sort), ["IN1", "OU2", "OU10"])


class Kinds(unittest.TestCase):
    def test_input_kinds_by_device_type(self) -> None:
        self.assertEqual(WS.in_kind("Switch 3 N FB", "Feedback"), "feedback")
        self.assertEqual(WS.in_kind("Switch 3 BTN", "Push button"), "button")
        self.assertEqual(WS.in_kind("", ""), "spare")
        self.assertEqual(WS.in_kind("Sensor", "Sensor"), "other")

    def test_output_kinds_relay_and_cal(self) -> None:
        self.assertEqual(WS.out_kind("Relay 1", "Relay"), WS.OutKind("relay"))
        self.assertEqual(WS.out_kind("CAL", "Calibration"), WS.OutKind("cal"))
        self.assertEqual(WS.out_kind("Lamp", "Panel lamp"), WS.OutKind("other"))

    def test_a_board_is_placed_where_most_specific_pins_are(self) -> None:
        self.assertEqual(WS.pick_location(["Fascia (east)", "Fascia", "Fascia (east)", ""]), "Fascia (east)")
        self.assertEqual(WS.pick_location(["Fascia", "Shelf", "Fascia"]), "Fascia")
        self.assertEqual(WS.pick_location(["", ""]), "")


if __name__ == "__main__":
    unittest.main()
