from __future__ import annotations

import ast
import csv
import re
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "render_ctc_panel.py"
MAP_CSV = SCRIPT.parents[1] / "data/public_name_map.csv"


def constant(name: str):
    for node in ast.parse(SCRIPT.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return ast.parse(ast.unparse(node.value), mode="eval").body
    raise AssertionError(name)


class ControlPointLabelsTest(unittest.TestCase):
    def test_every_plate_has_a_public_number(self) -> None:
        mapped = set()
        with MAP_CSV.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                hit = re.fullmatch(r"MTT(\d+)", row["hardware"])
                if row["layer"] == "turnout" and hit and row["current"].startswith("DCC Switch "):
                    mapped.add(hit.group(1))
        plates = set()
        for name in ("STANDALONE", "EAST_END", "LADDERS"):
            for node in ast.walk(constant(name)):
                if isinstance(node, ast.Constant) and re.fullmatch(r"1\d\d", str(node.value)):
                    plates.add(node.value)
        self.assertEqual(len(plates), 20)
        self.assertLessEqual(plates, mapped)


if __name__ == "__main__":
    unittest.main()
