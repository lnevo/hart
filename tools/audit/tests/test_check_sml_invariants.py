"""tools/audit/check_sml_invariants.py: the repo tables pass, an unreadable tables file gives a one-line message and
exit 2, an ISNX sensor in the tables while NX is parked fails, NX unparked fails until its own check exists, and a
copy of the script with no hartlib above it raises SmlInvariantsError when imported and prints one line when run. Every changed tables file is a temporary copy."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/audit/check_sml_invariants.py"
SPEC = importlib.util.spec_from_file_location("check_sml_invariants", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class CheckSmlInvariants(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_check(self, tables_xml: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = C.run(tables_xml)
        return rc, out.getvalue(), err.getvalue()

    def tables_with_isnx(self) -> Path:
        root = C.tables.read(C.TABLES)
        box = root.find("sensors")
        assert box is not None
        sensor = ET.SubElement(box, "sensor")
        ET.SubElement(sensor, "systemName").text = "ISNX:TEST"
        path = self.tmp / "tables.xml"
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        return path

    def test_repo_tables_pass_and_name_the_skip(self) -> None:
        rc, out, err = self.run_check(C.TABLES)
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("OK: destination count", out)
        self.assertIn("OK: Entry/Exit parked, no ISNX sensor in tables.xml", out)
        self.assertIn("skipped: NX mast-only check, NX is parked (hartlib.parked)", out)

    def test_missing_file(self) -> None:
        rc, out, err = self.run_check(self.tmp / "none.xml")
        self.assertEqual(rc, 2)
        self.assertIn("MISSING:", err)

    def test_broken_xml_is_a_clean_message(self) -> None:
        bad = self.tmp / "tables.xml"
        bad.write_text("<layout-config><sensors></layout-config>", encoding="utf-8")
        rc, out, err = self.run_check(bad)
        self.assertEqual((rc, out), (2, ""))
        self.assertTrue(err.startswith(f"FAIL: cannot read {bad}: "), err)
        self.assertNotIn("Traceback", err)

    def test_wrong_encoding_is_a_clean_message(self) -> None:
        bad = self.tmp / "tables.xml"
        bad.write_bytes(b'<?xml version="1.0" encoding="ISO-8859-1"?><layout-config/>')
        rc, _, err = self.run_check(bad)
        self.assertEqual(rc, 2)
        self.assertIn("UTF-8", err)

    def test_unreadable_path_is_a_clean_message(self) -> None:
        path = self.tmp / "tables.xml"
        path.write_text("<layout-config/>", encoding="utf-8")
        with mock.patch.object(C.tables, "read", side_effect=PermissionError("denied")):
            rc, _, err = self.run_check(path)
        self.assertEqual(rc, 2)
        self.assertIn("denied", err)

    def test_isnx_sensor_while_parked_fails(self) -> None:
        rc, out, _ = self.run_check(self.tables_with_isnx())
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: Entry/Exit is parked, but tables.xml holds 1 ISNX sensors", out)

    def test_nx_unparked_fails(self) -> None:
        with mock.patch.object(C.parked, "PARKED", frozenset({"dispatcher", "uss"})):
            rc, out, _ = self.run_check(C.TABLES)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: NX is not parked", out)
        self.assertNotIn("OK: NX", out)

    def test_unreadable_panel_counts_is_a_clean_message(self) -> None:
        with mock.patch.object(C, "expected_dests", side_effect=FileNotFoundError("panel_counts.json")):
            rc, out, err = self.run_check(C.TABLES)
        self.assertEqual((rc, out), (2, ""))
        self.assertEqual(err, "FAIL: panel_counts.json\n")

    def test_tables_without_their_sections_is_a_clean_message(self) -> None:
        with mock.patch.object(C.tables, "mast_logic_pairs", side_effect=ValueError("no signalmastlogics")):
            rc, _, err = self.run_check(C.TABLES)
        self.assertEqual(rc, 2)
        self.assertEqual(err, "FAIL: no signalmastlogics\n")

    def test_no_hartlib_run_is_a_one_line_message(self) -> None:
        copy = self.tmp / "check_sml_invariants.py"
        shutil.copy2(SCRIPT, copy)
        done = subprocess.run([sys.executable, "-I", str(copy)], capture_output=True, text=True, cwd=self.tmp)
        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stderr, f"FAIL: no tools/hartlib/src above {copy}\n")

    def test_no_hartlib_import_raises_own_error(self) -> None:
        copy = self.tmp / "check_sml_invariants.py"
        shutil.copy2(SCRIPT, copy)
        spec = importlib.util.spec_from_file_location("sml_copy", copy)
        assert spec is not None and spec.loader is not None
        with self.assertRaisesRegex(Exception, "no tools/hartlib/src above") as caught:
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
        self.assertEqual(type(caught.exception).__name__, "SmlInvariantsError")


if __name__ == "__main__":
    unittest.main()
