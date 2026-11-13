from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
