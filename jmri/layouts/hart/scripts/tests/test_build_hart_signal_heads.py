"""build_hart_signal_heads.py must reproduce the committed signal_head_plan.csv.

The script (wiki/pipelines/wiring-docs.md) rewrites signal_head_plan.csv from wiring.csv's wired heads, and the
CATS desk build
(hartlib.cats.mast_templates) reads PHYSIGNAL from signal_head_plan.csv. A builder list that drifts from
that file silently undoes field changes on the next run.
"""
from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[3]
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"

sys.path[:0] = [str(ROOT / "tools/hartlib/src")]
from hartlib import paths  # noqa: E402


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
            out = Path(tmp) / "signal_head_plan.csv"
            saved = self.m.HEAD_PLAN
            self.m.HEAD_PLAN = out
            try:
                with redirect_stdout(StringIO()):
                    self.m.write_csvs(self.rows)
            finally:
                self.m.HEAD_PLAN = saved
            self.assertEqual(
                out.read_bytes(),
                paths.SIGNAL_HEAD_PLAN.read_bytes(),
                "signal_head_plan.csv differs from the builder; fix wiring.csv or the CSV",
            )

    def test_check_mode_current_and_stale(self) -> None:
        self.assertTrue(self.m.check_csvs(self.rows))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "signal_head_plan.csv"
            saved = self.m.HEAD_PLAN
            self.m.HEAD_PLAN = out
            try:
                self.assertFalse(self.m.check_csvs(self.rows), "a missing file is stale")
                out.write_text(paths.SIGNAL_HEAD_PLAN.read_text() + "x\n")
                self.assertFalse(self.m.check_csvs(self.rows))
                self.assertTrue(out.read_text().endswith("x\n"), "check writes nothing")
            finally:
                self.m.HEAD_PLAN = saved

    def test_check_cli_reports_a_stale_file_and_exits_1(self) -> None:
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "signal_head_plan.csv"
            out.write_text("stale\n")
            saved = self.m.HEAD_PLAN
            self.m.HEAD_PLAN = out
            err = StringIO()
            try:
                with unittest.mock.patch.object(sys, "argv", ["x", "--check"]), contextlib.redirect_stderr(err):
                    code = self.m.main()
            finally:
                self.m.HEAD_PLAN = saved
            self.assertEqual(code, 1)
            self.assertIn("is stale", err.getvalue())
            self.assertEqual(out.read_text(), "stale\n", "check writes nothing")

    def test_check_cli_exit_codes(self) -> None:
        import subprocess
        script = str(SCRIPTS / "build_hart_signal_heads.py")
        ok = subprocess.run([sys.executable, script, "--wiring-only", "--check"], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def head_plan(self) -> dict[str, dict]:
        with paths.SIGNAL_HEAD_PLAN.open(newline="") as f:
            return {r["mast_user_name"]: r for r in csv.DictReader(f)}

    def test_6lb_one_high_head_in_head_plan(self) -> None:
        row = self.head_plan()["Mast 6LB"]
        self.assertEqual(row["physignal"], "single")
        self.assertEqual(row["mast_system_name"], "IF$shsm:basic:one-searchlight(IH432)")

    def test_wiring_lists_wired_heads_only(self) -> None:
        # ADR-024: Mast 6LB on IH432 is the one wired head; IH433 was dropped.
        packed = {(r.mast, r.packed) for r in self.rows}
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


class PortErrorsTest(unittest.TestCase):
    """build_rows raises HeadPlanError, which main() reports with exit 2, for a lamp it cannot place."""

    def setUp(self) -> None:
        self.m = load_module()
        self.HEAD = self.m.WiredHead("Mast 9", 4, "C4", 432, "C4-OU2-3", "C4-OU2-2", "C4-OU2-1", "S")

    def _rows(self, heads: list, cal_ports: set[str]) -> list:
        with unittest.mock.patch.object(self.m, "heads_3pin", return_value=heads), \
                unittest.mock.patch.object(self.m.wiring, "calibration_ports", return_value=cal_ports):
            return self.m.build_rows()

    def test_a_lamp_on_a_calibration_port_is_refused(self) -> None:
        with self.assertRaisesRegex(self.m.HeadPlanError, "C4-OU2-1 is a calibration relay's port"):
            self._rows([self.HEAD], {"C4-OU2-1"})

    def test_two_lamps_on_one_port_are_refused(self) -> None:
        other = self.HEAD._replace(mast="Mast 10", packed=433)
        with self.assertRaisesRegex(self.m.HeadPlanError, "duplicate port C4-OU2-1: Mast 9 S R and Mast 10"):
            self._rows([self.HEAD, other], set())

    def test_main_reports_the_error_and_exits_2(self) -> None:
        err = StringIO()
        with unittest.mock.patch.object(self.m, "build_rows", side_effect=self.m.HeadPlanError("duplicate port X")), \
                unittest.mock.patch.object(sys, "argv", ["build_hart_signal_heads.py", "--check"]), \
                unittest.mock.patch("sys.stderr", err):
            self.assertEqual(self.m.main(), 2)
        self.assertIn("duplicate port X", err.getvalue())


class WiringErrorsTest(unittest.TestCase):
    """heads_3pin and plan_masts raise HeadPlanError for wiring rows that make no head or no mast."""

    def setUp(self) -> None:
        self.m = load_module()

    @staticmethod
    def lamp(color: str, port: str, packed: str = "432", disc: str = "S", mast: str = "Mast 9") -> dict[str, str]:
        return {"packed": packed, "lamp_color": color, "mast_user_name": mast, "mqtt_node": "4",
                "parent_node_id": "C4", "port_id": port, "disc_role": disc}

    def heads(self, rows: list[dict[str, str]]) -> list:
        with unittest.mock.patch.object(self.m.wiring, "digicon_rows", return_value=rows):
            return self.m.heads_3pin()

    def test_a_whole_head_is_read(self) -> None:
        got = self.heads([self.lamp("R", "p1"), self.lamp("Y", "p2"), self.lamp("G", "p3")])
        self.assertEqual(got, [self.m.WiredHead("Mast 9", 4, "C4", 432, "p3", "p2", "p1", "S")])

    def test_a_head_missing_a_lamp_is_refused(self) -> None:
        with self.assertRaisesRegex(self.m.HeadPlanError, r"IH432 has lamps \['R', 'Y'\]"):
            self.heads([self.lamp("R", "p1"), self.lamp("Y", "p2")])

    def test_a_lamp_given_twice_is_refused(self) -> None:
        with self.assertRaisesRegex(self.m.HeadPlanError, "IH432 .* has two R lamps"):
            self.heads([self.lamp("R", "p1"), self.lamp("R", "p2")])

    def test_an_unknown_disc_is_refused(self) -> None:
        rows = [self.lamp(c, p, disc="X") for c, p in (("R", "p1"), ("Y", "p2"), ("G", "p3"))]
        with self.assertRaisesRegex(self.m.HeadPlanError, "disc 'X'"):
            self.heads(rows)

    def test_a_mast_with_four_heads_has_no_appearance(self) -> None:
        pins = [self.m.HeadPin("Mast 9", 4, "C4", 430 + i, "S", "R", f"p{i}") for i in range(4)]
        with self.assertRaisesRegex(self.m.HeadPlanError, "Mast 9 has 4 wired heads"):
            self.m.plan_masts(pins)

    def test_two_heads_plan_top_first(self) -> None:
        pins = [self.m.HeadPin("Mast 9", 4, "C4", 433, "B", "R", "p4"),
                self.m.HeadPin("Mast 9", 4, "C4", 432, "T", "R", "p1")]
        (row,) = self.m.plan_masts(pins)
        self.assertEqual(row["mast_system_name"], "IF$shsm:basic:two-searchlight(IH432)(IH433)")
        self.assertEqual((row["physignal"], row["port_ids"]), ("double", "p4 p1"))


if __name__ == "__main__":
    unittest.main()
