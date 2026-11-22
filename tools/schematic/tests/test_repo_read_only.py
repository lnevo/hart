"""repo_read_only() refuses writes inside the repo, but lets the builders use the shared cache (hartlib.paths.cache_dir,
<main checkout>/.cache/hart), which now sits inside the main checkout."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2] / "tools/hartlib/src")]

import repo_read_only as rro  # noqa: E402


class RepoReadOnlyGuard(unittest.TestCase):
    def test_a_write_in_the_repo_is_refused(self) -> None:
        with rro.repo_read_only(), self.assertRaises(AssertionError):
            (rro.REPO / "never-written.txt").open("w")

    def test_the_shared_cache_is_allowed(self) -> None:
        self.assertFalse(rro.in_repo(rro.CACHE / "schematic" / "entry.pickle"))
        self.assertTrue(rro.in_repo(rro.REPO / "jmri/layouts/hart/output/tables.xml"))

    def test_a_folder_outside_the_repo_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as d, rro.repo_read_only():
            (Path(d) / "ok.txt").write_text("ok", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
