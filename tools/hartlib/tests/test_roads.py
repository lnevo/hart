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
                           ("BO,,B&O,,\nCO,,B&O,,\n", ":3: car_spellings 'B&O' is already road BO's")):
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


if __name__ == "__main__":
    unittest.main()
