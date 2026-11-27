"""hartlib.hand_tables: the railroad's names come from the key and name columns of each CSV master in entities.csv
(items of a cell split, plain values left out), and hand_tables.csv is read row by row and written back sorted."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src")]
from hartlib import hand_tables  # noqa: E402
from hartlib.hand_tables import HandTablesError, Listed  # noqa: E402


class Names(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_key_and_name_columns_of_csv_masters(self):
        entities = self.write("e.csv", "kind,key,master\ntrain,train_symbol,t.csv\nspot,industry_id + spot number,"
                                       "s.csv\npage,path,p.json (a note)\n")
        self.write("t.csv", "train_symbol,train_name,engine\nD749,Neville Turn,1993\nX,Extra;Work Train,7\n")
        self.write("s.csv", "industry_id,Spot #,Usage\naristech,12,coal\n")
        self.write("p.json", "{}")
        names = hand_tables.railroad_names(entities, self.root)
        self.assertEqual(names["D749"], "train (t.csv)")
        self.assertIn("Work Train", names)               # a cell's items are split
        self.assertNotIn("X", names)                     # too plain alone
        self.assertNotIn("1993", names)                  # engine is not a name column
        self.assertIn("aristech", names)                 # a word of the key cell
        self.assertNotIn("coal", names)
        self.assertEqual(hand_tables.masters(entities, self.root)[0][0], "train")

    def test_listed_rows_read_and_write(self):
        path = self.write("h.csv", "file,table,entries,status,reason\nb.py,B,4,keep,\"why, with a comma\"\n"
                                   "a.py,A,5,move,stations\n")
        rows = hand_tables.read_listed(path)
        self.assertEqual(rows[("b.py", "B")], Listed("b.py", "B", 4, "keep", "why, with a comma"))
        hand_tables.write_listed(path, rows.values())
        self.assertTrue(path.read_text().splitlines()[1].startswith("a.py,A,5"))
        self.assertEqual(hand_tables.read_listed(path), rows)

    def test_bad_rows_name_the_line(self):
        for body, said in (("a.py,A,x,move,r\n", "entries 'x'"), ("a.py,A,4,move,\n", "a reason is needed"),
                           ("a.py,A,4,move,r\na.py,A,4,keep,r\n", ":3: a.py A is listed twice")):
            path = self.write("h.csv", "file,table,entries,status,reason\n" + body)
            with self.assertRaises(HandTablesError) as cm:
                hand_tables.read_listed(path)
            self.assertIn(said, str(cm.exception))
        with self.assertRaises(HandTablesError):
            hand_tables.read_listed(self.write("h.csv", "file,table\n"))


if __name__ == "__main__":
    unittest.main()
