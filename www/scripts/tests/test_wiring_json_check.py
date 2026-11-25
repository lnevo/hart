"""build_wiring_json.py: the wiring viewer's JSON is built from the wiring model, and --check must match it apart from the build date."""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_wiring_json", ROOT / "www/scripts/build_wiring_json.py")
BW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BW)

NAMES = ("wiring-inventory.json",)


def run_check(out_dir: Path) -> tuple[int, str]:
    BW.WARNINGS.clear()
    BW.SCRUBBED.clear()
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["build_wiring_json.py", "--check", "--out-dir", str(out_dir)]), redirect_stdout(out):
        code = BW.main()
    return code, out.getvalue()


class Stale(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.data = {"source": {"file": "x.xlsx", "built": "2026-11-17"}, "nodes": [{"id": "C1"}]}

    def write(self, data):
        p = self.dir / "a.json"
        p.write_text(BW.render(data), encoding="utf-8")
        return p

    def test_only_the_dates_differ(self):
        p = self.write({**self.data, "source": {"file": "x.xlsx", "built": "2026-01-01", "modified": "2026-01-01"}})
        self.assertFalse(BW.stale(p, {**self.data, "source": {**self.data["source"], "modified": "2026-11-17"}}))

    def test_changed_data_is_stale(self):
        p = self.write({**self.data, "nodes": [{"id": "C2"}]})
        self.assertTrue(BW.stale(p, self.data))

    def test_missing_or_broken_file_is_stale(self):
        self.assertTrue(BW.stale(self.dir / "none.json", self.data))
        p = self.dir / "bad.json"
        p.write_text("{", encoding="utf-8")
        self.assertTrue(BW.stale(p, self.data))
        for text in ("[]", '{"source": null}'):
            p.write_text(text, encoding="utf-8")
            self.assertTrue(BW.stale(p, self.data))


class FromTheModel(unittest.TestCase):
    """The JSON is built from the wiring model (write_inventory.workbook(), in memory); v86 is an output only."""

    def test_it_builds_the_committed_json_without_opening_any_workbook(self):
        never = mock.Mock(side_effect=AssertionError("a workbook file was opened"))
        with mock.patch("openpyxl.load_workbook", never), mock.patch("openpyxl.reader.excel.load_workbook", never), \
                mock.patch.object(BW.write_inventory, "load_workbook", never), \
                mock.patch.object(BW.write_inventory, "OUT", Path(tempfile.gettempdir()) / "no-such-v86.xlsx"):
            inv = BW.build_inventory()
        never.assert_not_called()
        self.assertEqual(inv["source"], {"file": "LCOS_Layout_Inventory_v86.xlsx", "version": "v86"})
        self.assertFalse(BW.stale(ROOT / "www/data/wiring-inventory.json", inv))

    def test_a_given_workbook_is_read_as_the_model_gives_it(self):
        wb = BW.write_inventory.workbook()
        wb["Nodes"].cell(2, 4, "Somewhere else")
        inv = BW.build_inventory(wb)
        self.assertEqual(inv["nodes"][0]["location"], "Somewhere else")


class CheckTheRepo(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        for name in NAMES:
            shutil.copy(ROOT / "www/data" / name, self.dir / name)

    def test_an_edited_file_fails_and_is_left_alone(self):
        p = self.dir / "wiring-inventory.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["nodes"][0]["location"] = "Nowhere"
        p.write_text(json.dumps(data), encoding="utf-8")
        before = p.read_bytes()
        code, out = run_check(self.dir)
        self.assertEqual(code, 1)
        self.assertIn("STALE", out)
        self.assertIn("wiring-inventory.json", out)
        self.assertEqual(p.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
