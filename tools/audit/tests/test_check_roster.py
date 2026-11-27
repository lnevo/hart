"""tools/ops/check_roster.py: the DecoderPro roster master and its link to locos.csv (lane N8, ADR-039 amendment
2026-11-26). Each problem it names, --write filling the two address columns from the roster, and the repo passing.
Every case runs on copies in a temporary folder."""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("check_roster", ROOT / "tools/ops/check_roster.py")
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.roster = self.tmp / "roster"
        shutil.copytree(C.ROSTER, self.roster)
        self.locos_csv = self.tmp / "locos.csv"
        shutil.copy2(C.MASTER, self.locos_csv)

    def run_check(self, write: bool = False) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.run(write, self.roster, self.locos_csv)
        return rc, out.getvalue()

    def edit_index(self, old: str, new: str) -> None:
        idx = self.roster / "roster.xml"
        text = idx.read_text(encoding="utf-8")
        self.assertIn(old, text)
        idx.write_text(text.replace(old, new, 1), encoding="utf-8")

    def rows(self) -> dict[str, dict]:
        with self.locos_csv.open(newline="", encoding="utf-8") as fh:
            return {r["roster_id"]: r for r in csv.DictReader(fh)}

    def set_row(self, rid: str, **fields: str) -> None:
        header, rows = C.read_master(self.locos_csv)
        for r in rows:
            if r["roster_id"] == rid:
                r.update(fields)
        C.locos.write_table(self.locos_csv, header, rows)


class RepoPasses(unittest.TestCase):
    def test_the_repo_master_and_locos_csv_agree(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.run(False)
        self.assertEqual(0, rc, out.getvalue())


class Problems(Fixture):
    def test_a_missing_dcc_address_fails(self) -> None:
        self.edit_index('dccAddress="2121"', 'dccAddress=""')
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("CSX 2121: no dccAddress", out)
        self.assertNotIn("not named by roster.xml", out, "review finding 5: its own file is named, not a stray")

    def test_a_dcc_address_that_is_not_a_number_fails(self) -> None:
        self.edit_index('dccAddress="2121"', 'dccAddress="21x"')
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("is not a whole number", out)

    def test_a_roster_id_locos_csv_lacks_fails(self) -> None:
        self.set_row("CSX 2121", roster_id="CSX 9999")
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("CSX 2121: no locos.csv row has this roster_id", out)

    def test_another_dcc_address_in_locos_csv_fails(self) -> None:
        self.set_row("BO 572", dcc_address="57")
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("BO 572: dcc_address '57', the roster's is '572'", out)

    def test_an_entry_file_with_another_address_fails(self) -> None:
        entry = self.roster / "roster/2121.xml"
        entry.write_text(entry.read_text(encoding="utf-8").replace('number="2121"', 'number="2122"'), encoding="utf-8")
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("2121.xml: <dcclocoaddress> number '2122'", out)

    def test_a_short_address_in_the_roster_is_compared_with_locos_csv(self) -> None:
        entry = self.roster / "roster/2121.xml"
        entry.write_text(entry.read_text(encoding="utf-8").replace('longaddress="yes"', 'longaddress="no"'),
                         encoding="utf-8")
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("CSX 2121: long_address 'yes', the roster's is 'no'", out)

    def test_a_longaddress_other_than_yes_or_no_fails(self) -> None:
        entry = self.roster / "roster/2121.xml"
        entry.write_text(entry.read_text(encoding="utf-8").replace('longaddress="yes"', 'longaddress="maybe"'),
                         encoding="utf-8")
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("2121.xml: <dcclocoaddress> number '2121', longaddress 'maybe'", out)

    def test_a_missing_entry_file_fails(self) -> None:
        (self.roster / "roster/2121.xml").unlink()
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("2121.xml: missing (named by CSX 2121 in roster.xml)", out)

    def test_a_backup_or_old_file_in_the_master_fails(self) -> None:
        (self.roster / "roster/2121.xml.bak").write_text("backup")
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("2121.xml.bak: not named by roster.xml", out)

    def test_an_index_that_does_not_parse_is_a_clear_failure(self) -> None:
        (self.roster / "roster.xml").write_text("<roster-config>", encoding="utf-8")
        rc, out = self.run_check()
        self.assertEqual(1, rc)
        self.assertIn("roster.xml: does not parse", out)


class Write(Fixture):
    def test_write_fills_the_addresses_from_the_roster_and_is_idempotent(self) -> None:
        self.set_row("BO 572", dcc_address="", long_address="")
        self.set_row("NWR 06", dcc_address="", long_address="")
        rc, out = self.run_check(write=True)
        self.assertEqual(0, rc, out)
        self.assertIn("2 locos.csv row(s) took the roster's address", out)
        self.assertEqual(("572", "yes"), (self.rows()["BO 572"]["dcc_address"], self.rows()["BO 572"]["long_address"]))
        self.assertEqual("6", self.rows()["NWR 06"]["dcc_address"], "the roster's address, not the road number 06")
        before = self.locos_csv.read_bytes()
        rc, out = self.run_check(write=True)
        self.assertEqual(0, rc, out)
        self.assertIn("0 locos.csv row(s)", out)
        self.assertEqual(before, self.locos_csv.read_bytes())

    def test_write_leaves_a_loco_the_roster_lacks(self) -> None:
        """An intake loco keeps the address bin/cars locos publish will send to DecoderPro."""
        header, rows = C.read_master(self.locos_csv)
        rows.append({**{h: "" for h in header}, "roster_id": "ZZ 1", "road_name": "ZZ", "road_number": "1",
                     "dcc_address": "1", "loco_type": "Diesel"})
        C.locos.write_table(self.locos_csv, header, rows)
        rc, out = self.run_check(write=True)
        self.assertEqual(0, rc, out)
        self.assertEqual("1", self.rows()["ZZ 1"]["dcc_address"])

    def test_write_on_a_broken_roster_writes_nothing(self) -> None:
        self.edit_index('dccAddress="2121"', 'dccAddress=""')
        self.set_row("BO 572", dcc_address="")
        before = self.locos_csv.read_bytes()
        rc, out = self.run_check(write=True)
        self.assertEqual(1, rc)
        self.assertIn("locos.csv was not written", out)
        self.assertEqual(before, self.locos_csv.read_bytes())


if __name__ == "__main__":
    unittest.main()
