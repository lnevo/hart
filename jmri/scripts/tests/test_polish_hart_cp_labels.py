"""polish_hart_cp_labels edits only the hierarchy labels and is stable on a second run."""

from __future__ import annotations

import contextlib
import difflib
import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"


def _load():
    spec = importlib.util.spec_from_file_location(
        "polish_hart_cp_labels", ROOT / "jmri/scripts/polish_hart_cp_labels.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PolishCpLabels(unittest.TestCase):
    def test_changes_only_labels_and_second_run_is_unchanged(self):
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "tables.xml"
            shutil.copy(TABLES, copy)
            original = copy.read_text(encoding="utf-8").splitlines()
            with contextlib.redirect_stdout(io.StringIO()):
                n = mod.apply(copy)
            first = copy.read_bytes()
            changed = [
                line[1:]
                for line in difflib.unified_diff(
                    original, first.decode("utf-8").splitlines(), lineterm="", n=0
                )
                if line[0] in "+-" and not line.startswith(("+++", "---"))
            ]
            self.assertTrue(changed)
            for line in changed:
                self.assertIn("<positionablelabel", line)
                self.assertTrue(any(f'text="{t}"' in line for t in mod.HIERARCHY), line)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(mod.apply(copy), n)
            self.assertEqual(copy.read_bytes(), first)
            self.assertIn("Unchanged", out.getvalue())


if __name__ == "__main__":
    unittest.main()
