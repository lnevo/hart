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
                    mock.patch.object(sys, "argv", [str(SCRIPT), "--out", str(out)]), redirect_stdout(io.StringIO()):
                runpy.run_path(str(SCRIPT), run_name="__main__")
            slides = Presentation(out).slides
            text = [" ".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame) for s in slides]
        never.assert_not_called()
        self.assertEqual(len(text), 2 + len(ids))         # the node and turnout summaries, then one per client node
        for nid in ids:
            self.assertTrue(any(t.startswith(f"Node {nid} ") for t in text[2:]), f"no slide for node {nid}")


if __name__ == "__main__":
    unittest.main()
