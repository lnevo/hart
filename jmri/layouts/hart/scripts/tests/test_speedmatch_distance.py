"""Speed-match distance mode and the pass job: the pure logic (settle time, block readings, the
step end rule), the jobs make_job.py builds, the log tags the runners emit (the contract in
docs/jmri/speedmatching/RUNBOOK.md), the analysis replay and the switch placement from passes.
Nothing here touches hardware, MQTT or the network; the Jython files are read as text."""
from __future__ import annotations

import csv
import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_speedmatch import SM, analyze, lr, make_job, mover  # noqa: E402

sys.path.insert(0, str(SM.parent))
import infer_block_lengths as ibl  # noqa: E402

RUNBOOK = SM.parents[4] / "docs/jmri/speedmatching/RUNBOOK.md"
ORDER1 = analyze.route_order("loop1")
LEN1 = {s: 1500.0 for s in ORDER1}


def steady(order, start, v, lengths, n, t0=100.0, step=1):
    """n ACTIVE events at one speed, entering the sensors of the ring in order from `start`."""
    out, t, i = [], t0, order.index(start)
    for _ in range(n):
        out.append((t, order[i]))
        t += lengths[order[i]] / v
        i = (i + step) % len(order)
    return out


def distance_log(step_events, loco="CSX 2121", direction="forward", extra_cfg=""):
    """A distance-mode runner log: step_events is [(step, [(t, sensor)])]."""
    lines = ["1.000 RUN loco=%s direction=%s" % (loco, direction),
             "1.001 CFG route=loop1 mode=distance steps=%s target_mm=6000 min_blocks=2 max_s=60 rel=0.03 "
             "warm_s=60 warm_step=48 cv3=26 cv4=24 mid=BS_Switch_23a%s" % (
                 ",".join(str(s) for s, _ in step_events), extra_cfg)]
    import json
    lines.append("1.002 LENGTHS " + json.dumps(LEN1))
    lines += ["2.000 WARMUP 48 secs=60", "62.000 WARMUP_DONE"]
    for st, ev in step_events:
        t_first = ev[0][0]
        lines.append("%.3f STEP %d" % (t_first - 9, st))
        lines.append("%.3f SETTLE %d secs=5.0" % (t_first - 9, st))
        lines.append("%.3f SENS %s ACTIVE" % (t_first - 4, ORDER1[3]))  # in the settle: ignored
        lines.append("%.3f SENS %s INACTIVE" % (t_first - 3.5, ORDER1[3]))
        for k, (t, s) in enumerate(ev):
            lines.append("%.3f SENS %s ACTIVE" % (t, s))
            if k == 0:
                lines.append("%.3f MEASURE %d from=%s" % (t + 0.001, st, s))
            lines.append("%.3f SENS %s INACTIVE" % (t + 0.3, s))
        lines.append("%.3f STEPDONE %d reason=settled n=1 mm=1 s=1 mm_s=1 relsd=0" % (ev[-1][0] + 0.01, st))
    lines += ["999.0 STOP all steps complete", "999.1 END"]
    return lines


class Settle(unittest.TestCase):
    def test_formula(self):
        self.assertAlmostEqual(lr.settle_time(26, 24, 0, 126), 0.896 * 26 + 2)
        self.assertAlmostEqual(lr.settle_time(26, 24, 48, 8), 0.896 * 24 * 40 / 126.0 + 2)
        self.assertAlmostEqual(lr.settle_time(26, 24, 48, 48), 2.0)

    def test_up_uses_cv3_down_uses_cv4(self):
        self.assertGreater(lr.settle_time(40, 10, 10, 50), lr.settle_time(40, 10, 50, 10))

    def test_defaults_are_the_locos_roster_values(self):
        self.assertEqual((lr.DIST_CV3, lr.DIST_CV4), (26, 24))


class Aggregate(unittest.TestCase):
    def test_speed_is_total_distance_over_total_time(self):
        n, mm, s, v, rsd = lr.aggregate([(1000.0, 4.0), (2000.0, 10.0)])
        self.assertEqual((n, mm, s), (2, 3000.0, 14.0))
        self.assertAlmostEqual(v, 3000.0 / 14.0)  # not the mean of 250 and 200
        self.assertGreater(rsd, 0)

    def test_empty_and_single(self):
        self.assertEqual(lr.aggregate([]), (0, 0.0, 0.0, 0.0, 0.0))
        self.assertEqual(lr.aggregate([(100.0, 2.0)])[4], 0.0)


class Blocks(unittest.TestCase):
    """SpanReader in steady mode, one block at a time: what the distance runner reads."""

    def reader(self, lengths=LEN1):
        r = lr.SpanReader(ORDER1, lengths, 0, True)
        r.restart(1)
        return r

    def feed(self, reader, events):
        return [reader.feed(t, s) for t, s in events]

    def test_each_block_is_entry_to_entry_in_travel_order(self):
        got = self.feed(self.reader(), steady(ORDER1, ORDER1[2], 250.0, LEN1, 4))
        self.assertIsNone(got[0])
        self.assertEqual([g[4] for g in got[1:]], ORDER1[2:5])
        for g in got[1:]:
            self.assertAlmostEqual(g[0], 250.0)
            self.assertEqual((g[2], g[3]), (1500.0, 1))

    def test_the_other_way_round_counts_too(self):
        got = self.feed(self.reader(), steady(ORDER1, ORDER1[5], 250.0, LEN1, 3, step=-1))
        self.assertEqual([g[4] for g in got[1:]], [ORDER1[5], ORDER1[4]])

    def test_a_missed_sensor_restarts_the_chain(self):
        ev = steady(ORDER1, ORDER1[0], 250.0, LEN1, 5)
        del ev[2]  # block 2 never lit: the 1 -> 3 gap is not a block
        got = self.feed(self.reader(), ev)
        self.assertEqual([g and g[4] for g in got], [None, ORDER1[0], None, ORDER1[3]])

    def test_a_turn_back_restarts_the_chain(self):
        r = self.reader()
        got = self.feed(r, [(0.0, ORDER1[3]), (6.0, ORDER1[4]), (12.0, ORDER1[3]), (18.0, ORDER1[2])])
        self.assertEqual([g and g[4] for g in got], [None, ORDER1[3], None, ORDER1[3]])

    def test_untrusted_length_and_off_route_events_are_skipped(self):
        lens = dict(LEN1)
        lens[ORDER1[1]] = None
        ev = steady(ORDER1, ORDER1[0], 250.0, LEN1, 4)
        ev.insert(2, (ev[1][0] + 0.5, "BS Somewhere Else"))
        got = self.feed(self.reader(lens), ev)
        self.assertEqual([g[4] for g in got if g], [ORDER1[0], ORDER1[2]])

    def test_a_retrigger_is_ignored(self):
        r = self.reader()
        self.assertIsNone(r.feed(1.0, ORDER1[0]))
        self.assertIsNone(r.feed(1.5, ORDER1[0]))
        self.assertEqual(r.feed(7.0, ORDER1[1])[1], 6.0)

    def test_there_is_one_reader_class(self):
        self.assertFalse(hasattr(lr, "BlockReader"))


class EndRule(unittest.TestCase):
    def run_rule(self, blocks, **kw):
        st = lr.DistanceStep(**kw)
        t = 0.0
        for mm, dt in blocks:
            t += dt
            st.add(mm, dt)
            done, why = st.check(t)
            if done:
                return st, why, t
        return st, "", t

    def test_target_distance_and_min_blocks(self):
        st, why, t = self.run_rule([(1500.0, 6.0)] * 6)
        self.assertEqual((why, len(st.blocks)), ("settled", 4))

    def test_one_long_block_is_not_enough_for_min_blocks(self):
        st, why, _ = self.run_rule([(7000.0, 20.0), (700.0, 2.0)])
        self.assertEqual((why, len(st.blocks)), ("settled", 2))

    def test_time_runs_out(self):
        st = lr.DistanceStep(max_s=60.0)
        st.add(500.0, 20.0)
        self.assertEqual(st.check(59.0), (False, ""))
        self.assertEqual(st.check(60.0), (True, "max"))

    def test_time_limit_with_enough_steady_blocks_is_timed_and_valid(self):
        st = lr.DistanceStep()  # step 8 at 56 mm/s: 2 blocks of 1500 mm in 53.6 s, none more by 60 s
        st.add(1500.0, 26.8)
        st.add(1500.0, 26.8)
        self.assertEqual(st.check(60.0), (True, "timed"))
        self.assertTrue(lr.is_valid_reason("timed"))

    def test_time_limit_with_one_block_or_high_spread_is_max_and_not_valid(self):
        one = lr.DistanceStep()
        one.add(1500.0, 26.8)
        self.assertEqual(one.check(60.0), (True, "max"))
        wide = lr.DistanceStep()
        wide.add(1500.0, 20.0)
        wide.add(1500.0, 30.0)
        self.assertEqual(wide.check(60.0), (True, "max"))
        self.assertFalse(lr.is_valid_reason("max"))
        self.assertFalse(lr.is_valid_reason("stalled"))

    def test_spread_earns_one_more_reading_when_time_allows(self):
        blocks = [(1500.0, 5.0), (1500.0, 7.5), (1500.0, 6.0), (1500.0, 6.0)]
        st, why, t = self.run_rule(blocks + [(1500.0, 6.0)] * 6)
        self.assertTrue(st.extra)
        self.assertEqual(why, "settled")
        self.assertGreaterEqual(sum(b[0] for b in st.blocks), 12000.0)  # twice the target
        self.assertLess(len(st.blocks), 10)

    def test_extra_flag_is_raised_once_for_the_log(self):
        st = lr.DistanceStep()
        for dt in (5.0, 7.5, 6.0, 6.0):
            st.add(1500.0, dt)
        self.assertEqual(st.check(24.5), (False, ""))
        self.assertTrue(st.extra_new)
        st.extra_new = False
        self.assertEqual(st.check(24.6), (False, ""))
        self.assertFalse(st.extra_new)

    def test_no_extra_reading_when_time_does_not_allow(self):
        st = lr.DistanceStep(max_s=40.0)
        for dt in (5.0, 7.5, 6.0, 6.0):
            st.add(1500.0, dt)
        self.assertEqual(st.check(24.5), (True, "settled"))
        self.assertFalse(st.extra)

    def test_steady_speed_takes_no_extra_reading(self):
        st, why, _ = self.run_rule([(1500.0, 6.0)] * 5)
        self.assertEqual((why, st.extra), ("settled", False))

    def test_next_after_goes_the_way_to_the_target(self):
        o = analyze.route_order("loop2")
        self.assertEqual(lr.next_after(o, "BS Switch 5", "BS Switch 15"), "BS S-R")
        self.assertEqual(lr.next_after(o, "BS Switch 15", "BS Switch 5"), "BS Brick-Plane")


class Jobs(unittest.TestCase):
    def build(self, *args):
        d = Path(tempfile.mkdtemp())
        out = d / "job.py"
        make_job.main(list(args) + ["--out", str(out)])
        return out.read_text()

    def setting(self, text, name):
        return re.search(r"^%s = (.*)$" % name, text, re.M).group(1)

    def test_distance_defaults(self):
        t = self.build("steps", "--loco", "CSX 2121", "--direction", "forward", "--mode", "distance",
                       "--guard", "default")
        self.assertEqual(self.setting(t, "STEPS_LIST"), "[8, 16, 24, 32, 48, 64, 96, 126]")
        for k, v in dict(WARM_S="60.0", WARM_STEP="48", TARGET_MM="6000.0", MIN_BLOCKS="2", MAX_S="60.0",
                         REL="0.03", CV3="26", CV4="24").items():
            self.assertEqual(self.setting(t, k), v, k)
        self.assertIn("class DistanceStep", t)
        self.assertIn("def settle_time", t)
        self.assertNotIn("WARM_LAPS", t)
        self.assertLess(t.index("P_FWD = True"), t.index("class SL("))

    def test_warm_step_is_checked_only_when_a_warm_up_runs(self):
        base = ["steps", "--loco", "CSX 2121", "--direction", "forward", "--mode", "distance", "--guard", "none",
                "--warm-step", "0"]
        self.build(*base, "--warm-s", "0")
        with self.assertRaises(SystemExit):
            self.build(*base, "--warm-s", "30")

    def test_path_between_takes_the_shorter_way(self):
        o = analyze.route_order("loop2")
        self.assertEqual(lr.path_between(o, "BS Switch 5", "BS Barn"), ["BS Switch 5", "BS Scale", "BS Switch 7", "BS Barn"])
        self.assertEqual(lr.path_between(o, "BS Switch 15", "BS Switch 7"),
                         ["BS Switch 15", "BS Switch 13", "BS Barn", "BS Switch 7"])

    def test_distance_overrides_and_validation(self):
        t = self.build("steps", "--loco", "CSX 2738", "--direction", "reverse", "--mode", "distance",
                       "--guard", "none", "--steps", "24,48", "--warm-s", "0", "--target-mm", "4000",
                       "--min-blocks", "3", "--max-s", "30", "--rel", "0.05", "--cv3", "10", "--cv4", "12",
                       "--route", "loop2")
        self.assertEqual(self.setting(t, "STEPS_LIST"), "[24, 48]")
        self.assertEqual(self.setting(t, "WARM_S"), "0.0")
        self.assertEqual(self.setting(t, "TARGET_MM"), "4000.0")
        self.assertEqual(self.setting(t, "ROUTE"), "'loop2'")
        self.assertEqual((self.setting(t, "CV3"), self.setting(t, "CV4")), ("10", "12"))
        with self.assertRaises(SystemExit):
            self.build("steps", "--loco", "CSX 2738", "--direction", "reverse", "--mode", "distance",
                       "--guard", "none", "--steps", "0,8")
        with self.assertRaises(SystemExit):
            self.build("steps", "--loco", "CSX 2738", "--direction", "reverse", "--mode", "distance",
                       "--guard", "none", "--steps", "8,127")

    def test_laps_mode_is_still_the_default(self):
        t = self.build("steps", "--loco", "CSX 2121", "--direction", "forward", "--guard", "none")
        self.assertIn("STEPS_LIST = [2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 80, 96, 112, 126, 126]", t)
        self.assertIn("WARM_LAPS = 3", t)
        self.assertIn("WARM_STEP = 64", t)
        self.assertIn("STOP_REL = 0.02", t)
        self.assertNotRegex(t, r"(?m)^TARGET_MM = ")

    def test_pass_job(self):
        t = self.build("pass", "--loco", "CSX 2121", "--direction", "forward", "--step", "24",
                       "--from", "BS Switch 5", "--to", "BS Switch 15", "--route", "loop2", "--guard", "default")
        self.assertEqual(self.setting(t, "FROM_S"), "'BS Switch 5'")
        self.assertEqual(self.setting(t, "TO_S"), "'BS Switch 15'")
        self.assertEqual(self.setting(t, "AFTER_S"), "'BS S-R'")  # one more block
        self.assertEqual(eval(self.setting(t, "PATH")), ["BS Switch 5", "BS Scale", "BS Switch 7", "BS Barn",
                                                       "BS Switch 13", "BS Switch 15"])
        self.assertEqual(self.setting(t, "P_STEP"), "24")
        self.assertNotIn("'BS Switch 5'", self.setting(t, "GUARD"))
        self.assertLess(t.index("P_FWD = True"), t.index("class SL("))

    def test_pass_job_refuses_bad_sensors(self):
        base = ["pass", "--loco", "CSX 2121", "--direction", "forward", "--step", "24", "--route", "loop2"]
        for frm, to, guard in [("BS Switch 5", "BS Nowhere", "none"), ("BS Switch 5", "BS Switch 5", "none"),
                               ("BS Switch 5", "BS Switch 15", "BS S-R")]:
            with self.assertRaises(SystemExit, msg=(frm, to)):
                self.build(*base, "--from", frm, "--to", to, "--guard", guard)


class RunnerSource(unittest.TestCase):
    """The log contract: every tag in RUNBOOK.md ("Log lines") is emitted by a runner."""

    def tags(self, src):
        return set(re.findall(r'L\("([A-Z_]+)', src))

    def test_distance_runner_emits_every_tag(self):
        src = mover("distance_runner.py")
        want = {"RUN", "CFG", "LENGTHS", "WARMUP", "WARMUP_DONE", "STEP", "SETTLE", "MEASURE", "SENS",
                "BLOCK", "FREEZE", "STEPDONE", "EXTRA", "STOP", "END"}
        self.assertEqual(want - self.tags(src), set())

    def test_pass_runner_emits_every_tag(self):
        src = mover("pass_runner.py")
        want = {"RUN", "CFG", "PATH", "PASS", "SENS", "PASSDONE", "STOP", "END"}
        self.assertEqual(want - self.tags(src), set())

    def test_the_runbook_states_the_contract(self):
        text = RUNBOOK.read_text()
        self.assertIn("## Log lines", text)
        for tag in ("RUN loco=", "CFG route=", "mode=distance", "LENGTHS ", "WARMUP ", "WARMUP_DONE", "STEP ",
                    "SETTLE ", "MEASURE ", "SENS ", "BLOCK ", "FREEZE ", "STEPDONE ", "PATH ", "PASS step=", "PASSDONE reason=",
                    "STOP ", "END"):
            self.assertIn(tag, text, tag)

    def test_cfg_line_has_the_contract_keys_in_order(self):
        src = (SM / "jython" / "distance_runner.py").read_text()
        cfg = re.search(r'L\("(CFG route=.*?)" %', src, re.S).group(1)
        keys = re.findall(r"(\w+)=", cfg)
        self.assertEqual(keys, ["route", "mode", "steps", "target_mm", "min_blocks", "max_s", "rel", "warm_s",
                                "warm_step", "cv3", "cv4", "mid"])

    def test_no_runner_keeps_its_own_listener_or_waits(self):
        kit = (SM / "jython" / "jobkit.py").read_text()
        for name in ("class SL(", "def wait(", "def pause("):
            self.assertEqual(kit.count(name), 1, name)
            for runner in ("step_runner.py", "distance_runner.py", "pass_runner.py"):
                self.assertNotIn(name, (SM / "jython" / runner).read_text(), (runner, name))

    def test_both_stop_with_their_own_throttle_only(self):
        for name in ("distance_runner.py", "pass_runner.py"):
            src = mover(name)
            for bad in ["emergencyStop", "setPower", "PowerManager", "setCommandedState", "THROWN",
                        "TurnoutManager", "sendMessage", "publish", "readCV", "writeCV", "Programmer"]:
                self.assertNotIn(bad, src, (name, bad))
            self.assertIn("setSpeedSetting(0.0)", src)
            self.assertIn("/tmp/speedrun.kill", src)
            self.assertIn("claim()", src)
            self.assertIn("check_guards(", src)
            self.assertIn("end_job(", src)
            self.assertNotRegex(src, r"\bf[\"']")
            self.assertIn("except Exception, e", src)


class AnalyzeDistance(unittest.TestCase):
    def profile(self, step_events, **kw):
        runs = analyze.parse_log(distance_log(step_events, **kw), source="d.log")
        return analyze.summarize_runs(runs, LEN1)

    def test_a_distance_log_becomes_profile_rows(self):
        sm = self.profile([(8, steady(ORDER1, ORDER1[0], 250.0, LEN1, 12, t0=100.0)),
                           (16, steady(ORDER1, ORDER1[4], 500.0, LEN1, 12, t0=500.0))])
        self.assertEqual(len(sm), 1)
        r8, r16 = sm[0]["rows"]
        self.assertEqual((r8["step"], r8["reason"], r8["settled"], r8["n"]), (8, "settled", True, 4))
        self.assertAlmostEqual(r8["median"], 250.0)
        self.assertAlmostEqual(r16["median"], 500.0)
        self.assertEqual(r8["travel"], "east")
        self.assertTrue(sm[0]["complete"])

    def test_a_sensor_between_step_and_settle_is_not_measured(self):
        lines = distance_log([(8, steady(ORDER1, ORDER1[0], 250.0, LEN1, 6, t0=100.0))])
        i = next(k for k, ln in enumerate(lines) if " STEP 8" in ln)
        lines.insert(i + 1, "%.3f SENS %s ACTIVE" % (91.0, ORDER1[9]))  # after STEP, before SETTLE
        run = analyze.parse_log(lines)[0]
        self.assertNotIn(ORDER1[9], [n for _, n in run["steps"][0]["events"]])
        self.assertEqual(run["steps"][0]["events"][0][1], ORDER1[0])

    def test_a_sensor_between_freeze_and_stepdone_is_not_counted(self):
        ev = steady(ORDER1, ORDER1[0], 250.0, LEN1, 6, t0=100.0)
        lines = distance_log([(8, ev)])
        lines = [ln.replace("STEPDONE 8", "FREEZE 8\n%.3f SENS %s ACTIVE\n%.3f STEPDONE 8" % (
            ev[-1][0] + 0.005, ORDER1[8], ev[-1][0] + 0.01)) if "STEPDONE 8" in ln else ln for ln in lines]
        lines = [x for ln in lines for x in ln.split("\n")]
        # the line before STEPDONE carries the FREEZE time stamp of the STEPDONE line it replaced
        run = analyze.parse_log(lines)[0]
        self.assertNotIn(ORDER1[8], [n for _, n in run["steps"][0]["events"]])
        self.assertEqual(len(run["steps"][0]["events"]), 6)

    def test_pass_logs_are_not_runs(self):
        lines = ["1.000 RUN loco=CSX 2121 direction=forward", "1.001 CFG route=loop2 mode=pass step=24 max_s=240",
                 "2.000 PATH BS Switch 5,BS Scale", "2.001 PASS step=24 from=BS Switch 5 to=BS Scale",
                 "3.000 SENS BS Switch 5 ACTIVE", "9.0 PASSDONE reason=passed", "9.1 STOP passed", "9.2 END"]
        self.assertEqual(analyze.parse_log(lines, source="p.log"), [])

    def test_distance_mode_comes_from_the_log_even_without_its_settings(self):
        runs = analyze.parse_log(distance_log([(8, steady(ORDER1, ORDER1[0], 250.0, LEN1, 12))]))
        sm = analyze.summarize_runs(runs, LEN1, use_logged=False)
        self.assertAlmostEqual(sm[0]["rows"][0]["median"], 250.0, delta=0.1)
        self.assertEqual(sm[0]["rows"][0]["reason"], "settled")

    def test_correct_reads_the_settled_column_and_old_files_by_reason(self):
        import correct as corr
        d = Path(tempfile.mkdtemp())
        head = "loco,direction,step,median_mm_s,reason,run,run_complete,route"
        (d / "a.csv").write_text(head + ",settled\nL,forward,8,50,timed,1,True,loop1,True\n"
                                 "L,forward,16,90,settled,1,True,loop1,False\n"
                                 "L,forward,24,120,max,1,True,loop1,False\n")
        got, skipped = corr.read_profile(d / "a.csv", "L", "forward")
        self.assertEqual(got, {8: 50.0})
        self.assertEqual(sorted(s[0] for s in skipped), [16, 24])
        (d / "b.csv").write_text(head + "\nL,forward,8,50,timed,1,True,loop1\nL,forward,16,90,max,1,True,loop1\n")
        got, _ = corr.read_profile(d / "b.csv", "L", "forward")
        self.assertEqual(got, {8: 50.0})

    def test_settle_events_are_not_measured(self):
        sm = self.profile([(8, steady(ORDER1, ORDER1[0], 250.0, LEN1, 12))])
        self.assertAlmostEqual(sm[0]["rows"][0]["median"], 250.0)  # the SENS in SETTLE was a different block

    def test_profile_csv_carries_distance_rows(self):
        sm = self.profile([(8, steady(ORDER1, ORDER1[0], 250.0, LEN1, 12)),
                           (16, steady(ORDER1, ORDER1[0], 500.0, LEN1, 12, t0=500.0))])
        d = Path(tempfile.mkdtemp())
        analyze.write_outputs(analyze.latest_runs(sm), None, d, sm)
        rows = list(csv.DictReader(open(d / "profile.csv")))
        self.assertEqual([(r["step"], r["median_mm_s"], r["settled"]) for r in rows],
                         [("8", "250.0", "True"), ("16", "500.0", "True")])

    def test_timed_step_is_used_and_max_step_is_not(self):
        ev = steady(ORDER1, ORDER1[0], 56.0, LEN1, 5)  # 26.8 s a block: 2 blocks fit in 60 s
        lines = distance_log([(8, ev)])
        sm = analyze.summarize_runs(analyze.parse_log([x.replace("reason=settled", "reason=timed") for x in lines]), LEN1)
        row = sm[0]["rows"][0]
        self.assertEqual((row["reason"], row["settled"], row["n"]), ("timed", True, 2))
        self.assertAlmostEqual(row["median"], 56.0, delta=0.01)
        d = Path(tempfile.mkdtemp())
        analyze.write_outputs(analyze.latest_runs(sm), None, d, sm)
        self.assertEqual(list(csv.DictReader(open(d / "profile.csv")))[0]["settled"], "True")
        import correct as corr
        got, skipped = corr.read_profile(d / "profile.csv", "CSX 2121", "forward")
        self.assertIn(8, got)

    def test_max_time_step_is_not_settled(self):
        ev = steady(ORDER1, ORDER1[0], 15.0, LEN1, 5)  # 100 s a block: the 60 s run out first
        lines = distance_log([(8, ev)])
        lines = [x.replace("reason=settled", "reason=max") for x in lines]
        sm = analyze.summarize_runs(analyze.parse_log(lines), LEN1)
        row = sm[0]["rows"][0]
        self.assertEqual((row["reason"], row["settled"], row["n"]), ("max", False, 0))

    def test_replay_matches_the_runner_rule_for_a_spread_step(self):
        ev = steady(ORDER1, ORDER1[0], 250.0, LEN1, 3)
        t = ev[-1][0]
        for k, dt in enumerate((7.5, 6.0, 6.0, 6.0, 6.0, 6.0)):  # one slow block, then steady
            t += dt
            ev.append((t, ORDER1[(3 + k) % len(ORDER1)]))
        blocks, why, rsd, extra = analyze.replay_distance(ev, ORDER1, LEN1, 6000.0, 2, 60.0, 0.03)
        self.assertTrue(extra)
        self.assertEqual(why, "settled")
        self.assertGreaterEqual(sum(b[1] for b in blocks), 12000.0)

    def test_block_events_do_not_drop_distance_events(self):
        runs = analyze.parse_log(distance_log([(8, steady(ORDER1, ORDER1[0], 250.0, LEN1, 20))]))
        self.assertEqual(runs[0]["cfg"]["mode"], "distance")
        self.assertEqual(runs[0]["cfg"]["target_mm"], 6000.0)
        self.assertEqual(runs[0]["cfg"]["max_s"], 60.0)


def pass_log(step, v, order, start_t=1000.0, direction="forward", reverse=False, frm="BS Switch 5",
             to="BS Switch 15", lens=None):
    """A pass log with constant speed v over the route: sensor entry times from true lengths."""
    lens = lens or {s: 1000.0 for s in order}
    seq = order if not reverse else list(reversed(order))
    i0 = seq.index(frm) - 1 if not reverse else seq.index(frm) - 1
    lines = ["%.3f RUN loco=CSX 2121 direction=%s" % (start_t - 5, direction),
             "%.3f PASS step=%d from=%s to=%s" % (start_t - 1, step, frm, to)]
    t = start_t
    i = i0
    while True:
        i = (i + 1) % len(seq)
        s = seq[i]
        lines.append("%.3f SENS %s ACTIVE" % (t, s))
        lines.append("%.3f SENS %s INACTIVE" % (t + 2, s))
        t += lens[s] / v
        if s == lr.next_after(order, frm, to) and not reverse:
            break
        if reverse and s == seq[(seq.index(to) + 1) % len(seq)]:
            break
    lines.append("%.3f PASSDONE reason=passed" % t)
    return lines


class Locate(unittest.TestCase):
    ORDER2 = analyze.route_order("loop2")
    PINS = ibl.PLAN_LOOP2_TURNOUT_MM

    def lens(self, sw7=900.0, sw13=700.0):
        """True section lengths: Switch 5 and 15 are 600 mm sections centred on their pins; Scale and
        Barn make up the rest of the stretch. Sections are laid end to end from Switch 5's entry."""
        return {"BS Switch 5": 600.0, "BS Scale": 1500.0, "BS Switch 7": sw7, "BS Barn": 1000.0,
                "BS Switch 13": sw13, "BS Switch 15": 600.0, "BS S-R": 2000.0}

    def events(self, v, lens):
        order = self.ORDER2
        pos = {}
        t = 0.0
        for s in order[:7]:
            pos[s] = t
            t += lens[s] / v
        return [(1000.0 + pos[s], s) for s in order[:7]]

    def test_centres_land_where_they_physically_are(self):
        lens = self.lens()
        # pin the geometry: centre of Switch 5 at 140, so entry at 140 - 300 and Switch 15's centre at its pin
        # gives a speed; make the lengths agree so the true answer is known
        edge = {}
        x = self.PINS["Switch 5"] - 300.0
        for s in self.ORDER2[:7]:
            edge[s] = x
            x += lens[s]
        pin15 = edge["BS Switch 15"] + 300.0
        pins = dict(self.PINS, **{"Switch 15": pin15})
        ev = self.events(120.0, lens)
        got = ibl.pass_centres(ev, "loop2", pins)
        self.assertAlmostEqual(got["speed"], 120.0, places=3)
        for t, s in (("Switch 7", "BS Switch 7"), ("Switch 13", "BS Switch 13")):
            self.assertAlmostEqual(got[t][0], edge[s] + lens[s] / 2, places=2)
            self.assertAlmostEqual(got[t][1], pin15 - (edge[s] + lens[s] / 2), places=2)

    def test_speed_cancels_out(self):
        lens = self.lens()
        a = ibl.pass_centres(self.events(60.0, lens), "loop2", self.PINS)
        b = ibl.pass_centres(self.events(240.0, lens), "loop2", self.PINS)
        for t in ("Switch 7", "Switch 13"):
            self.assertAlmostEqual(a[t][0], b[t][0], places=3)

    def test_the_other_direction_of_travel_works(self):
        lens = self.lens()
        order = self.ORDER2[:7]
        v = 100.0
        t, ev = 1000.0, []
        for s in list(reversed(order)) + ["BS Brick-Plane"]:  # S-R first, Switch 5 last, then the block behind it
            ev.append((t, s))
            t += lens.get(s, 1000.0) / v
        path = lr.path_between(self.ORDER2, "BS Switch 15", "BS Switch 5")
        got = ibl.pass_centres(ev, "loop2", self.PINS, frm="BS Switch 15", to="BS Switch 5", path=path)
        self.assertGreater(got["speed"], 0)
        self.assertTrue(0 < got["Switch 13"][0] < self.PINS["Switch 15"])
        fwd = ibl.pass_centres(self.events(100.0, lens), "loop2", self.PINS)
        self.assertGreater(fwd["Switch 13"][0], fwd["Switch 7"][0])

    def test_pass_that_does_not_follow_its_logged_path_is_refused(self):
        ev = self.events(100.0, self.lens())
        path = lr.path_between(self.ORDER2, "BS Switch 5", "BS Switch 15")
        swapped = [ev[0], ev[2], ev[1]] + ev[3:]  # Switch 7 lit before Scale
        swapped = [(ev[k][0], s) for k, (_, s) in enumerate(swapped)]
        with self.assertRaisesRegex(ValueError, "logged PATH"):
            ibl.pass_centres(swapped, "loop2", self.PINS, path=path)
        ibl.pass_centres(ev, "loop2", self.PINS, path=path)  # the real order is fine

    def test_pins_must_be_pins_of_the_route(self):
        with self.assertRaisesRegex(ValueError, "pins are"):
            ibl.pass_centres(self.events(100.0, self.lens()), "loop2", self.PINS, frm="BS Scale", to="BS Switch 15")

    def test_pass_that_misses_a_pin_is_refused(self):
        ev = [(1.0, "BS Scale"), (2.0, "BS Switch 7")]
        with self.assertRaises(ValueError):
            ibl.pass_centres(ev, "loop2", self.PINS)

    def test_two_logs_report_both_passes_and_their_difference(self):
        d = Path(tempfile.mkdtemp())
        lens = self.lens()
        lens2 = self.lens(sw7=950.0)
        for name, ls, v in (("a.log", lens, 80.0), ("b.log", lens2, 160.0)):
            ev = self.events(v, ls)
            lines = ["1.0 RUN loco=CSX 2121 direction=forward", "2.0 PASS step=24 from=BS Switch 5 to=BS Switch 15"]
            lines += ["%.3f SENS %s ACTIVE" % (t, s) for t, s in ev]
            lines.append("%.3f PASSDONE reason=passed" % (ev[-1][0] + 1))
            (d / name).write_text("\n".join(lines) + "\n")
        out = io.StringIO()
        old = sys.argv
        sys.argv = ["infer_block_lengths.py", "--route", "loop2", "--locate", "--pass-log",
                    str(d / "a.log"), str(d / "b.log")]
        try:
            with redirect_stdout(out):
                ibl.main()
        finally:
            sys.argv = old
        text = out.getvalue()
        self.assertIn("pass 1:", text)
        self.assertIn("pass 2:", text)
        self.assertIn("OS Switch 7 centre", text)
        self.assertIn("OS Switch 13 centre", text)
        self.assertRegex(text, r"locate: OS Switch 13 centre \d+ mm from Switch 5's points, -?\d+ mm before")
        self.assertIn("passes differ by", text)

    def test_parse_pass_log(self):
        lines = pass_log(24, 100.0, self.ORDER2)
        got = analyze.parse_pass_log(lines, "p.log")
        self.assertEqual(len(got), 1)
        p = got[0]
        self.assertEqual((p["loco"], p["direction"], p["step"], p["frm"], p["to"], p["reason"]),
                         ("CSX 2121", "forward", 24, "BS Switch 5", "BS Switch 15", "passed"))
        self.assertEqual([n for _, n in p["events"]][0], "BS Switch 5")
        self.assertEqual(p["events"][-1][1], "BS S-R")


class FakeLayout(object):
    """A virtual clock and a loco on a ring of sensors, standing in for JMRI so the Jython runners
    can be run for real as Python 3 (their `except X, e` lines are rewritten). The loco runs at
    SPEED_PER_STEP mm/s per throttle step; nothing leaves the process."""
    SPEED_PER_STEP = 10.0

    class Sensor(object):
        def __init__(self, name):
            self.name = name
            self.state = 4
            self.ls = []

        def getUserName(self):
            return self.name

        def getSystemName(self):
            return "IS" + self.name.replace(" ", "")

        def addPropertyChangeListener(self, listener):
            self.ls.append(listener)

        def removePropertyChangeListener(self, listener):
            self.ls.remove(listener)

        def getKnownState(self):
            return self.state

    def __init__(self, order, lengths, start_index, extra_sensors=()):
        import types
        self.now = 1000.0
        self.order = order
        self.lengths = lengths
        self.idx = start_index          # the sensor the loco is in
        self.into = 0.0                 # mm into that block
        self.speed = 0.0
        self.forward = True
        self.after = []                 # (time, fn)
        self.speeds = []                # throttle settings, in order
        self.sensors = {n: self.Sensor(n) for n in list(order) + list(extra_sensors)}
        outer = self

        self.ignore_dir = 0             # direction sets the "train node" overwrites (the 2026-11-13 race)

        class Throttle(object):
            def setIsForward(t, f):
                if outer.ignore_dir > 0:
                    outer.ignore_dir -= 1
                    return
                outer.forward = f

            def getIsForward(t):
                return outer.forward

            def setSpeedSetting(t, x):
                outer.speeds.append(x)
                outer.speed = x * 126 * outer.SPEED_PER_STEP

            def release(t, tl):
                pass

            def __getattr__(t, name):
                if name.startswith("setF"):
                    return lambda on: None
                raise AttributeError(name)

        class Roster(object):
            @staticmethod
            def getDefault():
                class R(object):
                    def getEntryForId(r, rid):
                        return rid
                return R()

        class SensorMgr(object):
            def getNamedBeanSet(m):
                return list(outer.sensors.values())

        class ThrottleMgr(object):
            def requestThrottle(m, entry, tl, steal):
                tl.notifyThrottleFound(Throttle())

        class IM(object):
            sensorManagerInstance = staticmethod(lambda: SensorMgr())
            throttleManagerInstance = staticmethod(lambda: ThrottleMgr())

        class Throwable(Exception):
            pass

        self.java = types.ModuleType("java")
        self.java.lang = types.SimpleNamespace(Throwable=Throwable)
        self.java.beans = types.SimpleNamespace(PropertyChangeListener=object)
        self.jmri = types.ModuleType("jmri")
        self.jmri.ThrottleListener = object
        self.jmri.InstanceManager = IM
        self.jmri.jmrit = types.SimpleNamespace(roster=types.SimpleNamespace(Roster=Roster))

    def set_state(self, name, st):
        sn = self.sensors[name]
        sn.state = st
        ev = type("E", (), {"getPropertyName": lambda e: "KnownState", "getNewValue": lambda e: st})()
        for listener in list(sn.ls):
            listener.propertyChange(ev)

    def sleep(self, secs):
        end = self.now + secs
        while self.now < end - 1e-9:
            dt = min(0.01, end - self.now)
            self.now += dt
            self.move(dt)
            for item in [a for a in self.after if a[0] <= self.now]:
                self.after.remove(item)
                item[1]()

    def move(self, dt):
        d = self.speed * dt
        step = 1 if self.forward else -1
        while d > 0:
            room = self.lengths[self.order[self.idx]] - self.into
            if d < room:
                self.into += d
                return
            d -= room
            old = self.order[self.idx]
            self.idx = (self.idx + step) % len(self.order)
            self.into = 0.0
            self.set_state(old, 4)
            self.set_state(self.order[self.idx], 2)

    def run(self, job_text, tmp):
        """Run a job as Python 3 on the virtual clock."""
        import threading
        import time as _time
        src = re.sub(r"except ([\w.]+), e:", r"except \1 as e:", job_text)
        src = src.replace("/tmp/speedrun", str(tmp / "speedrun"))
        saved = (_time.time, _time.sleep, threading.Thread, {k: sys.modules.get(k) for k in ("java", "jmri")})
        clock = self

        class Thread(object):
            def __init__(t, target):
                t.target = target

            def setDaemon(t, f):
                pass

            def start(t):
                t.target()

        _time.time, _time.sleep, threading.Thread = (lambda: clock.now), self.sleep, Thread
        sys.modules["java"], sys.modules["jmri"] = self.java, self.jmri
        try:
            exec(compile(src, "job.py", "exec"), {"__name__": "job"})
        finally:
            _time.time, _time.sleep, threading.Thread = saved[:3]
            for k, v in saved[3].items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v


def loop_csv(path, loop):
    rows = ["user_name,occupancy_sensor,inches,flag,old_source"]
    for sensor, name in loop:
        rows.append("%s,%s,59.055,anyrail," % (name, sensor))  # 59.055 in is 1500 mm
    path.write_text("\n".join(rows) + "\n")


class SimulatedRuns(unittest.TestCase):
    """The runners as Python 3 on a virtual clock: log order, tags, the stop, the guard."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.csv = self.tmp / "bl.csv"
        loop_csv(self.csv, analyze.LOOP)
        self.len = {s: 1500.0 for s in ORDER1}

    def job(self, *args):
        out = self.tmp / "job.py"
        log = self.tmp / "run.log"
        with redirect_stdout(io.StringIO()):
            extra = ["--lengths", str(self.csv)] if args[0] == "steps" else []
            make_job.main(list(args) + ["--out", str(out), "--log", str(log)] + extra)
        return out.read_text(), log

    def lines(self, log):
        return [ln.split(" ", 1) for ln in log.read_text().splitlines()]

    def msgs(self, log):
        return [m for _, m in self.lines(log)]

    def dist(self, *extra):
        return self.job("steps", "--loco", "CSX 2121", "--direction", "forward", "--mode", "distance", *extra)

    def test_distance_pass_end_to_end(self):
        text, log = self.dist("--guard", "none", "--steps", "8,24,48", "--warm-s", "5", "--warm-step", "24")
        sim = FakeLayout(ORDER1, self.len, 2)
        sim.run(text, self.tmp)
        msgs = self.msgs(log)
        for ln in self.lines(log):
            self.assertRegex(ln[0], r"^\d+\.\d{3}$")
        self.assertIn("RUN loco=CSX 2121 direction=forward", msgs)
        cfg = [m for m in msgs if m.startswith("CFG ")][0]
        self.assertIn("mode=distance steps=8,24,48 target_mm=6000 min_blocks=2 max_s=60 rel=0.03 warm_s=5 "
                      "warm_step=24 cv3=26 cv4=24 mid=BS_Switch_23a", cfg)
        self.assertTrue(any(m.startswith("LENGTHS ") for m in msgs))
        self.assertIn("WARMUP 24 secs=5", msgs)
        self.assertIn("WARMUP_DONE", msgs)
        for st in (8, 24, 48):
            i = msgs.index("STEP %d" % st)
            self.assertTrue(msgs[i + 1].startswith("SETTLE %d secs=" % st), msgs[i + 1])
            order = [m.split(" ", 1)[0] for m in msgs[i + 2:] if not m.startswith("SENS")]
            self.assertEqual(order[0], "MEASURE")
            self.assertIn("BLOCK", order)
            self.assertIn("STEPDONE", order)
        done = {int(m.split()[1]): m for m in msgs if m.startswith("STEPDONE ")}
        self.assertIn("reason=settled", done[48])  # 10 mm/s per step: 480 mm/s
        self.assertAlmostEqual(float(re.search(r"mm_s=([\d.]+)", done[48]).group(1)), 480.0, places=0)
        self.assertIn("reason=settled", done[24])
        self.assertIn("reason=timed", done[8])  # 80 mm/s: 6000 mm would take 75 s, but 3 steady blocks fit in 60 s
        blocks = [m for m in msgs if m.startswith("BLOCK 48 ")]
        self.assertGreaterEqual(len(blocks), 2)
        self.assertRegex(blocks[0], r"^BLOCK 48 block=BS_[A-Za-z0-9_-]+ mm=1500\.0 dt=\d+\.\d\d mm_s=\d+\.\d$")
        self.assertEqual(sim.speeds[-1], 0.0)  # stopped with its own throttle
        self.assertIn("STOP all steps complete", msgs)
        self.assertEqual(msgs[-1], "END")
        self.assertFalse((self.tmp / "speedrun.active").exists())

    def test_measuring_starts_at_the_first_sensor_after_the_settle_time(self):
        text, log = self.dist("--guard", "none", "--steps", "48", "--warm-s", "0")
        FakeLayout(ORDER1, self.len, 2).run(text, self.tmp)
        lines = self.lines(log)
        t = {m.split(" ")[0]: float(ts) for ts, m in lines if m.split(" ")[0] in ("STEP", "SETTLE", "MEASURE")}
        settle = float(re.search(r"secs=([\d.]+)", [m for _, m in lines if m.startswith("SETTLE")][0]).group(1))
        self.assertAlmostEqual(settle, lr.settle_time(26, 24, 0, 48), places=1)
        self.assertGreaterEqual(t["MEASURE"] - t["STEP"], settle - 0.01)
        during = [m for ts, m in lines if m.startswith("SENS") and t["STEP"] < float(ts) < t["MEASURE"]]
        self.assertTrue(during)  # lit during the settle: logged, not measured

    def test_a_guard_sensor_ends_the_run_with_speed_zero(self):
        text, log = self.dist("--guard", "BS Guard", "--steps", "8", "--warm-s", "0")
        sim = FakeLayout(ORDER1, self.len, 2, extra_sensors=["BS Guard"])
        sim.after.append((sim.now + 40.0, lambda: sim.set_state("BS Guard", 2)))
        sim.run(text, self.tmp)
        msgs = self.msgs(log)
        self.assertIn("STOP guard BS Guard", msgs)
        self.assertEqual(sim.speeds[-1], 0.0)
        self.assertEqual(msgs[-1], "END")
        self.assertNotIn("STOP all steps complete", msgs)

    def test_a_guard_already_lit_stops_before_the_loco_moves(self):
        text, log = self.dist("--guard", "BS Guard", "--steps", "48", "--warm-s", "0")
        sim = FakeLayout(ORDER1, self.len, 2, extra_sensors=["BS Guard"])
        sim.sensors["BS Guard"].state = 2
        sim.run(text, self.tmp)
        self.assertEqual(sim.speeds, [])
        self.assertIn("STOP guard already ACTIVE: BS Guard", self.msgs(log))

    def test_the_kill_flag_ends_the_run(self):
        text, log = self.job("steps", "--loco", "CSX 2121", "--direction", "reverse", "--mode", "distance",
                             "--guard", "none", "--steps", "8", "--warm-s", "0")
        sim = FakeLayout(ORDER1, self.len, 6)
        sim.after.append((sim.now + 30.0, lambda: (self.tmp / "speedrun.kill").write_text("")))
        sim.run(text, self.tmp)
        msgs = self.msgs(log)
        self.assertIn("STOP killed", msgs)
        self.assertEqual(sim.speeds[-1], 0.0)
        self.assertIn("RUN loco=CSX 2121 direction=reverse", msgs)

    def test_direction_is_set_again_when_the_train_node_overwrites_it(self):
        text, log = self.job("steps", "--loco", "CSX 2121", "--direction", "reverse", "--mode", "distance",
                             "--guard", "none", "--steps", "8", "--warm-s", "0")
        sim = FakeLayout(ORDER1, self.len, 6)
        sim.ignore_dir = 1
        sim.after.append((sim.now + 40.0, lambda: (self.tmp / "speedrun.kill").write_text("")))
        sim.run(text, self.tmp)
        msgs = self.msgs(log)
        self.assertIn("DIR reverse lost, try 1", msgs)
        self.assertIn("DIR reverse held", msgs)
        self.assertFalse(sim.forward)
        # no speed is sent before the direction holds
        self.assertLess(msgs.index("DIR reverse held"), msgs.index("STEP 8"))

    def test_a_direction_that_never_holds_ends_the_run_before_any_speed(self):
        text, log = self.job("steps", "--loco", "CSX 2121", "--direction", "reverse", "--mode", "distance",
                             "--guard", "none", "--steps", "8", "--warm-s", "0")
        sim = FakeLayout(ORDER1, self.len, 6)
        sim.ignore_dir = 99
        sim.run(text, self.tmp)
        msgs = self.msgs(log)
        self.assertIn("STOP direction reverse did not hold", msgs)
        self.assertEqual([x for x in sim.speeds if x > 0], [])
        self.assertIn("F0 left on", msgs)

    def test_a_stalled_loco_ends_the_run(self):
        text, log = self.dist("--guard", "none", "--steps", "48", "--warm-s", "0", "--stall", "20")
        sim = FakeLayout(ORDER1, self.len, 2)
        sim.SPEED_PER_STEP = 0.0
        sim.run(text, self.tmp)
        msgs = self.msgs(log)
        self.assertTrue(any(m.startswith("STEPDONE 48 reason=stalled n=0") for m in msgs), msgs[-8:])
        self.assertTrue(any(m.startswith("STOP stall") for m in msgs))
        self.assertEqual(sim.speeds[-1], 0.0)

    def test_a_distance_log_replays_into_the_same_speed(self):
        text, log = self.dist("--guard", "none", "--steps", "24,48", "--warm-s", "0")
        FakeLayout(ORDER1, self.len, 2).run(text, self.tmp)
        runs = analyze.parse_log(log.read_text().splitlines(), source="run.log")
        sm = analyze.summarize_runs(runs, self.len)
        rows = {r["step"]: r for r in sm[0]["rows"]}
        self.assertAlmostEqual(rows[24]["median"], 240.0, delta=1.0)
        self.assertAlmostEqual(rows[48]["median"], 480.0, delta=2.0)
        self.assertTrue(rows[48]["settled"])
        self.assertTrue(sm[0]["complete"])

    def pass_job(self, *extra):
        loop_csv(self.csv, analyze.LOOP2)
        return self.job("pass", "--loco", "CSX 2121", "--direction", "forward", "--step", "24",
                        "--from", "BS Switch 5", "--to", "BS Switch 15", "--route", "loop2",
                        "--guard", "none", *extra)

    def test_pass_job_stops_one_block_after_the_target(self):
        order = analyze.route_order("loop2")
        text, log = self.pass_job()
        sim = FakeLayout(order, {s: 1500.0 for s in order}, order.index("BS Switch 5") - 1)
        sim.run(text, self.tmp)
        msgs = self.msgs(log)
        self.assertIn("PASS step=24 from=BS Switch 5 to=BS Switch 15", msgs)
        self.assertIn("PASSDONE reason=passed", msgs)
        lit = [m for m in msgs if m.startswith("SENS") and m.endswith(" ACTIVE")]
        self.assertEqual(lit[-1], "SENS BS S-R ACTIVE")
        self.assertIn("SENS BS Switch 15 ACTIVE", lit)
        self.assertEqual(sim.speeds[-1], 0.0)
        self.assertEqual(msgs[-1], "END")
        self.assertLess(msgs.index("PASSDONE reason=passed"), msgs.index("STOP passed"))
        got = analyze.parse_pass_log(log.read_text().splitlines(), "p.log")
        self.assertEqual(got[0]["reason"], "passed")
        res = ibl.pass_centres(got[0]["events"], "loop2", ibl.PLAN_LOOP2_TURNOUT_MM)
        self.assertGreater(res["speed"], 0)

    def test_pass_job_stops_at_once_when_the_loco_goes_the_wrong_way(self):
        order = analyze.route_order("loop2")
        text, log = self.pass_job()
        text = text.replace("P_FWD = True", "P_FWD = False")  # runs against the route order
        i = order.index("BS Switch 5")
        sim = FakeLayout(order, {s: 1500.0 for s in order}, i)
        sim.sensors["BS Switch 5"].state = 2  # starts inside FROM
        sim.run(text, self.tmp)
        msgs = self.msgs(log)
        self.assertTrue(any(m.startswith("PATH BS Switch 5,BS Scale,") for m in msgs))
        self.assertIn("PASSDONE reason=wrong_way", msgs)
        self.assertIn("STOP wrong way", msgs)
        lit = [m for m in msgs if m.startswith("SENS") and m.endswith(" ACTIVE")]
        self.assertEqual(lit, ["SENS BS Brick-Plane ACTIVE"])  # stopped at the first wrong sensor
        self.assertEqual(sim.speeds[-1], 0.0)

    def test_pass_job_is_cut_off_by_the_time_limit(self):
        order = analyze.route_order("loop2")
        text, log = self.pass_job("--max-s", "10")
        sim = FakeLayout(order, {s: 1500.0 for s in order}, 0)
        sim.run(text, self.tmp)
        self.assertIn("PASSDONE reason=max", self.msgs(log))
        self.assertEqual(sim.speeds[-1], 0.0)


if __name__ == "__main__":
    unittest.main()
