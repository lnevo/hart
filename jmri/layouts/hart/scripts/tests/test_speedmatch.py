"""Speed-match tools (jmri/layouts/hart/scripts/speedmatch/): stop rule, block selection,
direction keying, comparison, preflight compare and the table correction.

The 2026-11-08 block transits (docs/jmri/speedmatching/profile-2026-11-08/block_events.csv)
are turned back into runner logs and analysed. Nothing here touches hardware, MQTT or the
network, and the Jython files are only read as text.
"""
from __future__ import annotations

import ast
import csv
import json
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SM = ROOT / "jmri/layouts/hart/scripts/speedmatch"
EVENTS = ROOT / "docs/jmri/speedmatching/profile-2026-11-08/block_events.csv"
sys.path.insert(0, str(SM))
import analyze  # noqa: E402
import correct  # noqa: E402
import liverule as lr  # noqa: E402
import make_job  # noqa: E402
import preflight_compare as pc  # noqa: E402


def sensor(block: str) -> str:
    return "BS " + block


def synth_log(log_name: str, loco: str, direction: str, warmup: bool = True) -> list[str]:
    """A runner log rebuilt from the 2026-11-08 block transits of one run."""
    rows = [r for r in csv.DictReader(open(EVENTS)) if r["log"] == log_name]
    by_step = defaultdict(set)
    for r in rows:
        by_step[int(r["step"])].update([(float(r["entry_epoch"]), sensor(r["block"]))])
        # the next block is entered at next_entry_epoch; its name is not in the row, so the
        # next row of the same lap supplies it (entry of the following transit)
    lines = ["1.0 RUN loco=%s direction=%s" % (loco, direction)]
    if warmup:
        lines += ["2.0 WARMUP 64 laps=3", "3.0 SENS BS Main West ACTIVE", "3.5 SENS BS Main West INACTIVE",
                  "4.0 WARMUP_DONE"]
    for step in sorted(by_step):
        ev = sorted(by_step[step])
        lines.append("%.3f STEP %d" % (ev[0][0] - 1, step))
        for t, s in ev:
            lines.append("%.3f SENS %s ACTIVE" % (t, s))
            lines.append("%.3f SENS %s INACTIVE" % (t + 0.2, s))
    return lines


def nominal_lengths() -> dict[str, float | None]:
    out: dict = {s: None for s in analyze.ORDER}
    for r in csv.DictReader(open(EVENTS)):
        out[sensor(r["block"])] = float(r["block_len_mm"])
    return out


class LogsFromBeforeTheRename(unittest.TestCase):
    """Logs recorded before 2026-11-13 call the extension tracks BS East Main Ext / BS West Main Ext."""

    def test_old_sensor_names_read_as_the_new_ones(self):
        lines = [
            "1000.000 RUN loco=2121 direction=forward",
            "1000.100 STEP 8",
            "1001.000 SENS BS East Main Ext ACTIVE",
            "1002.000 SENS BS West Main Ext ACTIVE",
        ]
        runs = analyze.parse_log(lines)
        self.assertEqual([n for _, n in runs[0]["steps"][0]["events"]], ["BS East Ext", "BS West Ext"])
        self.assertEqual(lr.current_names("BLOCK 8 block=BS_East_Main_Ext mm=1"), "BLOCK 8 block=BS_East_Ext mm=1")


class StopRule(unittest.TestCase):
    def test_median_and_stdev(self):
        self.assertEqual(lr.median([3, 1, 2]), 2)
        self.assertEqual(lr.median([4, 1, 2, 3]), 2.5)
        self.assertAlmostEqual(lr.stdev([2, 4, 4, 4, 5, 5, 7, 9]), 2.138, 3)
        self.assertEqual(lr.stdev([5]), 0.0)

    def test_settled_needs_k_readings_under_the_limit(self):
        self.assertFalse(lr.settled([100, 100, 100, 100], k=5))
        self.assertTrue(lr.settled([100, 101, 99, 100, 100], k=5, rel=0.02))
        self.assertFalse(lr.settled([100, 110, 90, 100, 100], k=5, rel=0.02))

    def test_only_the_last_k_count(self):
        vals = [10, 300, 50] + [100, 100.5, 99.5, 100, 100.2]
        self.assertTrue(lr.settled(vals, k=5, rel=0.02))

    def test_max_readings_moves_on(self):
        noisy = [100, 140, 70, 130, 80, 120, 90, 110]
        self.assertEqual(lr.should_move_on(noisy[:7], 5, 0.02, 8), (False, ""))
        self.assertEqual(lr.should_move_on(noisy, 5, 0.02, 8), (True, "max"))
        self.assertEqual(lr.should_move_on([100] * 5, 5, 0.02, 8), (True, "settled"))

    def test_replay_stops_where_the_runner_stopped(self):
        vals = [80, 120, 100, 100.2, 99.8, 100.1, 99.9, 100.0, 55]
        used, why, window = lr.replay(vals, 5, 0.02, 12)
        self.assertEqual((used, why), (7, "settled"))
        self.assertEqual(window, [100, 100.2, 99.8, 100.1, 99.9])
        used, why, _ = lr.replay([80, 120, 90], 5, 0.02, 12)
        self.assertEqual((used, why), (3, ""))

    def test_low_steps_use_every_block_high_steps_longer_spans(self):
        self.assertEqual(lr.span_for_step(2), 1)
        self.assertEqual(lr.span_for_step(48), 1)
        self.assertEqual(lr.span_for_step(64), lr.HIGH_SPAN)
        self.assertEqual(lr.span_for_step(64, high_span=2), 2)


class Spans(unittest.TestCase):
    order = ["A", "B", "C", "D", "E"]
    lengths = {"A": 100.0, "B": 200.0, "C": None, "D": 400.0, "E": 500.0}

    def test_one_block_either_way_round(self):
        east = lr.span_speed([(0, "A"), (10, "B")], self.order, self.lengths, 1)
        west = lr.span_speed([(0, "B"), (10, "A")], self.order, self.lengths, 1)
        self.assertEqual(east[:2], (10.0, 10))
        self.assertEqual(west[:2], (20.0, 10))
        self.assertEqual(lr.span_speed([(0, "E"), (10, "A")], self.order, self.lengths, 1)[2], 500.0)

    def test_span_sums_the_blocks_entered(self):
        r = lr.span_speed([(0, "D"), (5, "E"), (10, "A"), (20, "B")], self.order, self.lengths, 3)
        self.assertEqual(r[2], 400 + 500 + 100)
        self.assertEqual(r[0], 1000 / 20.0)

    def test_untrusted_block_or_a_gap_gives_nothing(self):
        self.assertIsNone(lr.span_speed([(0, "C"), (10, "D")], self.order, self.lengths, 1))
        self.assertIsNone(lr.span_speed([(0, "B"), (10, "D")], self.order, self.lengths, 1))
        self.assertIsNone(lr.span_speed([(0, "A"), (5, "B"), (10, "A")], self.order, self.lengths, 2))

    def test_reader_skips_settle_events_and_retriggers(self):
        rd = lr.SpanReader(self.order, self.lengths, settle=2)
        rd.restart(1)
        got = [rd.feed(t, s) for t, s in [(0, "A"), (1, "B"), (2, "D"), (3, "D"), (12, "E")]]
        # A and B thrown away; D starts; the retrigger of D is ignored; E ends D's span
        self.assertEqual(got[:4], [None] * 4)
        self.assertEqual(got[4][0], 400 / 10.0)

    def test_reader_falls_back_to_a_shorter_span(self):
        rd = lr.SpanReader(self.order, self.lengths, settle=0)
        rd.restart(3)  # blocks C..E would include untrusted C
        out = [rd.feed(t, s) for t, s in [(0, "C"), (5, "D"), (15, "E"), (20, "A")]]
        self.assertEqual(out[:3], [None] * 3)  # a whole span has not been seen yet
        self.assertEqual(out[3][3], 2)  # C is untrusted: D and E make the longest usable span
        self.assertEqual(out[3][0], 900 / 15.0)


class Lengths(unittest.TestCase):
    def write(self, header, rows):
        d = tempfile.mkdtemp()
        p = Path(d) / "bl.csv"
        p.write_text(",".join(header) + "\n" + "\n".join(",".join(r) for r in rows) + "\n")
        return p

    def test_basis_column_decides_when_present(self):
        p = self.write(["user_name", "occupancy_sensor", "inches", "basis", "flag"],
                       [["Track Main West", "x", "220", "anyrail", "assigned"],
                        ["Track East Lead", "x", "172", "inferred", "estimate"],
                        ["Track K-1", "x", "122.5", "", "split"],
                        ["Track K-2", "x", "122.5", "estimate", "assigned"]])
        got = analyze.load_lengths(p)
        self.assertAlmostEqual(got["BS Main West"], 220 * 25.4)
        self.assertAlmostEqual(got["BS East Lead"], 172 * 25.4)
        self.assertIsNone(got["BS K-1"])
        self.assertIsNone(got["BS K-2"])
        only = analyze.load_lengths(p, trusted=("anyrail",))
        self.assertIsNone(only["BS East Lead"])

    def test_without_basis_assigned_counts_only_when_passed(self):
        p = self.write(["user_name", "occupancy_sensor", "inches", "flag", "old_source"],
                       [["Track Main West", "x", "220", "assigned", ""],
                        ["Track Main East", "x", "185", "cut", ""],
                        ["OS Switch 1", "x", "10", "estimate", ""]])
        self.assertIsNone(analyze.load_lengths(p)["BS Main West"])
        got = analyze.load_lengths(p, trusted=("anyrail", "inferred", "assigned"))
        self.assertIsNotNone(got["BS Main West"])
        self.assertIsNone(got["BS Main East"])
        self.assertIsNone(got["BS Switch 1"])
        self.assertIsNone(got["BS K-2"])  # no row at all

    def test_flag_column_carries_the_basis_and_stubs_are_added(self):
        p = self.write(["user_name", "occupancy_sensor", "inches", "flag", "old_source"],
                       [["Track East Lead", "x", "92", "inferred", "timed share"],
                        ["Track East Lead East", "BS East Lead", "15.748", "stub",
                         "hidden throat of Track East Lead; same detector"],
                        ["Track K-2", "x", "114.5", "anyrail", ""],
                        ["Track K-1", "x", "122.5", "split", ""]])
        got = analyze.load_lengths(p)
        self.assertAlmostEqual(got["BS East Lead"], 92 * 25.4 + 400.0, places=1)
        self.assertAlmostEqual(got["BS K-2"], 114.5 * 25.4)
        self.assertIsNone(got["BS K-1"])

    def test_the_repo_csv_loads(self):
        got = analyze.load_lengths()
        self.assertEqual(set(got), set(analyze.ORDER))


class OnTheOldData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lengths = nominal_lengths()
        cls.log_2738 = synth_log("steprun_2738_b.log", "CSX 2738", "forward")
        cls.log_2121 = synth_log("steprun_2121_c.log", "CSX 2121", "forward")

    def run_of(self, lines):
        return analyze.summarize(analyze.parse_log(lines), self.lengths)

    def test_warmup_events_are_discarded(self):
        run = analyze.parse_log(self.log_2738)[0]
        self.assertEqual(run["direction"], "forward")
        self.assertNotIn("BS Main West", [s for st in run["steps"] for _, s in st["events"]][:1])
        t_warm = 3.0
        self.assertTrue(all(t > t_warm for st in run["steps"] for t, _ in st["events"]))

    def test_travel_direction_is_read_from_the_sensors(self):
        r2738 = self.run_of(self.log_2738)[("CSX 2738", "forward")]
        r2121 = self.run_of(self.log_2121)[("CSX 2121", "forward")]
        self.assertEqual({r["travel"] for r in r2738}, {"east"})
        self.assertEqual({r["travel"] for r in r2121}, {"west"})

    def test_top_step_speed_matches_the_2026_11_08_result(self):
        r2738 = {r["step"]: r for r in self.run_of(self.log_2738)[("CSX 2738", "forward")]}
        # the 2026-11-08 nominal lengths were not reliable (README), so only plausibility here
        self.assertTrue(350 < r2738[126]["median"] < 550, r2738[126]["median"])
        self.assertTrue(r2738[24]["median"] < 125)
        self.assertEqual(r2738[24]["blocks"], 1)       # low step: every block
        self.assertEqual(r2738[126]["blocks"], lr.HIGH_SPAN)  # top step: longer spans

    def test_steps_rise_with_throttle(self):
        rows = self.run_of(self.log_2738)[("CSX 2738", "forward")]
        by = {r["step"]: r["median"] for r in rows}
        self.assertLess(by[24], by[48])
        self.assertLess(by[48], by[64])

    def test_untrusted_blocks_leave_fewer_readings(self):
        full = self.run_of(self.log_2738)[("CSX 2738", "forward")]
        cut = dict(self.lengths)
        for s in analyze.ORDER:
            if "Switch" in s:
                cut[s] = None
        part = analyze.summarize(analyze.parse_log(self.log_2738), cut)[("CSX 2738", "forward")]
        self.assertLess(sum(r["n"] for r in part), sum(r["n"] for r in full))

    def test_results_are_keyed_by_loco_and_direction(self):
        lines2 = [l.replace("CSX 2121 direction=forward", "CSX 2121 direction=reverse") for l in self.log_2121]
        res = analyze.summarize(analyze.parse_log(self.log_2738 + lines2), self.lengths)
        self.assertEqual(set(res), {("CSX 2738", "forward"), ("CSX 2121", "reverse")})

    def test_older_log_needs_loco_and_direction(self):
        old = [l for l in self.log_2738 if " RUN " not in l]
        with self.assertRaises(ValueError):
            analyze.parse_log(old)
        runs = analyze.parse_log(old, "CSX 2738", "forward")
        self.assertEqual(runs[0]["loco"], "CSX 2738")


class Drift(unittest.TestCase):
    def test_repeat_of_the_top_step(self):
        rows = [{"step": 64, "occurrence": 1, "median": 400.0},
                {"step": 126, "occurrence": 1, "median": 430.0},
                {"step": 126, "occurrence": 2, "median": 421.4}]
        d = analyze.top_drift(rows)
        self.assertEqual(d["step"], 126)
        self.assertAlmostEqual(d["drift_pct"], -2.0, 1)
        self.assertIsNone(analyze.top_drift(rows[:2]))

    def test_repeat_is_labelled_and_kept_apart(self):
        lines = ["1.0 RUN loco=L direction=forward", "2.0 STEP 126", "3.0 STEP 126"]
        run = analyze.parse_log(lines)[0]
        self.assertEqual([s["occurrence"] for s in run["steps"]], [1, 2])
        row = {"step": 126, "occurrence": 2}
        self.assertEqual(analyze.step_label(row), "126#2")


class Comparison(unittest.TestCase):
    def result(self):
        def row(step, med, travel="east", occ=1):
            return {"step": step, "occurrence": occ, "median": med, "travel": travel}
        return {("CSX 2121", "forward"): [row(24, 200.0), row(48, 400.0)],
                ("CSX 2738", "reverse"): [row(24, 190.0), row(48, 404.0)],
                ("CSX 2121", "reverse"): [row(24, 210.0, "west")],
                ("CSX 2738", "forward"): [row(24, 189.0, "east")]}

    def test_the_two_consist_pairings(self):
        self.assertEqual(analyze.pairings("CSX 2121", "CSX 2738"), [
            (("CSX 2121", "forward"), ("CSX 2738", "reverse")),
            (("CSX 2121", "reverse"), ("CSX 2738", "forward"))])

    def test_compare_gives_follower_against_leader(self):
        a, b = analyze.pairings("CSX 2121", "CSX 2738")[0]
        out = analyze.compare(self.result(), a, b)
        self.assertEqual([c["step"] for c in out], [24, 48])
        self.assertAlmostEqual(out[0]["b_vs_a_pct"], -5.0)
        self.assertAlmostEqual(out[1]["b_vs_a_pct"], 1.0)
        self.assertTrue(all(c["same_travel"] for c in out))

    def test_different_physical_travel_is_flagged(self):
        a, b = analyze.pairings("CSX 2121", "CSX 2738")[1]
        self.assertFalse(analyze.compare(self.result(), a, b)[0]["same_travel"])

    def test_outputs_are_written(self):
        d = tempfile.mkdtemp()
        res = analyze.summarize(analyze.parse_log(synth_log("steprun_2738_b.log", "CSX 2738", "reverse")),
                                nominal_lengths())
        analyze.write_outputs(res, ("CSX 2121", "CSX 2738"), d)
        header = open(Path(d) / "profile.csv").readline()
        self.assertIn("median_mm_s", header)
        self.assertTrue((Path(d) / "drift.csv").exists())
        self.assertTrue((Path(d) / "compare.csv").exists())


ROSTER = """<?xml version="1.0" encoding="utf-8"?>
<locomotive-config>
  <locomotive id="CSX 2738" dccAddress="2738">
    <values>
      <decoderDef><varValue item="Speed Table" value="1,2,3"/></decoderDef>
      <CVvalue name="2" value="0"/>
      <CVvalue name="25" value="16"/>
      <CVvalue name="29" value="50"/>
      <CVvalue name="67" value="9"/>
      <CVvalue name="95" value="128"/>
    </values>
  </locomotive>
</locomotive-config>
"""


class Preflight(unittest.TestCase):
    def roster(self, text=ROSTER):
        p = Path(tempfile.mkdtemp()) / "r.xml"
        p.write_text(text)
        return p

    def test_roster_cv_values_are_read(self):
        self.assertEqual(pc.roster_cvs(self.roster()), {2: 0, 25: 16, 29: 50, 67: 9, 95: 128})
        with self.assertRaises(ValueError):
            pc.roster_cvs(self.roster(), "CSX 1")

    def test_log_lines_parse_with_failures(self):
        vals, fails = pc.parse_preflight(["1.5 PREFLIGHT CSX 2738 cvs=3", "2.0 CV 2 0", "3.0 CV 25 16",
                                          "4.0 CV 29 FAIL timeout", "5.0 END"])
        self.assertEqual(vals, {2: 0, 25: 16})
        self.assertEqual(list(fails), [29])

    def test_match_difference_failure_and_missing(self):
        roster = pc.roster_cvs(self.roster())
        rows = pc.compare({2: 0, 25: 0, 66: 1}, {29: "FAIL timeout"}, roster)
        res = {r["cv"]: r["result"] for r in rows}
        self.assertEqual(res, {2: "ok", 25: "DIFFERENT", 29: "FAILED", 66: "not in roster"})
        self.assertEqual([r["cv"] for r in pc.blocking(rows)], [25, 29])

    def test_cli_exit_status(self):
        d = Path(tempfile.mkdtemp())
        log = d / "p.log"
        log.write_text("1.0 CV 2 0\n2.0 CV 25 16\n3.0 END\n")
        ros = str(self.roster())
        self.assertEqual(pc.main(["--log", str(log), "--roster-xml", ros, "--expect", "2,25"]), 0)
        log.write_text("1.0 CV 2 0\n2.0 CV 25 15\n3.0 END\n")
        self.assertEqual(pc.main(["--log", str(log), "--roster-xml", ros, "--expect", "2,25",
                                  "--save", str(d / "o.json")]), 1)
        self.assertEqual(json.loads((d / "o.json").read_text())["read"]["25"], 15)

    def test_job_reads_the_cvs_the_plan_lists(self):
        for cv in [2, 3, 4, 5, 6, 25, 29, 66, 95] + list(range(67, 95)):
            self.assertIn(cv, make_job.BASE_CVS)
        self.assertEqual(sum(1 for c in make_job.BASE_CVS if 67 <= c <= 94), 28)


class Correction(unittest.TestCase):
    table = [round(255 * k / 28) for k in range(1, 29)]  # linear, as 2738's was

    def curve(self, table, power):
        """Fake loco: speed at a step from the table, speed = 430 * (value/255) ** power."""
        pts = [(0.0, 0.0)] + [(126.0 * (k + 1) / 28, v) for k, v in enumerate(table)]
        return {s: 430.0 * (correct.interp(float(s), pts) / 255.0) ** power for s in range(2, 127, 2)}

    def test_entry_is_scaled_by_the_measured_ratio(self):
        measured = {s: 100.0 for s in range(0, 127, 6)}
        target = {s: 120.0 for s in range(0, 127, 6)}
        rep = correct.propose([100] * 28, measured, target, tol=0.03)
        self.assertEqual(rep["values"], [120] * 28)
        self.assertFalse(rep["all_within"])

    def test_within_tolerance_leaves_the_entry_alone(self):
        flat = {s: 100.0 for s in range(0, 127, 6)}
        rep = correct.propose([50] * 28, flat, {s: 102.0 for s in flat})
        self.assertEqual(rep["values"], [50] * 28)
        self.assertTrue(rep["all_within"])

    def test_clamped_and_monotonic(self):
        table = list(range(10, 38)) + []
        measured = {s: 100.0 for s in range(0, 127, 6)}
        target = {s: (20.0 if s < 60 else 400.0) for s in range(0, 127, 6)}  # down then up
        rep = correct.propose(table, measured, target, max_ratio=100)
        v = rep["values"]
        self.assertTrue(all(1 <= x <= 255 for x in v))
        self.assertEqual(v, sorted(v))
        sat = correct.propose([250] * 28, measured, {s: 400.0 for s in measured}, max_ratio=100)
        self.assertEqual(sat["values"], [255] * 28)
        self.assertIn("reaches 255", sat["anchors"][0]["note"])

    def test_one_round_cannot_move_an_entry_more_than_max_ratio(self):
        measured = {s: 10.0 for s in range(0, 127, 6)}
        target = {s: 100.0 for s in measured}
        rep = correct.propose([40] * 28, measured, target, max_ratio=1.5)
        self.assertEqual(rep["values"], [60] * 28)

    def test_no_measurement_keeps_the_entry(self):
        rep = correct.propose([40] * 28, {}, {10: 5.0})
        self.assertEqual(rep["values"], [40] * 28)
        self.assertFalse(rep["all_within"])

    def test_wrong_table_length_is_refused(self):
        with self.assertRaises(ValueError):
            correct.propose([1] * 27, {1: 1.0}, {1: 1.0})

    def test_rounds_converge_on_a_simulated_loco(self):
        target = self.curve(self.table, 1.0)
        table = list(self.table)
        for rnd in range(1, correct.MAX_ROUNDS + 1):
            rep = correct.propose(table, self.curve(table, 1.35), target)
            st = correct.status(rep, rnd, correct.MAX_ROUNDS)
            if st == "done":
                break
            table = rep["values"]
        self.assertEqual(st, "done", (rnd, table))
        self.assertLessEqual(rnd, correct.MAX_ROUNDS)

    def test_status_stops_after_max_rounds(self):
        bad = {"all_within": False}
        self.assertEqual(correct.status(bad, 2, 5), "continue")
        self.assertEqual(correct.status(bad, 5, 5), "max_rounds")
        self.assertEqual(correct.status({"all_within": True}, 1, 5), "done")

    def test_on_the_2026_11_08_profiles(self):
        lengths = nominal_lengths()
        res = analyze.summarize(analyze.parse_log(synth_log("steprun_2738_b.log", "CSX 2738", "reverse")), lengths)
        res.update(analyze.summarize(analyze.parse_log(synth_log("steprun_2121_c.log", "CSX 2121", "forward")), lengths))
        slow = analyze.first_by_step(res[("CSX 2738", "reverse")])
        want = analyze.first_by_step(res[("CSX 2121", "forward")])
        rep = correct.propose(self.table, slow, want)
        self.assertFalse(rep["all_within"])
        self.assertEqual(rep["values"], sorted(rep["values"]))
        # 2738 ran at about half of 2121's speed at step 32, so the entries there go up
        k7 = rep["anchors"][6]
        self.assertGreater(k7["new"], k7["old"])

    def test_proposal_record_and_cli(self):
        d = Path(tempfile.mkdtemp())
        res = analyze.summarize(analyze.parse_log(synth_log("steprun_2738_b.log", "CSX 2738", "reverse")),
                                nominal_lengths())
        res.update(analyze.summarize(analyze.parse_log(synth_log("steprun_2121_c.log", "CSX 2121", "forward")),
                                     nominal_lengths()))
        for rows in res.values():
            for r in rows:
                r["reason"] = "settled"  # the old data is noisy; this test is about the record
                r["settled"] = True
        analyze.write_outputs(res, None, d)
        code = correct.main(["--table", ",".join(map(str, self.table)), "--profile", str(d / "profile.csv"),
                             "--loco", "CSX 2738", "--direction", "reverse", "--target-loco", "CSX 2121",
                             "--target-direction", "forward", "--round", "1", "--out", str(d / "p")])
        self.assertEqual(code, 2)
        prop = json.loads((d / "p" / "proposal.json").read_text())
        self.assertEqual(prop["kind"], "speed_table_proposal")
        self.assertFalse(prop["applied"])
        self.assertEqual(len(prop["new"]), 28)
        self.assertEqual(prop["cv_start"], 67)
        # the fields pom_guard.py reads: roster_id and writes of {cv, value} only
        self.assertEqual(prop["roster_id"], "CSX 2738")
        self.assertEqual(prop["writes"], [{"cv": c["cv"], "value": c["new"]} for c in prop["changes"]])
        self.assertTrue(prop["writes"])
        self.assertNotIn("address", prop)
        self.assertTrue(all(67 <= c["cv"] <= 94 for c in prop["changes"]))
        rows = list(csv.DictReader(open(d / "p" / "proposal.csv")))
        self.assertEqual(len(rows), 28)


FORBIDDEN_EVERYWHERE = ["emergencyStop", "setPower", "PowerManager", "setCommandedState", "THROWN",
                        "TurnoutManager", "sendMessage", "publish"]


def mover(name):
    """A mover as the Pi runs it: the shared jobkit.py, then the runner."""
    return (SM / "jython" / "jobkit.py").read_text() + "\n" + (SM / "jython" / name).read_text()


class JythonFiles(unittest.TestCase):
    """The scripts that run inside the Pi's JMRI are read as text, never run."""

    def text(self, name):
        return (SM / "jython" / name).read_text()

    def test_runner_never_stops_with_anything_but_its_own_throttle(self):
        src = mover("step_runner.py")
        for bad in FORBIDDEN_EVERYWHERE + ["readCV", "writeCV", "Programmer"]:
            self.assertNotIn(bad, src, bad)
        self.assertIn("setSpeedSetting(0.0)", src)
        self.assertIn("/tmp/speedrun.kill", src)
        self.assertIn("GUARD", src)
        self.assertIn("STALL0", src)

    def test_preflight_only_reads(self):
        src = self.text("preflight.py")
        for bad in FORBIDDEN_EVERYWHERE + ["writeCV", "confirmCV", "Throttle", "setSpeedSetting", "OpsMode"]:
            self.assertNotIn(bad, src, bad)
        self.assertIn("readCV", src)
        self.assertIn("service mode", src)
        self.assertIn('L("END")', src)

    def test_shared_logic_is_python_2_compatible(self):
        tree = ast.parse((SM / "liverule.py").read_text())
        for node in ast.walk(tree):
            self.assertNotIsInstance(node, (ast.JoinedStr, ast.AnnAssign, ast.AsyncFunctionDef,
                                            ast.Nonlocal, ast.Starred, ast.NamedExpr))
            if isinstance(node, ast.FunctionDef):
                self.assertIsNone(node.returns)
                self.assertTrue(all(a.annotation is None for a in node.args.args))
                self.assertFalse(node.args.kwonlyargs)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self.assertEqual([a.name for a in node.names], ["math"])
        self.assertNotIn("statistics", (SM / "liverule.py").read_text().replace("`statistics`", ""))

    def test_runner_has_no_f_strings_and_uses_jython_except_style(self):
        for name in ("step_runner.py", "preflight.py"):
            src = self.text(name)
            self.assertNotRegex(src, r"\bf[\"']")
            self.assertIn("except Exception, e", src)

    def test_job_files_carry_settings_then_shared_logic_then_runner(self):
        d = Path(tempfile.mkdtemp())
        out = d / "job.py"
        lengths = d / "bl.csv"
        lengths.write_text("user_name,occupancy_sensor,inches,flag,old_source\n"
                           "Track Main West,x,220,anyrail,\n")
        make_job.main(["steps", "--loco", "CSX 2738", "--direction", "reverse", "--out", str(out),
                       "--lengths", str(lengths), "--guard", "BS W-1"])
        text = out.read_text()
        self.assertLess(text.index("def should_move_on"), text.index("P_FWD = False"))
        self.assertLess(text.index("P_FWD = False"), text.index("class SL("))
        self.assertIn("WARM_LAPS = 3", text)
        self.assertIn("WARM_STEP = 64", text)
        self.assertIn("STEPS_LIST = [2, 4, 6, 8,", text)
        self.assertTrue(text.count("126") >= 2)
        self.assertIn("GUARD = ['BS W-1']", text)
        self.assertIn("'BS Main West': 5588.0", text)
        steps = text.split("STEPS_LIST = ")[1].split("\n")[0]
        self.assertEqual(eval(steps)[-2:], [126, 126])

    def test_forward_job_sets_the_throttle_direction(self):
        d = Path(tempfile.mkdtemp())
        lengths = d / "bl.csv"
        lengths.write_text("user_name,occupancy_sensor,inches,flag,old_source\nTrack Main West,x,220,anyrail,\n")
        make_job.main(["steps", "--loco", "CSX 2121", "--direction", "forward", "--out", str(d / "j.py"),
                       "--lengths", str(lengths), "--guard", "none"])
        self.assertIn("P_FWD = True", (d / "j.py").read_text())

    def test_a_job_with_no_trusted_lengths_is_refused(self):
        d = Path(tempfile.mkdtemp())
        lengths = d / "bl.csv"
        lengths.write_text("user_name,occupancy_sensor,inches,flag,old_source\nTrack Main West,x,220,estimate,\n")
        with self.assertRaises(SystemExit):
            make_job.main(["steps", "--loco", "CSX 2121", "--direction", "forward", "--out", str(d / "j.py"),
                           "--lengths", str(lengths), "--guard", "none"])

    def test_preflight_job_lists_the_cvs(self):
        d = Path(tempfile.mkdtemp())
        make_job.main(["preflight", "--loco", "CSX 2121", "--backemf", "tsunami2", "--out", str(d / "p.py")])
        text = (d / "p.py").read_text()
        self.assertIn("CVS = [2, 3, 4, 5, 6, 25, 29, 66, 67,", text)
        self.assertIn("209", text)


if __name__ == "__main__":
    unittest.main()
