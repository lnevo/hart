from __future__ import annotations

import importlib.util
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


class DisplayPathTest(unittest.TestCase):
    def test_repo_file_is_written_relative(self):
        self.assertEqual(
            "jmri/layouts/hart/output/tables.xml",
            capture.display_path(capture.DEFAULT_TABLES),
        )

    def test_outside_file_keeps_its_path(self):
        outside = Path("/example.invalid/tables.xml")
        self.assertEqual(str(outside), capture.display_path(outside))


class StaleFilesTest(unittest.TestCase):
    def test_sha_change_alone_is_not_stale_but_a_binding_change_is(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            committed, fresh = Path(a), Path(b)
            (committed / "counts.txt").write_text("tables.xml sha256=aaa\nx.csv=1\n")
            (fresh / "counts.txt").write_text("tables.xml sha256=bbb\nx.csv=1\n")
            (committed / "x.csv").write_text("mast\nMast 9LA\n")
            (fresh / "x.csv").write_text("mast\nMast 10RA\n")
            self.assertEqual(["x.csv"], capture.stale_files(committed, fresh))

    def test_committed_baselines_match_tables(self):
        self.assertEqual(0, capture.main(["--check"]))


if __name__ == "__main__":
    unittest.main()
