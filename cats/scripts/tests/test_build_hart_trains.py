"""cats/data/hart_trains.csv is built from the train master, in the CATS file's own columns. The tests use fixtures
only: unit-cats may read code, jmri/ and cats/ (check_stamps.BY_KIND), not ops/; the hart-trains step checks the
committed file."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "build_hart_trains.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_hart_trains", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class BuildHartTrains(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_cats_columns_in_order_and_master_only_columns_and_trains_left_out(self) -> None:
        master = self.dir / "trains.csv"
        master.write_text("train_symbol,train_name,engine,font,runs_job,on_desks,opspro_name,notes\n"
                          'X1,Extra 1,42,East,true,yes,Extra One,"a note, with a comma"\n'
                          "STG-X,,,,,no,,an Operations Pro staging train\n", encoding="utf-8")
        self.assertEqual(self.mod.build(master),
                         "train_name,train_symbol,engine,font,runs_job,notes\n"
                         'Extra 1,X1,42,East,true,"a note, with a comma"\n')

    def test_on_desks_other_than_yes_or_no_is_an_error(self) -> None:
        master = self.dir / "trains.csv"
        master.write_text("train_symbol,train_name,engine,font,runs_job,on_desks,opspro_name,notes\n"
                          "X1,Extra 1,42,East,true,Yes,,\n", encoding="utf-8")
        self.assertRaisesRegex(self.mod.TrainsError, "on_desks must be yes or no: X1", self.mod.build, master)

    def test_a_missing_column_is_an_error(self) -> None:
        master = self.dir / "trains.csv"
        master.write_text("train_symbol,train_name\nX1,Extra 1\n", encoding="utf-8")
        self.assertRaisesRegex(self.mod.TrainsError, "no column engine", self.mod.build, master)

    def test_main_reports_a_bad_master_and_writes_nothing(self) -> None:
        import contextlib
        import io
        master = self.dir / "trains.csv"
        master.write_text("train_symbol,train_name\nX1,Extra 1\n", encoding="utf-8")
        out = self.dir / "hart_trains.csv"
        err = io.StringIO()
        with mock.patch.object(self.mod, "OUT", out), mock.patch.object(self.mod, "MASTER", master), \
                contextlib.redirect_stderr(err):
            self.assertEqual(self.mod.main([]), 1)
        self.assertIn("no column engine", err.getvalue())
        self.assertFalse(out.exists())

    def test_check_fails_on_a_stale_file_and_a_build_fixes_it(self) -> None:
        out = self.dir / "hart_trains.csv"
        out.write_text("stale\n", encoding="utf-8")
        master = self.dir / "trains.csv"
        master.write_text("train_symbol,train_name,engine,font,runs_job,on_desks,opspro_name,notes\n"
                          "X1,Extra 1,42,East,true,yes,,DS-01 #1 \u2014 a note\n", encoding="utf-8")
        with mock.patch.object(self.mod, "OUT", out), mock.patch.object(self.mod, "MASTER", master):
            self.assertEqual(self.mod.main(["--check"]), 1)
            self.assertEqual(self.mod.main([]), 0)
            self.assertEqual(self.mod.main(["--check"]), 0)
        self.assertEqual(out.read_bytes(), "train_name,train_symbol,engine,font,runs_job,notes\n"
                                           "Extra 1,X1,42,East,true,DS-01 #1 \u2014 a note\n".encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
