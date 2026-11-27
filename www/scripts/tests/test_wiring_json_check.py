"""build_wiring_json.py: the wiring viewer's JSON is built from the wiring model, never committed (ADR-036); its checks
fail a build that is empty or leaks a network detail, and a broken model is a named error, not a traceback."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_wiring_json", ROOT / "www/scripts/build_wiring_json.py")
assert SPEC is not None and SPEC.loader is not None, "www/scripts/build_wiring_json.py cannot be loaded"
BW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BW)

INV = BW.build().data  # built once for the tests that read the real model


def run_main(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "argv", ["build_wiring_json.py", *args]), redirect_stdout(out), redirect_stderr(err):
        code = BW.main()
    return code, out.getvalue(), err.getvalue()


class FromTheModel(unittest.TestCase):
    """The JSON is built from the wiring model (write_inventory.workbook(), in memory); v86 is an output only."""

    def test_it_builds_without_opening_any_workbook(self):
        never = mock.Mock(side_effect=AssertionError("a workbook file was opened"))
        with mock.patch("openpyxl.load_workbook", never), mock.patch("openpyxl.reader.excel.load_workbook", never), \
                mock.patch.object(BW.write_inventory, "load_workbook", never), \
                mock.patch.object(BW.write_inventory, "OUT", Path(tempfile.gettempdir()) / "no-such-v86.xlsx"):
            inv = BW.build_inventory().data
        never.assert_not_called()
        self.assertEqual(inv["source"], {"file": "LCOS_Layout_Inventory_v86.xlsx", "version": "v86"})

    def test_the_real_model_builds_and_passes_its_checks(self):
        self.assertEqual(BW.problems(INV), [])
        data = json.loads(BW.data_text(INV))
        for key in BW.REQUIRED:
            self.assertTrue(data[key], key)
        self.assertRegex(data["source"]["built"], r"^\d{4}-\d{2}-\d{2}$")

    def test_a_given_workbook_is_read_as_the_model_gives_it(self):
        wb = BW.write_inventory.workbook()
        wb["Nodes"].cell(2, 4, "Somewhere else")
        inv = BW.build_inventory(wb).data
        self.assertEqual(inv["nodes"][0]["location"], "Somewhere else")

    def test_each_build_reports_only_its_own_warnings(self):
        first = BW.build_inventory().log
        self.assertEqual(BW.build_inventory().log, first)

    def test_a_bad_row_is_a_warning_of_that_build(self):
        wb = BW.write_inventory.workbook()
        ws = wb["DNIN8"]
        ws.append(["not a port"])
        ws.append([ws.cell(2, 1).value])  # the first port again
        warnings = BW.build_inventory(wb).log.warnings
        self.assertIn("DNIN8: unreadable port id 'not a port'", warnings)
        self.assertIn(f"DNIN8: port {ws.cell(2, 1).value} listed twice", warnings)
        self.assertNotIn("DNIN8: unreadable port id 'not a port'", BW.build_inventory().log.warnings)

    def test_a_network_detail_is_scrubbed_and_noted(self):
        wb = BW.write_inventory.workbook()
        wb["Nodes"].cell(2, 4, "10.0.0.150")
        built = BW.build_inventory(wb)
        self.assertEqual(built.data["nodes"][0]["location"], "")
        self.assertIn("10.0.0.150", built.log.scrubbed)


class TheChecks(unittest.TestCase):
    def broken(self, edit) -> list[str]:
        inv = copy.deepcopy(INV)
        edit(inv)
        return BW.problems(inv)

    def test_an_empty_list_fails(self):
        for key in BW.REQUIRED:
            with self.subTest(key=key):
                self.assertIn(f"{key!r} has no entries", self.broken(lambda inv: inv.update({key: []})))

    def test_a_leaked_network_detail_fails(self):
        bad = self.broken(lambda inv: inv["nodes"][0].update(location="10.0.0.150"))
        self.assertTrue(any("network details or secrets" in b for b in bad), bad)

    def test_a_node_listed_twice_or_unnamed_fails(self):
        self.assertTrue(self.broken(lambda inv: inv["nodes"].append(dict(inv["nodes"][0]))))
        self.assertTrue(self.broken(lambda inv: inv["nodes"][0].update(id="")))

    def test_no_source_fails(self):
        self.assertIn("source.file is empty", self.broken(lambda inv: inv["source"].update(file="")))

    def test_data_text_raises_a_named_error(self):
        inv = copy.deepcopy(INV)
        inv["turnouts"] = []
        with self.assertRaisesRegex(BW.WiringDataError, r"www/data/wiring-inventory.json fails its checks:\n.*turnouts"):
            BW.data_text(inv)


class Errors(unittest.TestCase):
    def test_a_broken_wiring_model_is_a_wiring_data_error(self):
        boom = BW.write_inventory.FactsError("wiring.csv: no such file")
        with mock.patch.object(BW.write_inventory, "workbook", side_effect=boom):
            with self.assertRaisesRegex(BW.WiringDataError, "wiring model cannot be read: wiring.csv"):
                BW.view()

    def test_check_exits_2_when_the_model_cannot_be_read(self):
        boom = BW.write_inventory.FactsError("wiring.csv: no such file")
        with mock.patch.object(BW.write_inventory, "workbook", side_effect=boom):
            code, _, err = run_main("--check")
        self.assertEqual(code, 2)
        self.assertIn("wiring.csv: no such file", err)

    def test_a_missing_sheet_is_named(self):
        wb = BW.write_inventory.workbook()
        del wb["BlockSensors"]
        with self.assertRaisesRegex(BW.WiringDataError, "missing sheet.*BlockSensors"):
            BW.build_inventory(wb)

    def test_check_exits_1_with_the_reason_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(BW, "problems", return_value=["'blocks' has no entries"]):
            code, out, err = run_main("--check", "--out-dir", d)
            self.assertEqual(list(Path(d).iterdir()), [])
        self.assertEqual(code, 1)
        self.assertIn("'blocks' has no entries", err)


class Turnouts(unittest.TestCase):
    """One TurnoutSummary row against a small inventory: its name, its crossover half and the checks on its pins."""

    def inventory(self) -> Any:  # BW.Inventory; BW is loaded by path
        inv = BW.Inventory({}, "test.xlsx", BW.BuildLog())
        inv.device_ports = {"Switch 3 N": ["C1-OU1-1"], "Switch 3 R": ["C1-OU1-2"]}
        inv.nodes["C1"] = {"id": "C1", "inputs": [{"board": "IN1", "pins": [{"port": "C1-IN1-1", "device": "Switch 3 BTN"}]}]}
        return inv

    def test_a_crossover_half_names_its_os_block(self):
        self.assertEqual(BW.crossover_half("Switch 7 (OS Switch 7b)", "Switch 7"), "OS Switch 7b")
        self.assertEqual(BW.crossover_half("Switch 7", "Switch 7"), "")

    def test_a_label_that_is_not_the_turnout_or_a_half_is_an_error(self):
        with self.assertRaisesRegex(BW.WiringDataError, "'Switch 8' is not 'Switch 7'"):
            BW.crossover_half("Switch 8", "Switch 7")

    def test_the_old_workbook_uses_the_label_and_an_empty_name_is_an_error(self):
        self.assertEqual(BW.turnout_name({}, "Switch 3"), "Switch 3")
        with self.assertRaisesRegex(BW.WiringDataError, "'Switch 3' has no JMRI Turnout"):
            BW.turnout_name({"JMRI Turnout": ""}, "Switch 3")

    def test_a_wired_turnout_gives_its_record_and_no_warning(self):
        inv = self.inventory()
        t = inv.turnout({"JMRI Turnout": "Switch 3", "Parent Node": "C1", "Button": "C1-IN1-1",
                         "Entry Signal": "12 upper"}, "Switch 3")
        self.assertEqual((t["motorN"], t["motorR"], t["half"], t["signals"]), ("C1-OU1-1", "C1-OU1-2", "", {"entry": "12 upper"}))
        self.assertEqual(inv.log.warnings, [])

    def test_wrong_pins_are_warnings(self):
        inv = self.inventory()
        inv.turnout({"JMRI Turnout": "Switch 3", "Parent Node": "C2", "Feedback N": "C1-IN1-1", "Button": "C9-IN1-1"},
                    "Switch 3")
        self.assertEqual(inv.log.warnings, [
            "TurnoutSummary: Switch 3 parent node C2, but its motor is on ['C1']",
            "TurnoutSummary: Switch 3 button → C9-IN1-1, but DNIN8 has nothing there",
            "TurnoutSummary: Switch 3 fbN → C1-IN1-1, but DNIN8 has Switch 3 BTN there",
        ])

    def test_no_motor_pins_is_a_warning(self):
        inv = self.inventory()
        inv.turnout({"JMRI Turnout": "Switch 5"}, "Switch 5")
        self.assertEqual(inv.log.warnings, ["TurnoutSummary: Switch 5 has no motor pins on the DNOU8 sheet"])


class OutputKinds(unittest.TestCase):
    def test_a_lamp_names_its_head_and_colour(self):
        self.assertEqual(BW.out_kind("Head 12 upper Y", ""), BW.OutKind("lamp", "Y", "12 upper"))

    def test_other_pins_by_device_type(self):
        self.assertEqual(BW.out_kind("Switch 3 N", "Turnout motor"), BW.OutKind("motor"))
        self.assertEqual(BW.out_kind("", ""), BW.OutKind("spare"))
        self.assertEqual(BW.out_kind("Reserved", ""), BW.OutKind("reserved"))


class Main(unittest.TestCase):
    def test_check_builds_in_memory_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = run_main("--check", "-q", "--out-dir", d)
            self.assertEqual(list(Path(d).iterdir()), [])
        self.assertEqual(code, 0)
        self.assertIn("passes its checks", out)

    def test_a_write_is_the_checked_view(self):
        with tempfile.TemporaryDirectory() as d:
            code, _, _ = run_main("-q", "--out-dir", d)
            self.assertEqual(code, 0)
            written = json.loads((Path(d) / "wiring-inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(written, json.loads(BW.data_text(INV)))

    def test_the_file_is_not_committed(self):
        rel = "www/" + BW.OUT_REL
        tracked = subprocess.run(["git", "ls-files", "--", rel], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.split()
        self.assertEqual(tracked, [], "git rm --cached it (ADR-036)")


if __name__ == "__main__":
    unittest.main()
