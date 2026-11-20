"""hartlib.railroad_facts.station_group_rows: staging's control points in the older control_points.csv shape, built
from control_points_staging.csv and switch_legs.csv (level-unification step 8)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import paths, railroad_facts as rf  # noqa: E402

CPS = paths.LAYOUT_DATA / "schematic" / "control_points_staging.csv"
LEGS = paths.LAYOUT_DATA / "switch_legs.csv"
HEAD = "cp_id,cp_name,level,switches,area,code,notes\n"
LEGS_HEAD = "switch,os_block\n"


class StationGroups(unittest.TestCase):
    def files(self, cps: str, legs: str) -> tuple[Path, Path]:
        d = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (d / "cps.csv").write_text(HEAD + cps)
        (d / "legs.csv").write_text(LEGS_HEAD + legs)
        return d / "cps.csv", d / "legs.csv"

    def test_the_repo_rows(self):
        rows = {r["cp_name"]: r for r in rf.station_group_rows(CPS, LEGS)}
        self.assertEqual(rows["East End"]["switches"].split(",")[:2], ["25", "27"])
        self.assertIn("23a", rows["East End"]["switches"].split(","))
        self.assertEqual(rows["Barn"]["switches"], "7,7b")
        self.assertEqual(rows["Engine House"]["cp_id"], "engine_house")
        self.assertEqual({r["level"] for r in rows.values()}, {"1"})

    def test_a_crossover_is_listed_by_its_halves_in_order(self):
        cps, legs = self.files('cp_xx,X Y,1,"7,5",X,XX,n\n', "7,OS Switch 7b\n7,OS Switch 7\n5,OS Switch 5\n")
        self.assertEqual(rf.station_group_rows(cps, legs),
                         [dict(cp_id="x_y", cp_name="X Y", level="1", switches="7,7b,5", notes="n", code="XX")])

    def test_errors_name_the_file_and_line(self):
        cps, legs = self.files("cp_xx,X,,5,X,XX,\n", "5,OS Switch 5\n")
        with self.assertRaisesRegex(rf.FactsError, r"cps.csv line 2 \(X\): no level"):
            rf.station_group_rows(cps, legs)
        cps, legs = self.files("cp_xx,X,1,9,X,XX,\n", "5,OS Switch 5\n")
        with self.assertRaisesRegex(rf.FactsError, r"cps.csv line 2 \(X\): switch 9 has no OS block in legs.csv"):
            rf.station_group_rows(cps, legs)
        cps, legs = self.files("cp_xx,X,1,5,X,XX,\n", "5,Track 5\n")
        with self.assertRaisesRegex(rf.FactsError, r"legs.csv line 2: 'Track 5' is not an OS Switch block"):
            rf.station_group_rows(cps, legs)


if __name__ == "__main__":
    unittest.main()
