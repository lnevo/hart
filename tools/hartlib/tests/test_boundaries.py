"""hartlib.boundaries: the one reader of le_signal_boundaries.csv."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import boundaries as B  # noqa: E402

HEADER = "kind,ident,slot,mast_user_name,notes\n"


class Read(unittest.TestCase):
    def write(self, body: str, header: str = HEADER) -> Path:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        tmp = folder / "b.csv"
        tmp.write_text(header + body, encoding="utf-8")
        return tmp

    def test_committed_file(self) -> None:
        rows = B.read()
        self.assertTrue(rows)
        self.assertIn(B.Boundary("turnout", "TO1", "C", "Mast 14R", rows[[r.mast for r in rows].index("Mast 14R")].notes),
                      rows)

    def test_values_stripped(self) -> None:
        rows = B.read(self.write(" turnout , TO1 , C , Mast 14R , n \n anchor,AG6, east ,Mast 40RB,\n"))
        self.assertEqual([(r.kind, r.ident, r.slot, r.mast, r.notes) for r in rows],
                         [("turnout", "TO1", "C", "Mast 14R", "n"), ("anchor", "AG6", "east", "Mast 40RB", "")])

    def test_slot_case(self) -> None:
        rows = B.read(self.write("turnout,TO1,c,Mast 1,\nanchor,AG6,East,Mast 2,\n"))
        self.assertEqual([(r.slot, r.binding_name) for r in rows], [("C", "signalCMast"), ("east", "eastboundsignalmast")])

    def test_blank_masts_reported_once(self) -> None:
        with self.assertRaises(ValueError) as cm:
            B.read(self.write("turnout,TO1,A,,\nturnout,TO1,A,,\n"))
        self.assertNotIn("named twice", str(cm.exception))

    def test_binding_name(self) -> None:
        self.assertEqual(B.Boundary("turnout", "TO1", "c", "M").binding_name, "signalCMast")
        self.assertEqual(B.Boundary("anchor", "AG6", "East", "M").binding_name, "eastboundsignalmast")

    def test_refusals(self) -> None:
        cases = {
            "unknown kind": "block,X,A,Mast 1,\n",
            "turnout TO1 has no slot": "turnout,TO1,E,Mast 1,\n",
            "anchor AG1 has no slot": "anchor,AG1,A,Mast 1,\n",
            "named twice": "turnout,TO1,A,Mast 1,\nturnout,TO2,A,Mast 1,\n",
            "already holds": "turnout,TO1,A,Mast 1,\nturnout,TO1,A,Mast 2,\n",
            "no mast name": "turnout,TO1,A,,\n",
        }
        for want, body in cases.items():
            with self.subTest(want), self.assertRaisesRegex(ValueError, want):
                B.read(self.write(body))

    def test_missing_column(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing columns mast_user_name"):
            B.read(self.write("turnout,TO1,A\n", header="kind,ident,slot\n"))


if __name__ == "__main__":
    unittest.main()
