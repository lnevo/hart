"""hartlib.level_masts: the main and upper heads' virtual names come from their user names alone."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import level_masts as L  # noqa: E402


class HeadNameTest(unittest.TestCase):
    def test_from_the_user_name(self):
        self.assertEqual(L.head_name("Head 108LA"), "IH:HART:C3:108LA")
        self.assertEqual(L.head_name("Head 108R Top"), "IH:HART:C3:108R_Top")
        self.assertEqual(L.head_name("Head 226RB Bottom"), "IH:HART:C3:226RB_Bottom")
        for bad in ("Head 108", "Mast 108LA", "Head 108LA Middle", "IH3332", ""):
            with self.subTest(user=bad), self.assertRaises(ValueError):
                L.head_name(bad)

    def test_level_heads_and_masts_are_never_lcos_numbers(self):
        self.assertTrue(L.is_level_head("IH:HART:C3:108R_Top"))
        for other in ("IH3332", "IH93332", "IH9990", "IH:HART:C3:X"):
            self.assertFalse(L.is_level_head(other), other)
        mast = "IF$shsm:basic:two-searchlight(IH:HART:C3:108R_Top)(IH:HART:C3:108R_Bottom)"
        self.assertEqual(L.mast_heads(mast), ["IH:HART:C3:108R_Top", "IH:HART:C3:108R_Bottom"])
        self.assertTrue(L.is_level_mast(mast))
        self.assertFalse(L.is_level_mast("IF$shsm:basic:one-low(IH432)"))

    def test_read_checks_each_head_against_its_user_name(self):
        head = "IF$shsm:basic:one-low({h})"
        row = "Mast 108LA,CP 107,107,Track 107 Loop 1,OS Switch 107,west,,{m},{h}=Head 108LA,IF$shsm:basic:one-low(IH3332)\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.csv"
            for h, ok in (("IH:HART:C3:108LA", True), ("IH:HART:C3:108LB", False), ("IH3332", False)):
                path.write_text(",".join(L.FIELDS) + "\n" + row.format(m=head.format(h=h), h=h), encoding="utf-8")
                with self.subTest(head=h):
                    if ok:
                        self.assertEqual(L.read(path)[0]["heads"], [(h, "Head 108LA")])
                    else:
                        with self.assertRaises(ValueError):
                            L.read(path)

    def test_read_checks_the_header_and_each_mast_once(self):
        """A missing column, a row longer than the header and a mast named twice stop with the file and the line; a
        column the file adds beyond FIELDS is left out."""
        from hartlib.railroad import FactsError
        mast = "Mast 108LA,CP 107,107,Track 107 Loop 1,OS Switch 107,west,,IF$shsm:basic:one-low(IH:HART:C3:108LA)," \
               "IH:HART:C3:108LA=Head 108LA,\n"
        other = mast.replace("108LA", "108LB")
        header = ",".join(L.FIELDS) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.csv"

            def stops(text: str, message: str) -> None:
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(FactsError) as stop:
                    L.read(path)
                self.assertEqual(str(stop.exception), message)

            path.write_text(header + mast + other, encoding="utf-8")
            self.assertEqual([r["mast"] for r in L.read(path)], ["Mast 108LA", "Mast 108LB"])
            no_leg = [c for c in L.FIELDS if c != "leg"]
            stops(",".join(no_leg) + "\n" + mast.replace(",,IF$", ",IF$"),
                  f"m.csv: no column leg (the header is {','.join(no_leg)})")
            stops(header + mast + other.replace(",\n", ",,stray\n"),
                  f"m.csv line 3: 10 fields ({','.join(L.FIELDS)}), not 11")
            stops(header + mast + other + mast, "m.csv line 4: mast Mast 108LA is on line 2 already")
            # a short row is a damaged file: it stops like a long one, however many fields it lost
            stops(header + mast + other.replace(",\n", "\n"), f"m.csv line 3: 10 fields ({','.join(L.FIELDS)}), not 9")
            stops(header + mast + "Mast 108LB,CP 107\n", f"m.csv line 3: 10 fields ({','.join(L.FIELDS)}), not 2")
            # a dir that is missing or not east or west stops, whatever the name says
            for bad in ("", "up", "West"):
                stops(header + mast.replace(",west,", f",{bad},"),
                      f"m.csv line 2: mast Mast 108LA: dir {bad!r} is not one of east, west")
            # a row with no mast name, empty or blank
            for blank in ("", "  "):
                stops(header + mast + other.replace("Mast 108LB", blank), "m.csv line 3: no mast name")
            stops(header + mast + other.replace("=Head 108LB", "=Head 108LA"),
                  "m.csv line 3: mast Mast 108LB: heads 'IH:HART:C3:108LB=Head 108LA' are not system=user pairs of "
                  "its system name's virtual heads")
            # a column beyond FIELDS is allowed and left out of the rows; the checks still run
            more = header.replace("\n", ",remark\n")
            path.write_text(more + mast.replace(",\n", ",,spare\n"), encoding="utf-8")
            self.assertEqual(set(L.read(path)[0]), set(L.FIELDS) | {"heads"})
            stops(more + mast.replace(",\n", ",,spare\n") + mast.replace(",\n", ",,x\n"),
                  "m.csv line 3: mast Mast 108LA is on line 2 already")
            with self.assertRaisesRegex(FactsError, "none.csv: cannot read it"):
                L.read(Path(tmp) / "none.csv")

    def test_read_carries_the_dir_column_even_when_the_name_says_otherwise(self):
        """A mast named like an L mast (westbound by ADR-005) that the file gives east is east: the reader never
        reads the name for it."""
        mast = "Mast 108LA,CP 107,107,Track 107 Loop 1,OS Switch 107,east,,IF$shsm:basic:one-low(IH:HART:C3:108LA)," \
               "IH:HART:C3:108LA=Head 108LA,\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.csv"
            path.write_text(",".join(L.FIELDS) + "\n" + mast, encoding="utf-8")
            self.assertEqual(L.read(path)[0]["dir"], "east")

    def test_the_committed_file(self):
        """One row per main or upper mast in the released tables (44 since the 2026-11-19 plan), by system name."""
        from hartlib import tables
        rows = L.read()
        self.assertTrue(all(L.is_level_mast(r["system_name"]) for r in rows))
        released = {tables.system_name(m) for m in tables.read().iter("signalmast")}
        self.assertEqual(sorted(r["system_name"] for r in rows),
                         sorted(m for m in released if L.is_level_mast(m)))
        self.assertGreater(len(rows), 40)


if __name__ == "__main__":
    unittest.main()
