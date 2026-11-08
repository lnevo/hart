"""build_hart_signal_heads.py must reproduce the committed wiring CSVs.

`--wiring-only` (wiki/pipelines/wiring-docs.md) rewrites signal_wiring.csv,
signal_head_plan.csv and signal_mast_plan.csv, and cats/scripts/wire_digicon.py
reads PHYSIGNAL from signal_head_plan.csv. A builder list that drifts from
those files silently undoes field changes on the next run.
"""
from __future__ import annotations

import csv
import importlib.util
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[3]
SIGNALS = ROOT / "docs/wiring/signals"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
FILES = ("signal_wiring.csv", "signal_head_plan.csv", "signal_mast_plan.csv")


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

    def test_wiring_only_output_matches_committed_csvs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            shutil.copy(SIGNALS / "signal_mast_plan.csv", out / "signal_mast_plan.csv")
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
                        f"{name} differs from the builder; fix HEADS_3PIN or the CSV",
                    )

    def head_plan(self) -> dict[str, dict]:
        with (SIGNALS / "signal_head_plan.csv").open(newline="") as f:
            return {r["mast_user_name"]: r for r in csv.DictReader(f)}

    def test_6lb_interim_dwarf_in_head_plan(self) -> None:
        row = self.head_plan()["Mast 6LB"]
        self.assertEqual(row["physignal"], "single")
        self.assertEqual(row["mast_system_name"], "IF$shsm:basic:one-low(IH432)")

    def test_6lb_wiring_keeps_planned_bottom_head(self) -> None:
        packed = {r["packed"] for r in self.rows if r["mast_user_name"] == "Mast 6LB"}
        self.assertEqual(packed, {432, 433})

    def test_head_plan_mast_names_match_tables(self) -> None:
        text = TABLES.read_text(encoding="utf-8")
        for mast, row in self.head_plan().items():
            if row["mast_system_name"] in text:
                continue
            # Plan packed IDs may differ from live beans (crosswalk); the
            # appearance must still match, which is what CATS PHYSIGNAL needs.
            with self.subTest(mast=mast):
                self.assertRegex(
                    text,
                    rf"<systemName>IF\$shsm:basic:{row['appearance']}\([^<]*</systemName>\s*"
                    rf"<userName>{mast}</userName>",
                )

    def test_full_mode_refuses_plan_ids_that_are_not_live(self) -> None:
        text = TABLES.read_text(encoding="utf-8")
        missing = self.m.check_live_heads(self.m.fitted_rows(self.rows), text)
        self.assertIn("IH232", missing)  # 24RA plan ID; live bean is IH1232
        self.assertNotIn("IH432", missing)


if __name__ == "__main__":
    unittest.main()
