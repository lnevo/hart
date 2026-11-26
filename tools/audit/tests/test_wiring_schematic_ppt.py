"""create_wiring_schematic_ppt.py builds Wiring_Schematic.pptx from the wiring model (write_inventory.workbook(), in
memory), never from LCOS_Layout_Inventory_v86.xlsx, which is an output only (ADR-039)."""
from __future__ import annotations

import ast
import importlib.util
import io
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType
from typing import ClassVar
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
WIRING = ROOT / "tools/wiring"
SCRIPT = WIRING / "create_wiring_schematic_ppt.py"
HAS_PPTX = importlib.util.find_spec("pptx") is not None


class ReadsTheModel(unittest.TestCase):
    def test_the_source_takes_the_workbook_from_the_model_and_names_no_xlsx(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        self.assertIn("write_inventory.workbook", calls)
        self.assertFalse({c for c in calls if c.endswith("load_workbook")}, "the script opens a workbook file")
        docs = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr)}      # docstrings may name it
        strings = [n.value for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
        self.assertFalse([s for s in strings if ".xlsx" in s], "the script names a workbook file")

    @unittest.skipUnless(HAS_PPTX, "python-pptx is not installed (requirements.txt)")
    def test_it_builds_a_slide_per_client_node_without_opening_any_workbook(self):
        from pptx import Presentation

        sys.path.insert(0, str(WIRING))
        self.addCleanup(sys.path.remove, str(WIRING))
        import write_inventory

        ids = [r[0].value for r in write_inventory.workbook()["Nodes"].iter_rows(min_row=2)
               if str(r[0].value).startswith("C")]
        never = mock.Mock(side_effect=AssertionError("a workbook file was opened"))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "deck.pptx"
            with mock.patch("openpyxl.load_workbook", never), mock.patch("openpyxl.reader.excel.load_workbook", never), \
                    mock.patch.object(write_inventory, "load_workbook", never), \
                    mock.patch.object(sys, "argv", [str(SCRIPT), "--out", str(out)]), redirect_stdout(io.StringIO()), \
                    self.assertRaises(SystemExit) as done:
                runpy.run_path(str(SCRIPT), run_name="__main__")
            self.assertEqual(done.exception.code, 0)
            slides = Presentation(out).slides
            text = [" ".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame) for s in slides]
        never.assert_not_called()
        bad = mock.Mock(side_effect=write_inventory.FactsError("node 99 is not in lcos_nodes.csv"))
        err = io.StringIO()
        with mock.patch.object(write_inventory, "workbook", bad), redirect_stdout(io.StringIO()), \
                mock.patch.object(sys, "stderr", err), mock.patch.object(sys, "argv", [str(SCRIPT), "--out", "x"]):
            with self.assertRaises(SystemExit) as stop:
                runpy.run_path(str(SCRIPT), run_name="__main__")
        self.assertEqual(stop.exception.code, 2)          # bad wiring data: one line, no traceback
        self.assertIn("node 99 is not in lcos_nodes.csv", err.getvalue())
        mismatch = mock.Mock(side_effect=write_inventory.InventoryError("occupancy X names no block"))
        err = io.StringIO()
        with mock.patch.object(write_inventory, "workbook", mismatch), redirect_stdout(io.StringIO()), \
                mock.patch.object(sys, "stderr", err), mock.patch.object(sys, "argv", [str(SCRIPT), "--out", "x"]):
            with self.assertRaises(SystemExit) as stop:
                runpy.run_path(str(SCRIPT), run_name="__main__")
        self.assertEqual(stop.exception.code, 2)          # a master/node-file mismatch is bad wiring data too
        self.assertIn("occupancy X names no block", err.getvalue())
        self.assertEqual(len(text), 2 + len(ids))         # the node and turnout summaries, then one per client node
        for nid in ids:
            self.assertTrue(any(t.startswith(f"Node {nid} ") for t in text[2:]), f"no slide for node {nid}")


class FakeSheet:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def iter_rows(self, values_only: bool = False) -> list[tuple]:
        return self.rows


class FakeBook(dict):
    @property
    def sheetnames(self) -> list[str]:
        return list(self)


@unittest.skipUnless(HAS_PPTX, "python-pptx is not installed (requirements.txt)")
class Steps(unittest.TestCase):
    """The deck's reading steps, on small sheets."""

    D: ClassVar[ModuleType]

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(WIRING))
        spec = importlib.util.spec_from_file_location("wiring_deck", SCRIPT)
        assert spec is not None and spec.loader is not None
        cls.D = sys.modules["wiring_deck"] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.D)

    def test_split_port(self) -> None:
        self.assertEqual(self.D.split_port("C3-OU1-7"), ("C3-OU1", 7))
        self.assertIsNone(self.D.split_port("C3-OU1"))
        self.assertIsNone(self.D.split_port("C3-OU1-x"))

    def test_a_missing_column_is_named(self) -> None:
        with self.assertRaisesRegex(self.D.WiringDeckError, "sheet 'Nodes' has no column 'Location'"):
            self.D.records(FakeSheet([("Node ID",), ("C1",)]), "Nodes", ("Node ID", "Location"))

    def test_location_in_the_first_column_is_read(self) -> None:
        heads = ("Location", "Node ID", "Address", "12V Boards", "5V Boards", "Num Blocks")
        book = FakeBook(Nodes=FakeSheet([heads, ("Yard", "C2", 2, 1, None, 3), ("East", "M1", 1, 0, 0, 0)]),
                        DNOU8=FakeSheet([("Parent Node ID", "Output Port ID", "Connected Device"),
                                         ("C2", "C2-OU1-1", " T1 "), ("C2", "C2-OU1-0", "x")]),
                        DNIN8=FakeSheet([("Parent Node ID", "Input Port ID", "Connected Device")]),
                        BlockSensors=FakeSheet([("Node ID", "Port ID", "Block Section Name"), ("C2", "C2-B1", " B ")]))
        nodes, boards = self.D.collect_nodes(book)
        self.assertEqual(nodes, [self.D.NodeSummary("C2", "Yard", "2", 1, 0, 3)])
        self.assertEqual(boards["C2"].outputs, {"C2-OU1": {1: "T1"}})
        self.assertEqual(boards["C2"].blocks, [("C2-B1", "B")])

    def test_crossover_halves_are_one_turnout_row(self) -> None:
        heads = ("JMRI Turnout", "Parent Node", "Button", "Feedback N", "Feedback R", "Entry Signal",
                 "Normal Exit Signal", "Reverse Exit Signal")
        book = FakeBook(TurnoutSummary=FakeSheet([heads, ("T9", "C10", "B1", "C10-IN1-1", None, "S1", None, None),
                                                   ("T9", "C10", "B1", None, None, "S2", "S1", None),
                                                   ("T2", "C2", None, None, "C2-IN1-2", None, None, None)]))
        rows = self.D.collect_turnouts(book)
        self.assertEqual([(r.turnout, r.feedback, r.signals) for r in rows],
                         [("T2", "R:C2-IN1-2", []), ("T9", "N:C10-IN1-1", ["S1", "S2"])])
        self.assertIsNone(self.D.collect_turnouts(FakeBook()))


if __name__ == "__main__":
    unittest.main()
