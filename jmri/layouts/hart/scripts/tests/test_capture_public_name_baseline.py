from __future__ import annotations

import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "capture_public_name_baseline", SCRIPTS / "capture_public_name_baseline.py"
)
capture = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(capture)


class StaleFilesTest(unittest.TestCase):
    def test_binding_change_and_missing_file_are_stale(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            committed, fresh = Path(a), Path(b)
            (committed / "counts.txt").write_text("x.csv=1\n")
            (fresh / "counts.txt").write_text("x.csv=1\n")
            (committed / "sml_pairs.csv").write_text("mast\nMast 9LA\n")
            (fresh / "sml_pairs.csv").write_text("mast\nMast 10RA\n")
            (committed / "ctc_trl.csv").write_text("old\n")
            (committed / "README.md").write_text("not a capture\n")
            self.assertEqual(
                ["ctc_trl.csv", "sml_pairs.csv"], capture.stale_files(committed, fresh)
            )

    def test_counts_file_holds_only_name_count_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "counts.txt"
            capture.write_counts(path, {"b.csv": 2, "a.csv": 1})
            lines = path.read_text().splitlines()
        self.assertEqual(["a.csv=1", "b.csv=2"], lines)
        committed = (capture.DEFAULT_OUT / "counts.txt").read_text().splitlines()
        self.assertTrue(all(re.fullmatch(r"[\w.]+=\d+", line) for line in committed), committed)


if __name__ == "__main__":
    unittest.main()
