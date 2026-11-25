"""hartlib.level_masts: every level's masts in masts.csv (the level a column), their heads' internal names from their
user names and level alone, and the reader's rules."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import level_masts as L  # noqa: E402

NO_PLAN = "," * (len(L.PLAN_FIELDS) - 1)          # a row's empty plan facts (main and upper)
HEADER = ",".join(L.FIELDS) + "\n"


def line(mast_columns: str, level: int = 2, plan: str = NO_PLAN) -> str:
    """A masts.csv line from the ten mast columns, its level and its plan facts."""
    return f"{level},{mast_columns},{plan}\n"


MAST = line("Mast 108LA,CP 107,107,Track 107 Loop 1,OS Switch 107,west,,IF$shsm:basic:one-low(IH:HART:C3:108LA),"
            "IH:HART:C3:108LA=Head 108LA,")
OTHER = MAST.replace("108LA", "108LB")


class HeadNameTest(unittest.TestCase):
    def test_from_the_user_name_and_level(self):
        self.assertEqual(L.head_name("Head 108LA", 2), "IH:HART:C3:108LA")
        self.assertEqual(L.head_name("Head 108R Top", 3), "IH:HART:C3:108R_Top")
        self.assertEqual(L.head_name("Head 226RB Bottom", 3), "IH:HART:C3:226RB_Bottom")
        self.assertEqual(L.head_name("Head 2L Top", 1), "IH:HART:C1:2L_Top")
        self.assertEqual(L.head_name("Head 67", 1), "IH:HART:C1:67")
        for bad, level in (("Mast 108LA", 2), ("Head 108LA Middle", 2), ("IH3332", 2), ("", 2), ("Head 2L", 4)):
            with self.subTest(user=bad, level=level), self.assertRaises(ValueError):
                L.head_name(bad, level)

    def test_level_heads_and_masts_are_never_lcos_numbers(self):
        self.assertTrue(L.is_level_head("IH:HART:C3:108R_Top"))
        for other in ("IH3332", "IH93332", "IH9990", "IH:HART:C3:X"):
            self.assertFalse(L.is_level_head(other), other)
        mast = "IF$shsm:basic:two-searchlight(IH:HART:C3:108R_Top)(IH:HART:C3:108R_Bottom)"
        self.assertEqual(L.mast_heads(mast), ["IH:HART:C3:108R_Top", "IH:HART:C3:108R_Bottom"])
        self.assertTrue(L.is_level_mast(mast))
        self.assertFalse(L.is_level_mast("IF$shsm:basic:one-low(IH432)"))


class ReadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "m.csv"

    def stops(self, text: str, message: str) -> None:
        from hartlib.railroad import FactsError
        self.path.write_text(text, encoding="utf-8")
        with self.assertRaises(FactsError) as stop:
            L.read(self.path)
        self.assertEqual(str(stop.exception), message)

    def test_read_checks_each_head_against_its_user_name_and_level(self):
        row = "Mast 108LA,CP 107,107,Track 107 Loop 1,OS Switch 107,west,,IF$shsm:basic:one-low({h}),{h}=Head 108LA," \
              "IF$shsm:basic:one-low(IH3332)"
        for h, level, refused in (("IH:HART:C3:108LA", 2, None), ("IH3332", 1, None),   # a wired head on staging
                                  ("IH:HART:C3:108LB", 2, "neither its internal name IH:HART:C3:108LA"),
                                  ("IH:HART:C1:108LA", 2, "neither its internal name IH:HART:C3:108LA"),
                                  # a head swapped in by its row: the planned physical head at its place
                                  ("IH3332", 2, None),
                                  # a wired head that is not the planned one: refused on every level
                                  ("IH4240", 2, "is the wired LCOS head 'IH4240', but a level 2 head is internal"),
                                  ("IH4240", 1, "is the wired LCOS head 'IH4240', but a level 1 head is internal")):
            text = line(row.format(h=h), level)
            if level == 1:          # staging's internal prefix, so only the wired head is tried
                text = text.replace("CP 107", "Brick")
            self.path.write_text(HEADER + text, encoding="utf-8")
            with self.subTest(head=h, level=level):
                if refused is None:
                    self.assertEqual(L.read(self.path)[0]["heads"], [(h, "Head 108LA")])
                else:
                    with self.assertRaisesRegex(ValueError, refused):
                        L.read(self.path)

    def test_levels_go_by_keyword_and_a_positional_one_is_refused(self):
        with self.assertRaisesRegex(TypeError, "takes the path, then levels= by keyword"):
            L.read((2, 3))
        with self.assertRaises(TypeError):
            L.read(self.path, (2, 3))         # levels is keyword-only

    def test_the_rows_of_the_levels_asked_for_with_level_and_line(self):
        staging = line("Mast 2R,Brick,1,Track Brick-Plane,OS Switch 1,east,,IF$shsm:basic:one-searchlight(IH:HART:C1:2R),"
                       "IH:HART:C1:2R=Head 2R,IF$shsm:basic:one-searchlight(IH:HART:C1:2R)", 1,
                       "1,1;5,Brick-Plane,181.9,0.0,e28,TOL34067")
        self.path.write_text(HEADER + staging + MAST, encoding="utf-8")
        self.assertEqual([(r["mast"], r["level"], r["line"]) for r in L.read(self.path)],
                         [("Mast 2R", 1, 2), ("Mast 108LA", 2, 3)])
        self.assertEqual([r["mast"] for r in L.read(self.path, levels=(2, 3))], ["Mast 108LA"])
        self.assertTrue(L.placed(L.read(self.path, levels=(1,))[0]))
        self.assertFalse(L.placed(L.read(self.path, levels=(2,))[0]))
        with self.assertRaisesRegex(ValueError, r"levels \[4\] are not"):
            L.read(self.path, levels=(4,))

    def test_read_checks_the_header_and_each_mast_once(self):
        """A header that is not FIELDS, a short or long row and a mast named twice (on any level) stop with the file
        and the line."""
        self.path.write_text(HEADER + MAST + OTHER, encoding="utf-8")
        self.assertEqual([r["mast"] for r in L.read(self.path)], ["Mast 108LA", "Mast 108LB"])
        no_leg = [c for c in L.FIELDS if c != "leg"]
        self.stops(",".join(no_leg) + "\n" + MAST, f"m.csv line 1: columns {','.join(no_leg)}, not {','.join(L.FIELDS)}")
        self.stops(HEADER.replace("\n", ",remark\n") + MAST,
                   f"m.csv line 1: columns {','.join(L.FIELDS)},remark, not {','.join(L.FIELDS)}")
        n = len(L.FIELDS)
        self.stops(HEADER + MAST + OTHER.replace("\n", ",stray\n"), f"m.csv line 3: {n} fields ({','.join(L.FIELDS)}), not {n + 1}")
        self.stops(HEADER + MAST + OTHER + MAST, "m.csv line 4: mast Mast 108LA is on line 2 already")
        self.stops(HEADER + MAST + MAST.replace("2,Mast", "3,Mast"), "m.csv line 3: mast Mast 108LA is on line 2 already")
        self.stops(HEADER + MAST + "2,Mast 108LB,CP 107\n", f"m.csv line 3: {n} fields ({','.join(L.FIELDS)}), not 3")
        for bad in ("", "up", "West"):
            self.stops(HEADER + MAST.replace(",west,", f",{bad},"),
                       f"m.csv line 2: mast Mast 108LA: dir {bad!r} is not east or west")
        self.stops(HEADER + MAST + OTHER.replace("Mast 108LB", ""), "m.csv line 3: mast (none): the name '' is not "
                   "Mast <number>[L|R][letter] or Mast <A|B><milepost number>")
        self.stops(HEADER + MAST.replace("2,Mast", "4,Mast"), "m.csv line 2: mast Mast 108LA: level '4' is not one of 1, 2, 3")
        self.stops(HEADER + MAST + OTHER.replace("=Head 108LB", ""),
                   "m.csv line 3: mast Mast 108LB: heads 'IH:HART:C3:108LB' are not system=user pairs of its system "
                   "name's heads")
        self.stops(HEADER + MAST.replace(NO_PLAN + "\n", "1,1;5,,x,0.0,e1,N1\n"),
                   "m.csv line 2: mast Mast 108LA: edge_cm 'x' and cm_from_toward '0.0' are not numbers")
        self.stops(HEADER + MAST.replace(NO_PLAN + "\n", "1" + NO_PLAN + "\n"),
                   "m.csv line 2: mast Mast 108LA: plan facts {'toward': '1', 'run': '', 'names': '', 'edge_cm': '', "
                   "'cm_from_toward': '', 'schematic_edge': '', 'schematic_toward_node': ''}: a row has all of them "
                   "(names may be empty) or none")
        from hartlib.railroad import FactsError
        with self.assertRaisesRegex(FactsError, "none.csv: cannot read it"):
            L.read(self.path.with_name("none.csv"))

    def test_read_carries_the_dir_column_even_when_the_name_says_otherwise(self):
        """A mast named like an L mast (westbound by ADR-005) that the file gives east is east: the reader never
        reads the name for it."""
        self.path.write_text(HEADER + MAST.replace(",west,", ",east,"), encoding="utf-8")
        self.assertEqual(L.read(self.path)[0]["dir"], "east")

    def test_read_takes_a_virtual_mast_with_no_heads_in_its_levels_thousand(self):
        from hartlib.railroad import FactsError
        ok = line("Mast 102RA,,,Track 101 Spur 1,,east,,IF$vsm:basic:one-low($2001),,IF$vsm:basic:one-low($2001)")
        self.path.write_text(HEADER + ok, encoding="utf-8")
        self.assertEqual(L.read(self.path)[0]["heads"], [])
        for bad in (ok.replace("$2001", "$1001"),                                     # staging's thousand
                    ok.replace(",,east", ",OS Switch 101,east"),                       # protects a block
                    ok.replace(",,,Track", ",,101,Track"),                             # at a switch
                    ok.replace("($2001),,", "($2001),IH:HART:C3:102RA=Head 102RA,", 1),   # with heads
                    ok.replace("($2001)," + NO_PLAN, "($2002)," + NO_PLAN)):          # another device name
            self.path.write_text(HEADER + bad, encoding="utf-8")
            with self.subTest(row=bad), self.assertRaisesRegex(FactsError, "mast Mast 102RA: virtual mast"):
                L.read(self.path)


class CommittedTest(unittest.TestCase):
    def test_the_committed_file(self):
        """One row per visible main or upper mast in the released tables (44 since the 2026-11-19 plan), by system
        name, and the virtual masts (24 since 2026-11-20); staging's 30 in the same file."""
        from hartlib import tables
        rows = L.read(levels=(2, 3))
        visible = [r for r in rows if not L.is_level_virtual(r["system_name"])]
        self.assertTrue(all(L.is_level_mast(r["system_name"]) for r in visible))
        released = {tables.system_name(m) for m in tables.read().iter("signalmast")}
        self.assertEqual(sorted(r["system_name"] for r in visible),
                         sorted(m for m in released if L.is_level_mast(m)))
        self.assertGreater(len(visible), 40)
        self.assertEqual(len(rows) - len(visible), 24)
        self.assertEqual(len(L.read(levels=(1,))), 30)

    def test_virtual_ordinals_are_by_level(self):
        self.assertEqual([L.virtual_level(f"IF$vsm:basic:one-low(${n})") for n in (1001, 2001, 2999, 3001, 4001, 1000)],
                         [1, 2, 2, 3, None, None])
        self.assertEqual(L.virtual_ordinal("IF$vsm:basic:one-low($2001)"), 2001)
        self.assertIsNone(L.virtual_ordinal("IF$shsm:basic:one-low(IH:HART:C3:2L)"))
        self.assertEqual([L.is_level_virtual(f"IF$vsm:basic:one-low(${n})") for n in (1001, 2001, 3001)],
                         [False, True, True])


if __name__ == "__main__":
    unittest.main()
