"""build_hart_signal_heads.py must reproduce the committed signal_head_plan.csv.

The script (wiki/pipelines/wiring-docs.md) rewrites signal_head_plan.csv from wiring.csv's wired heads, and the
CATS desk build
(hartlib.cats.mast_templates) reads PHYSIGNAL from signal_head_plan.csv. A builder list that drifts from
that file silently undoes field changes on the next run.
"""
from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[3]
SIGNALS = ROOT / "docs/wiring/signals"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
FILES = ("signal_head_plan.csv",)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "build_hart_signal_heads", SCRIPTS / "build_hart_signal_heads.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BuildHartSignalHeadsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load_module()
        cls.rows = cls.m.build_rows()

    def test_the_head_plan_matches_the_committed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            saved = self.m.DATA
            self.m.DATA = out
            try:
                with redirect_stdout(StringIO()):
                    self.m.write_csvs(self.rows)
            finally:
                self.m.DATA = saved
            for name in FILES:
                with self.subTest(file=name):
                    self.assertEqual(
                        (out / name).read_bytes(),
                        (SIGNALS / name).read_bytes(),
                        f"{name} differs from the builder; fix wiring.csv or the CSV",
                    )

    def head_plan(self) -> dict[str, dict]:
        with (SIGNALS / "signal_head_plan.csv").open(newline="") as f:
            return {r["mast_user_name"]: r for r in csv.DictReader(f)}

    def test_6lb_one_high_head_in_head_plan(self) -> None:
        row = self.head_plan()["Mast 6LB"]
        self.assertEqual(row["physignal"], "single")
        self.assertEqual(row["mast_system_name"], "IF$shsm:basic:one-searchlight(IH432)")

    def test_wiring_lists_wired_heads_only(self) -> None:
        # ADR-024: Mast 6LB on IH432 is the one wired head; IH433 was dropped.
        packed = {(r["mast_user_name"], r["packed"]) for r in self.rows}
        self.assertEqual(packed, {("Mast 6LB", 432)})

    def test_head_plan_mast_names_match_tables(self) -> None:
        text = TABLES.read_text(encoding="utf-8")
        for mast, row in self.head_plan().items():
            if row["mast_system_name"] in text:
                continue
            # An interim mast (6LB) shows fewer heads than planned; the
            # appearance must still match, which is what CATS PHYSIGNAL needs.
            with self.subTest(mast=mast):
                self.assertRegex(
                    text,
                    rf"<systemName>IF\$shsm:basic:{row['appearance']}\([^<]*</systemName>\s*"
                    rf"<userName>{mast}</userName>",
                )


if __name__ == "__main__":
    unittest.main()
