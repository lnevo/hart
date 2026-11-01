"""The helix page builds from files in the repo; every STL must be classified."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "www/scripts/build_helix_page.py"
STL_DIR = ROOT / "docs/benchwork/helix/stl"


def constant(name: str):
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


class HelixIndexTest(unittest.TestCase):
    def test_index_matches_repo_files(self) -> None:
        listed = {f for _, rows in constant("GROUPS") for files, _, _ in rows for f in files}
        on_disk = {p.name for p in STL_DIR.iterdir() if p.suffix in {".stl", ".3mf"}}
        self.assertEqual(listed, on_disk)

    def test_no_home_folder_inputs(self) -> None:
        self.assertNotIn("Downloads", GENERATOR.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
