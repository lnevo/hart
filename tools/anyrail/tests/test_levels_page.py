"""tools/anyrail/staging_run.py, engine_terminal.py and levels_page.py on the committed staging drawing
(staging_plan.svg) and the committed data (loop2_locate.csv, block_lengths.csv, block_lengths_before.csv): the run is
read off the drawing, the timed passes agree with the block lengths, and the page's tables come from the data. Where
plan 5.3b is on this machine (never in CI), the whole page is built from it."""
import csv
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import engine_terminal as ET  # noqa: E402
import levels_page as LP  # noqa: E402
import staging_run as SR  # noqa: E402

STAGING = (HERE.parent / "staging_plan.svg").read_text()
PLAN_B = Path.home() / "Documents/Layout/Lee Nevo Design Version 5.3b.any"

# The run as the page drew it before it was read from the drawing: the turnout symbol's route, then the six pieces
# from Switch 5 (cm).
OLD_RUN_ENDS = [(72.9, 636.5), (94.9, 653.9), (141.8, 666.2), (197.9, 666.3), (270.3, 593.9), (197.9, 521.5),
                (103.0, 521.5), (24.3, 442.8)]


def locate_csv(tmp, rows):
    path = Path(tmp) / "locate.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "mean_mm", "step24_mm", "step48_mm", "before_sw15_mm", "note"])
        w.writerows(rows)
    return path


class TheRunIsReadFromTheDrawing(unittest.TestCase):
    def test_the_path_passes_through_the_drawn_pieces_from_switch_5(self) -> None:
        path, pieces = SR.run_path(STAGING)
        for want in OLD_RUN_ENDS:
            self.assertIn(want, path)
        self.assertEqual(path[:2], OLD_RUN_ENDS[:2])
        self.assertEqual(path[-1], OLD_RUN_ENDS[-1])
        self.assertEqual(len(pieces), 7)       # the turnout symbol's route and the six pieces

    def test_the_curve_and_straight_are_the_ones_the_terminal_hangs_on(self) -> None:
        run_y, centre, radius, sw13 = ET.run_facts(STAGING)
        self.assertEqual((run_y, centre, radius), (521.5, (103.0, 442.8), 78.7))
        self.assertAlmostEqual(sw13[0], 31.3, delta=0.05)
        self.assertAlmostEqual(sw13[1], 475.3, delta=0.05)

    def test_the_crossover_rise_is_the_gap_to_the_loops_straight(self) -> None:
        path, pieces = SR.run_path(STAGING)
        p7 = SR.point_at(path, SR.load_locate()["7"]["mean"] / 10)
        self.assertEqual(SR.straight_at(STAGING, pieces, p7), (521.5, 6.4))

    def test_a_drawing_without_the_run_stops(self) -> None:
        with self.assertRaisesRegex(SR.RunError, "no sw7 polylines"):
            SR.run_path("<svg></svg>")

    def test_a_run_that_does_not_chain_stops_and_says_where(self) -> None:
        broken = STAGING.replace('points="141.8,666.2 139.7', 'points="141.9,666.2 139.7', 1)
        with self.assertRaisesRegex(SR.RunError, "do not chain into one run"):
            SR.run_path(broken)

    def test_no_sw5_label_stops(self) -> None:
        with self.assertRaisesRegex(SR.RunError, '"Sw 5" label'):
            SR.run_path(STAGING.replace(">Sw 5<", ">Sw 55<"))

    def test_a_curve_that_is_not_a_circle_stops(self) -> None:
        path, pieces = SR.run_path(STAGING)
        arc = pieces[-1]
        bent = [list(p) for p in arc]
        bent[len(bent) // 2][0] += 3.0
        with self.assertRaisesRegex(SR.RunError, "not a circle"):
            SR.curve_at(pieces[:-1] + [[tuple(p) for p in bent]], arc[len(arc) // 2])


class TheTimedPassesAgreeWithTheBlockLengths(unittest.TestCase):
    def test_the_committed_data_is_consistent(self) -> None:
        locate = SR.load_locate()
        SR.check_block_lengths(locate)
        self.assertEqual((locate["7"]["mean"], locate["13"]["mean"]), (4249, 5457))
        self.assertEqual((locate["7"]["before"], locate["13"]["before"]), (1660, 452))

    def test_a_mean_that_is_not_the_mean_of_its_passes_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = locate_csv(tmp, [("Switch 7", 4300, 4260, 4239, 1660, ""), ("Switch 13", 5457, 5444, 5470, 452, ""),
                                    ("Switch 7b", 3900, "", "", "", "")])
            with self.assertRaisesRegex(SR.RunError, "not the mean of its passes"):
                SR.load_locate(path)

    def test_a_distance_to_switch_15_that_does_not_match_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = locate_csv(tmp, [("Switch 7", 4249, 4260, 4239, 1700, ""), ("Switch 13", 5457, 5444, 5470, 452, ""),
                                    ("Switch 7b", 3900, "", "", "", "")])
            with self.assertRaisesRegex(SR.RunError, "does not match its mean"):
                SR.load_locate(path)

    def test_a_missing_section_or_a_number_that_is_not_one_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = locate_csv(tmp, [("Switch 7", 4249, 4260, 4239, 1660, "")])
            with self.assertRaisesRegex(SR.RunError, "no row for Switch"):
                SR.load_locate(path)
            path = locate_csv(tmp, [("Switch 7", "x", 4260, 4239, 1660, "")])
            with self.assertRaisesRegex(SR.RunError, "not a number"):
                SR.load_locate(path)
            path = locate_csv(tmp, [("Switch 9", 1, 1, 1, 1, "")])
            with self.assertRaisesRegex(SR.RunError, "is not Switch 7"):
                SR.load_locate(path)

    def test_block_lengths_that_no_longer_follow_the_passes_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(SR.BLOCK_CSV, newline="") as f:
                rows = list(csv.DictReader(f))
            for r in rows:
                if r["user_name"] == "Track Barn":
                    r["measured_in"] = "40"
            path = Path(tmp) / "block_lengths.csv"
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            with self.assertRaisesRegex(SR.RunError, r"Track Barn is 40.0 in, the timed passes give 34.1 in"):
                SR.check_block_lengths(SR.load_locate(), path)


class ThePageTablesComeFromTheData(unittest.TestCase):
    def test_the_loop_runs_from_switch_5_and_adds_up(self) -> None:
        rows = LP.loop_rows()
        self.assertEqual(len(rows), 17)
        self.assertEqual(rows[0][0], "OS Switch 5")
        self.assertFalse([r[0] for r in rows if r[0].endswith("*")])   # no hidden stubs since 2026-11-20
        self.assertAlmostEqual(sum(r[1] for r in rows), 1232.0)
        self.assertAlmostEqual(sum(r[2] for r in rows), 1382.2, places=1)
        self.assertEqual(LP.laps_note(rows), "33 timed laps (16 for East Ext)")

    def test_the_table_shows_the_totals(self) -> None:
        html = LP.block_table(LP.loop_rows())
        self.assertNotIn("hidden stubs", html)
        self.assertIn("<b>1232</b>", html)
        self.assertIn("<b>1382</b>", html)
        self.assertIn("<b>+150</b>", html)

    def test_a_loop_block_with_no_timed_spread_stops(self) -> None:
        rows = LP.block_rows()
        rows["Track K-2"] = dict(rows["Track K-2"], source="plan")
        with mock.patch.object(LP, "block_rows", return_value=rows):
            with self.assertRaisesRegex(SystemExit, "Track K-2 has no timed spread"):
                LP.loop_rows()

    def test_a_before_table_that_misses_a_block_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lines = LP.BEFORE_CSV.read_text().splitlines()
            path = Path(tmp) / "before.csv"
            path.write_text("\n".join(l for l in lines if not l.startswith("OS Switch 39,")) + "\n")
            with mock.patch.object(LP, "BEFORE_CSV", path):
                with self.assertRaisesRegex(SystemExit, "OS Switch 39"):
                    LP.loop_rows()

    def test_the_plan_version_must_look_like_one(self) -> None:
        with self.assertRaisesRegex(SystemExit, "not 'x'"):
            LP.main("a", "b", "-", "c", "d", "x")


class TheEngineTerminalIsDrawnOnTheRun(unittest.TestCase):
    def test_the_lengths_the_page_prints(self) -> None:
        info = ET.build(STAGING)[4]
        self.assertEqual({k: round(v, 1) for k, v in info["lengths_in"].items()},
                         {"13 to 11": 9.4, "11 to 9": 12.8, "EH-1": 49.3, "EH-2": 25.2, "EH-3": 25.0})
        self.assertTrue(all(math.isfinite(v) for v in info["lengths_in"].values()))


@unittest.skipUnless(PLAN_B.exists(), "the owner's plan 5.3b is not on this machine")
class TheWholePageFromPlan5_3b(unittest.TestCase):
    def test_it_builds_with_the_plan_version_printed(self) -> None:
        prototype = HERE.parent / "prototype"
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(PLAN_B, Path(tmp) / "plan.any")
            for script in ("parse1.py", "parse2.py", "graph.py"):
                subprocess.run([sys.executable, str(prototype / script), "plan.any"], cwd=tmp, check=True,
                               capture_output=True)
            out = Path(tmp) / "out"
            out.mkdir()
            subprocess.run([sys.executable, str(HERE.parent / "levels_svg.py"), "parts.json", "graph.json", str(out)],
                           cwd=tmp, check=True, capture_output=True)
            site, art = Path(tmp) / "site.html", Path(tmp) / "art.html"
            LP.main(str(out), str(HERE.parent / "staging_plan.svg"), "-", str(site), str(art), "5.3b")
            html = site.read_text()
        self.assertIn("plan version 5.3b", html)
        self.assertNotIn("@PLAN@", html)
        self.assertIn("1382 in (35,108 mm) test loop", html)
        self.assertIn("<b>4249 mm</b>", html)


if __name__ == "__main__":
    unittest.main()
