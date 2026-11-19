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
        row = "Mast 108LA,CP 107,107,Track 107 Loop 1,OS Switch 107,,{m},{h}=Head 108LA,IF$shsm:basic:one-low(IH3332)\n"
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
