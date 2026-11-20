"""The wiring scripts' CSV readers on hartlib.railroad.read_rows: each reads the committed file as the plain reader
it replaced did, stops on a header without a column it needs, and its caller prints that instead of a traceback."""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))

from hartlib.railroad import DEVICE_COLUMNS, FactsError  # noqa: E402


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AM = load("add_main_upper_levels", "docs/wiring/scripts/add_main_upper_levels.py")
RW = load("refresh_wiring_docs", "docs/wiring/scripts/refresh_wiring_docs.py")
SP = load("sync_public_name_map", "jmri/layouts/hart/scripts/sync_public_name_map.py")


def plain(path: Path) -> list[dict[str, str]]:
    """The file as csv.DictReader gives it, values stripped: what the readers did before hartlib."""
    with path.open(newline="", encoding="utf-8") as fh:
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(fh)]


class Case(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def without(self, source: Path, column: str) -> Path:
        """A copy of `source` with one column taken out of the header and every row."""
        rows = plain(source)
        keep = [c for c in rows[0] if c != column]
        self.assertLess(len(keep), len(rows[0]), f"{source.name} has no column {column}")
        out = self.tmp / source.name
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, keep, extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        return out

    def stops(self, read, source: Path, column: str) -> None:
        with self.assertRaisesRegex(FactsError, rf"^{source.name}: no column {column} \(the header is "):
            read(self.without(source, column))


class CommittedFiles(Case):
    """Each moved reader against the committed CSV."""

    def test_the_device_map(self) -> None:
        rows = AM.read_device_rows()
        self.assertTrue(rows)
        self.assertEqual(rows, [{c: r[c] for c in DEVICE_COLUMNS} for r in plain(AM.DEVICE_MAP)])

    def test_the_nodes(self) -> None:
        rows = AM.read_node_rows()
        self.assertTrue(rows)
        self.assertEqual(rows, plain(AM.NODES))

    def test_the_name_map_for_the_wiring_docs(self) -> None:
        want = {r["current"]: r["proposed"] for r in plain(RW.PUBLIC_MAP)
                if r["current"] and r["proposed"] and r["current"] != r["proposed"]}
        self.assertEqual(RW.load_proposed(), want)
        self.assertEqual(RW._PROPOSED, want)

    def test_the_occupancy_bindings(self) -> None:
        got = RW.occupancy_by_hw()
        rows = [r for r in plain(RW.CATS / "occupancy_bindings.csv")
                if r["occupancy_sensor_user_name"] and r["block_user_name"]]
        self.assertTrue(got)
        self.assertEqual(set(got), {r["occupancy_sensor_user_name"] for r in rows})
        self.assertTrue(all(got.values()))

    def test_the_name_map_for_the_sync(self) -> None:
        rows = SP.read_old_rows()
        self.assertTrue(rows)
        self.assertEqual(rows, plain(SP.CSV_PATH))


class BadHeader(Case):
    """A header without a column the script reads stops the read, naming the file and the column."""

    def test_the_device_map_needs_every_column_the_script_reads(self) -> None:
        for column in ("level", "layer", "user_name", "system_name", "node", "comment", "trial_name"):
            with self.subTest(column):
                self.stops(AM.read_device_rows, AM.DEVICE_MAP, column)
        # notes is not read: the file may leave it out, and it reads as ""
        rows = AM.read_device_rows(self.without(AM.DEVICE_MAP, "notes"))
        self.assertEqual({r["notes"] for r in rows}, {""})
        self.assertEqual(len(rows), len(plain(AM.DEVICE_MAP)))

    def test_the_nodes(self) -> None:
        for column in ("level", "area", "node"):
            with self.subTest(column):
                self.stops(AM.read_node_rows, AM.NODES, column)
        self.assertEqual(len(AM.read_node_rows(self.without(AM.NODES, "source"))), len(plain(AM.NODES)))

    def test_the_name_map(self) -> None:
        for column in ("layer", "current", "proposed"):
            for read in (RW.load_proposed, SP.read_old_rows):
                with self.subTest(column=column, read=read.__name__):
                    self.stops(read, RW.PUBLIC_MAP, column)

    def test_the_occupancy_bindings(self) -> None:
        for column in ("block_user_name", "occupancy_sensor_user_name"):
            with self.subTest(column):
                self.stops(RW.occupancy_by_hw, RW.CATS / "occupancy_bindings.csv", column)

    def test_a_row_longer_than_the_header(self) -> None:
        bad = self.tmp / "nodes.csv"
        bad.write_text("level,area,node,source\n2,Barn,31,plan,stray\n", encoding="utf-8")
        with self.assertRaisesRegex(FactsError, r"^nodes\.csv line 2: 4 fields \(level,area,node,source\), not 5$"):
            AM.read_node_rows(bad)


class Callers(Case):
    """A file that cannot be read ends each script with one line naming the script and the fault."""
    FAULT = FactsError("some.csv: no column current (the header is layer,proposed)")

    def test_add_main_upper_levels(self) -> None:
        for argv in (["--check"], []):
            err = io.StringIO()
            with self.subTest(argv=argv), mock.patch.object(AM, "read_device_rows", side_effect=self.FAULT), \
                    mock.patch.object(AM, "OUT", self.tmp / "out.xlsx"), contextlib.redirect_stderr(err):
                self.assertEqual(AM.main(argv), 2)
            self.assertEqual(err.getvalue(), f"add_main_upper_levels.py: {self.FAULT}\n")
            self.assertFalse((self.tmp / "out.xlsx").exists())

    def test_refresh_wiring_docs(self) -> None:
        with mock.patch.object(RW, "refresh_inventory", side_effect=self.FAULT), \
                mock.patch.object(RW, "refresh_asbuilt") as asbuilt, self.assertRaises(SystemExit) as stop:
            RW.main()
        self.assertEqual(stop.exception.code, f"refresh_wiring_docs.py: {self.FAULT}")
        asbuilt.assert_not_called()

    def test_sync_public_name_map(self) -> None:
        canvas = self.tmp / "canvas.tsx"
        canvas.write_text("", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(SP, "read_old_rows", side_effect=self.FAULT), \
                mock.patch.object(SP, "parse_canvas", return_value=[]), \
                mock.patch.object(sys, "argv", ["sync_public_name_map.py", "--canvas", str(canvas)]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(SP.main(), 2)
        self.assertEqual(err.getvalue(), f"sync_public_name_map.py: {self.FAULT}\n")


if __name__ == "__main__":
    unittest.main()
