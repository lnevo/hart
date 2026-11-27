"""The scripts that once edited tables.xml by hand refuse to write it since R9c (ADR-029): it is generated
(tools/schematic/build_tables.py), so each stops naming the generator (hartlib.tables_build.refuse_generated) and
the file keeps its bytes. They may still write another tables file they are pointed at."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import paths, tables_build as tb  # noqa: E402

TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
REFUSING = (
    ("tools/schematic/sync_signals.py", []),
)


class GeneratedTablesRefused(unittest.TestCase):
    def test_the_old_writers_stop_and_leave_tables_xml_alone(self) -> None:
        before = TABLES.read_bytes()
        env = {k: v for k, v in os.environ.items() if k != "HART_TABLES"}
        env["HART_GUARD_JMRI_RUNNING"] = "0"
        for script, args in REFUSING:
            with self.subTest(script=script):
                done = subprocess.run([sys.executable, str(ROOT / script), *args], cwd=ROOT, env=env,
                                      capture_output=True, text=True, timeout=300)
                self.assertEqual(1, done.returncode, done.stdout[-500:])
                self.assertIn("tables.xml is generated (ADR-029)", done.stderr)
                self.assertNotIn("Traceback", done.stderr)          # main prints the refusal, not a traceback
                self.assertEqual(before, TABLES.read_bytes())

    def test_refuse_generated_names_only_the_repo_file(self) -> None:
        with self.assertRaisesRegex(tb.GeneratedTablesError, "x.py: not writing .*build_tables.py"):
            tb.refuse_generated(paths.REPO_TABLES_XML, "x.py")
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "tables.xml"
            link.symlink_to(paths.REPO_TABLES_XML)
            with self.assertRaises(tb.GeneratedTablesError):
                tb.refuse_generated(link, "x.py")             # through a link too
            other = Path(tmp) / "other.xml"
            shutil.copy(paths.REPO_TABLES_XML, other)
            tb.refuse_generated(other, "x.py")                # another tables file may be written
