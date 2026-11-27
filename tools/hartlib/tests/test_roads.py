"""hartlib.operations.read_roads and read_loco_models, the one reader of roads.csv and loco_models.csv: the lookups
the car pipeline used to type in engine_lookup.py and process_car_images.py, built from the rows, with a bad row
stopped at its line."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src")]
from hartlib import operations as roads  # noqa: E402
from hartlib.operations import RoadsError  # noqa: E402

HEADER = "road,marks,car_spellings,engine_spellings,notes\n"


class Roads(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_rows_give_the_lookups(self):
        r = roads.read_roads(self.write("roads.csv", HEADER + "BO,B&O,BO;B&O;B O,B&O,\nCR,,,CR;CONRAIL,\nNWR,,,,a note\n"))
        self.assertEqual(r.codes, ("BO", "CR", "NWR"))
        self.assertEqual(r.display, {"BO": "B&O"})                # no marks: not in display, so a card shows the code
        self.assertEqual(r.car_aliases, {"BO": "BO", "B&O": "BO", "B O": "BO"})
        self.assertEqual(r.engine_aliases, {"B&O": "BO", "CR": "CR", "CONRAIL": "CR"})

    def test_bad_rows_name_the_line(self):
        for body, said in (("BO,B&O,,,\nBO,,,,\n", ":3: road BO is listed twice"),
                           (",B&O,,,\n", ":2: road is empty"),
                           ("BO,,B&O,,\nCO,,B&O,,\n", ":3: car_spellings 'B&O' is already road BO's"),
                           ("ATSF,,Santa Fe,,\n", ":2: car_spellings 'Santa Fe' must be in capitals ('SANTA FE')")):
            with self.assertRaises(RoadsError) as cm:
                roads.read_roads(self.write("roads.csv", HEADER + body))
            self.assertIn(said, str(cm.exception))
        with self.assertRaises(RoadsError):
            roads.read_roads(self.write("roads.csv", "road,marks\nBO,B&O\n"))   # a required column is missing

    def test_models_keep_file_order(self):
        models = roads.read_loco_models(self.write("m.csv", "model,mfg\nGP38,EMD\nU30B,GE\nGP20,EMD\n"))
        self.assertEqual(list(models.items()), [("GP38", "EMD"), ("U30B", "GE"), ("GP20", "EMD")])
        with self.assertRaises(RoadsError):
            roads.read_loco_models(self.write("m.csv", "model,mfg\nGP38,\n"))

    def test_the_repo_files_read(self):
        r = roads.read_roads()
        self.assertEqual(r.display["NW"], "N&W")
        self.assertEqual(r.engine_aliases["OHIO CENTRAL"], "CWRY")
        self.assertEqual(r.car_aliases["NORFOLKANDWESTERN"], "NW")
        self.assertEqual(roads.read_loco_models()["RS3"], "ALCO")


class IndustrySheet(unittest.TestCase):
    """read_industry_sheet, read_industry_notes and read_spot_usages: the operator sheet's industry tables."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_sheet_rows_in_file_order(self):
        rows = roads.read_industry_sheet(self.write("s.csv", "industry_id,sheet_name,sheet_order,waybill_order,logo,"
                                                    "logo_width\nstucki,A Stucki Co,1,1,stucki.png,1.55\n"
                                                    "shenango,Shenango Coke Works,5,,shenango.png,0.55\n"))
        self.assertEqual([(r.industry_id, r.sheet_order, r.waybill_order, r.logo_width) for r in rows],
                         [("stucki", 1, 1, 1.55), ("shenango", 5, None, 0.55)])
        for body, said in (("a,A,x,,l.png,1\n", "sheet_order 'x'"), ("a,A,0,,l.png,wide\n", "logo_width 'wide'"),
                           ("a,A,0,,l.png,1\na,B,1,,l.png,1\n", "a (B) is listed twice")):
            with self.assertRaises(roads.OpsDataError) as cm:
                roads.read_industry_sheet(self.write("s.csv", "industry_id,sheet_name,sheet_order,waybill_order,logo,"
                                                     "logo_width\n" + body))
            self.assertIn(said, str(cm.exception))

    def test_notes_by_line_and_usages(self):
        notes = roads.read_industry_notes(self.write("n.csv", 'industry_id,line,text\na,2,"second, with a comma"\na,1,first\n'))
        self.assertEqual(notes, {"a": ["first", "second, with a comma"]})
        with self.assertRaises(roads.OpsDataError):
            roads.read_industry_notes(self.write("n.csv", "industry_id,line,text\na,1,x\na,1,y\n"))
        self.assertEqual(roads.read_spot_usages(self.write("u.csv", "usage,label\npellet unload,Pellet Unloading\n")),
                         {"pellet unload": "Pellet Unloading"})
        with self.assertRaises(roads.OpsDataError):
            roads.read_spot_usages(self.write("u.csv", "usage,label\nPellet Unload,Pellet Unloading\n"))


if __name__ == "__main__":
    unittest.main()
