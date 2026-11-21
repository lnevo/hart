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

from hartlib import devices  # noqa: E402
from hartlib.railroad import DEVICE_COLUMNS, FactsError  # noqa: E402


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AM = load("add_main_upper_levels", "tools/wiring/add_main_upper_levels.py")
RW = load("refresh_wiring_docs", "tools/wiring/refresh_wiring_docs.py")


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
        """The reader gives the main and upper rows of devices.csv, in the device-map form, checked against a plain read."""
        rows = AM.read_device_rows()
        master = plain(devices.Files.here().master)
        want = [r for r in master if r["level"] in ("2", "3") and r["role"] not in devices.OUT_OF_MAPS]
        self.assertTrue(rows)
        self.assertEqual({lv: sum(1 for r in rows if r["level"] == lv) for lv in ("2", "3")},
                         {lv: sum(1 for r in want if r["level"] == lv) for lv in ("2", "3")})
        self.assertEqual({r["level"] for r in rows}, {"2", "3"})
        self.assertEqual([r["user_name"] for r in rows], [r["user_name"] for r in want])
        turnout = next(r for r in want if r["layer"] == "turnout" and r["role"] == "turnout")
        got = next(r for r in rows if r["layer"] == "turnout" and r["user_name"] == turnout["user_name"])
        self.assertEqual((got["jmri_name"], got["system_name"]), (turnout["jmri_name"], turnout["system_name"]))
        self.assertTrue(got["jmri_name"].startswith("IT:HART:C3:"))

    def test_the_nodes(self) -> None:
        rows = AM.read_node_rows()                  # the main and upper rows; staging's are v85's own
        self.assertTrue(rows)
        self.assertEqual(rows, [r for r in plain(AM.NODES) if r["level"] in AM.LEVEL_NAME])

    def test_the_occupancy_bindings(self) -> None:
        got = RW.occupancy_by_hw()
        rows = [r for r in plain(RW.CATS / "occupancy_bindings.csv")
                if r["occupancy_sensor_user_name"] and r["block_user_name"]]
        self.assertTrue(got)
        self.assertEqual(set(got), {r["occupancy_sensor_user_name"] for r in rows})
        self.assertTrue(all(got.values()))


class BadHeader(Case):
    """A header without a column the script reads stops the read, naming the file and the column."""

    def test_the_master_needs_every_column_the_loader_holds(self) -> None:
        """hartlib.devices is the one reader of the master and holds its whole header: a column gone stops the read."""
        for column in ("level", "layer", "user_name", "system_name", "node", "wiring", "trial_name", "notes"):
            with self.subTest(column), self.assertRaisesRegex(FactsError, "the header is not the master's columns"):
                AM.read_device_rows(self.without(AM.DEVICE_MAP, column))
        with self.assertRaisesRegex(FactsError, "cannot read it"):
            AM.read_device_rows(self.tmp / "missing.csv")

    def test_the_nodes(self) -> None:
        for column in ("level", "area", "node"):
            with self.subTest(column):
                self.stops(AM.read_node_rows, AM.NODES, column)
        self.assertEqual(len(AM.read_node_rows(self.without(AM.NODES, "source"))),
                         len([r for r in plain(AM.NODES) if r["level"] in AM.LEVEL_NAME]))

    def test_the_occupancy_bindings(self) -> None:
        for column in ("block_user_name", "occupancy_sensor_user_name"):
            with self.subTest(column):
                self.stops(RW.occupancy_by_hw, RW.CATS / "occupancy_bindings.csv", column)

    def test_a_node_level_that_is_no_level_stops(self) -> None:
        bad = self.tmp / "nodes.csv"
        bad.write_text(AM.NODES.read_text(encoding="utf-8") + "4,North,62,\n", encoding="utf-8")
        with self.assertRaisesRegex(FactsError, r"nodes.csv line \d+: level is 1, 2 or 3, not '4'"):
            AM.read_node_rows(bad)

    def test_the_staging_nodes_match_the_inventory(self) -> None:
        from openpyxl import load_workbook
        wb = load_workbook(AM.SRC)
        AM.check_staging_nodes(wb)                                    # the committed file
        for old, new, msg in (("1,Helix,11,", "", r"missing \[11\], extra \[\]"),
                              ("1,West,13,", "1,West,13,\n1,West,16,", r"missing \[\], extra \[16\]")):
            with self.subTest(msg=msg):
                bad = self.tmp / "nodes.csv"
                text = AM.NODES.read_text(encoding="utf-8")
                line = next(l for l in text.splitlines() if l.startswith(old))
                bad.write_text(text.replace(line + "\n", (new + line[len(old):] + "\n") if new else ""),
                               encoding="utf-8")
                with self.assertRaisesRegex(FactsError, msg):
                    AM.check_staging_nodes(wb, bad)

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


if __name__ == "__main__":
    unittest.main()
