"""cats/data/hart_trains.csv is built from the train master, in the CATS file's own columns."""
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

    def test_the_committed_file_is_a_build_of_the_master(self) -> None:
        self.assertEqual(self.mod.OUT.read_bytes(), self.mod.build().encode("utf-8"))

    def test_cats_columns_in_order_and_master_only_columns_left_out(self) -> None:
        master = self.dir / "trains.csv"
        master.write_text("train_symbol,train_name,engine,font,runs_job,opspro_name,notes\n"
                          'X1,Extra 1,42,East,true,Extra One,"a note, with a comma"\n', encoding="utf-8")
        self.assertEqual(self.mod.build(master),
                         "train_name,train_symbol,engine,font,runs_job,notes\n"
                         'Extra 1,X1,42,East,true,"a note, with a comma"\n')

    def test_a_missing_column_is_an_error(self) -> None:
        master = self.dir / "trains.csv"
        master.write_text("train_symbol,train_name\nX1,Extra 1\n", encoding="utf-8")
        self.assertRaisesRegex(SystemExit, "no column engine", self.mod.build, master)

    def test_check_fails_on_a_stale_file_and_a_build_fixes_it(self) -> None:
        out = self.dir / "hart_trains.csv"
        out.write_text("stale\n", encoding="utf-8")
        master = self.dir / "trains.csv"
        master.write_bytes(self.mod.MASTER.read_bytes())
        with mock.patch.object(self.mod, "OUT", out), mock.patch.object(self.mod, "MASTER", master):
            self.assertEqual(self.mod.main(["--check"]), 1)
            self.assertEqual(self.mod.main([]), 0)
            self.assertEqual(self.mod.main(["--check"]), 0)
        self.assertEqual(out.read_bytes(), self.mod.OUT.read_bytes())


if __name__ == "__main__":
    unittest.main()
