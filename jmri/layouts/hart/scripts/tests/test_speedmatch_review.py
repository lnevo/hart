"""Speed-match tools, second round: settings that survive the paste, the stall cap, logged
config replay, sensor states, guard sensors, settled-only correction input, the rising pass,
the move job and the drop script's usage. Shares helpers with test_speedmatch.py.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_speedmatch import FORBIDDEN_EVERYWHERE, SM, analyze, correct, lr, make_job, mover  # noqa: E402
from test_speedmatch import pc  # noqa: E402

pc_problems = pc.log_problems
pc_main = pc.main


def effective_settings(job_text: str) -> dict:
    """Run everything before the runner (liverule defaults, then the settings), which is
    what the names are when the runner starts on the Pi."""
    prefix = job_text.split(make_job.RUNNER_MARK)[0]
    ns: dict = {}
    exec(compile(prefix, "job", "exec"), ns)
    return ns


class Settings(unittest.TestCase):
    def lengths_csv(self):
        d = Path(tempfile.mkdtemp())
        p = d / "bl.csv"
        p.write_text("user_name,occupancy_sensor,inches,flag,old_source\nTrack Main West,x,220,anyrail,\n")
        return d, p

    def test_owner_settings_beat_the_liverule_defaults(self):
        d, p = self.lengths_csv()
        make_job.main(["steps", "--loco", "CSX 2121", "--direction", "forward", "--out", str(d / "j.py"),
                       "--lengths", str(p), "--guard", "none", "--k", "7", "--rel", "0.05", "--max", "20", "--settle", "4",
                       "--low-max", "30", "--high-span", "2", "--stall-cap", "200",
                       "--stall-skip-below", "4"])
        ns = effective_settings((d / "j.py").read_text())
        self.assertEqual((ns["STOP_K"], ns["STOP_REL"], ns["MAX_READINGS"]), (7, 0.05, 20))
        self.assertEqual((ns["SETTLE_EVENTS"], ns["LOW_MAX"], ns["HIGH_SPAN"]), (4, 30, 2))
        self.assertEqual((ns["STALL_CAP"], ns["STALL_SKIP_BELOW"]), (200.0, 4))
        self.assertEqual(ns["GUARD"], [])

    def test_a_guard_is_set_once(self):
        d, p = self.lengths_csv()
        make_job.main(["steps", "--loco", "CSX 2121", "--direction", "forward", "--out", str(d / "j.py"),
                       "--lengths", str(p), "--guard", "BS W-1"])
        self.assertEqual((d / "j.py").read_text().count("GUARD = "), 1)


class Stall(unittest.TestCase):
    def test_limit_is_capped_and_not_raised_by_a_dead_step(self):
        self.assertEqual(lr.next_stall(120, 300, None), 120)
        self.assertEqual(lr.next_stall(120, 300, 50), 200)
        self.assertEqual(lr.next_stall(120, 300, 500), 300)
        self.assertEqual(lr.next_stall(400, 300, None), 300)

    def test_two_creep_stalls_then_a_dead_loco_at_step_8_ends_the_run(self):
        stall, actions = 120.0, []
        for step in (2, 4, 8):
            actions.append(lr.stall_action(step, 6))
            stall = lr.next_stall(120, 300, None)  # nothing settled
        self.assertEqual(actions, ["skip", "skip", "end"])
        self.assertEqual(stall, 120)

    def test_runner_uses_both_rules(self):
        src = (SM / "jython" / "step_runner.py").read_text()
        self.assertIn("stall_action(st, STALL_SKIP_BELOW)", src)
        self.assertIn("next_stall(STALL0, STALL_CAP, interval)", src)
        self.assertIn('reason == "settled" and frozen', src)


class Logs(unittest.TestCase):
    def test_logged_config_and_lengths_are_replayed(self):
        lines = ["1.0 RUN loco=L direction=forward",
                 "1.1 CFG k=3 rel=0.2000 max=4 settle=0 low_max=48 high_span=3 warm=3@64",
                 '1.2 LENGTHS {"BS Main West": 1000.0, "BS Switch 1": 1000.0, "BS Brick-Plane": 1000.0}',
                 "2.0 STEP 24"]
        t = 3.0
        for i, s in enumerate(["BS Main West", "BS Switch 1", "BS Brick-Plane", "BS Switch 5"] * 2):
            lines.append("%.1f SENS %s ACTIVE" % (t, s))
            t += 10 if i % 2 else 11
        run = analyze.parse_log(lines)[0]
        self.assertEqual(run["cfg"]["k"], 3)
        self.assertEqual(run["lengths"]["BS Switch 1"], 1000.0)
        # the CLI values (k=5, rel 0.1%, no lengths) lose to the log
        row = analyze.summarize([run], {}, k=5, rel=0.001, max_n=12)[("L", "forward")][0]
        self.assertGreater(row["n"], 0)
        self.assertEqual(row["reason"], "settled")
        old = analyze.summarize([run], {}, use_logged=False)[("L", "forward")][0]
        self.assertEqual(old["n"], 0)

    def test_old_logs_use_the_command_line_values(self):
        lines = ["1.0 RUN loco=L direction=forward", "2.0 STEP 24"]
        run = analyze.parse_log(lines)[0]
        self.assertEqual(run["cfg"], {})
        self.assertIsNone(run["lengths"])

    def test_unknown_between_two_actives_is_a_new_active(self):
        lines = ["1.0 RUN loco=L direction=forward", "2.0 STEP 24",
                 "3.0 SENS BS Main West ACTIVE", "3.5 SENS BS Main West ACTIVE",
                 "4.0 SENS BS Main West UNKNOWN", "5.0 SENS BS Main West ACTIVE",
                 "6.0 SENS BS Main West INCONSISTENT", "7.0 SENS BS Main West ACTIVE",
                 "8.0 SENS BS Main West INACTIVE"]
        ev = analyze.parse_log(lines)[0]["steps"][0]["events"]
        self.assertEqual([t for t, _ in ev], [3.0, 5.0, 7.0])

    def test_runner_logs_real_state_names_and_keeps_every_state(self):
        src = mover("step_runner.py")
        for name in ("UNKNOWN", "INCONSISTENT"):
            self.assertIn('"%s"' % name, src)
        self.assertIn("state[self.n] = st", src)
        self.assertIn("LENGTHS ", src)


class Guards(unittest.TestCase):
    def test_guard_sensors_are_found_by_any_name_and_checked_at_start(self):
        for name in ("step_runner.py", "move_to.py", "stop_test.py"):
            src = mover(name)
            self.assertIn("guard already ACTIVE", src)
            self.assertIn("not found", src)
        src = mover("step_runner.py")
        self.assertIn("getSystemName", src)
        self.assertIn("isg or isx or want(un)", src)  # listened to whatever its name starts with
        self.assertIn("factory(un or sn, isg, s)", src)  # one listener per bean, both roles


def profile_csv(rows):
    p = Path(tempfile.mkdtemp()) / "profile.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["loco", "direction", "step", "travel", "blocks_per_reading", "readings",
                    "readings_used", "median_mm_s", "rel_sd_pct", "settled", "reason"])
        w.writerows(rows)
    return p


class Correction(unittest.TestCase):
    def test_only_settled_steps_are_used(self):
        p = profile_csv([
            ["A", "forward", "24", "", 1, 5, 5, 100.0, 1.0, True, "settled"],
            ["A", "forward", "48", "", 1, 12, 12, 200.0, 9.0, False, "max"],
            ["A", "forward", "64", "", 1, 3, 3, 300.0, 3.0, False, "open"],
            ["A", "forward", "126#2", "", 1, 5, 5, 400.0, 1.0, True, "settled"],
            ["A", "forward", "8", "", 0, 0, 0, "", "", False, "no readings"]])
        got, skipped = correct.read_profile(p, "A", "forward")
        self.assertEqual(got, {24: 100.0})
        self.assertEqual(sorted(skipped), [(8, "no readings"), (48, "max"), (64, "open")])

    def test_skipped_steps_are_reported_in_the_proposal(self):
        rows = [["B", "reverse", str(s), "", 1, 5, 5, 50.0 + s, 1.0, True, "settled"] for s in (24, 64, 126)]
        rows += [["A", "forward", str(s), "", 1, 5, 5, 100.0 + s, 1.0, True, "settled"] for s in (24, 64)]
        rows += [["A", "forward", "126", "", 1, 12, 12, 300.0, 9.0, False, "max"]]
        p = profile_csv(rows)
        out = p.parent / "o"
        correct.main(["--table", ",".join(["100"] * 28), "--profile", str(p), "--loco", "B", "--direction",
                      "reverse", "--target-loco", "A", "--target-direction", "forward", "--out", str(out)])
        prop = json.loads((out / "proposal.json").read_text())
        self.assertEqual(len(prop["skipped_steps"]), 1)
        self.assertIn("step 126: max", prop["skipped_steps"][0])
        self.assertIn("skipped A forward step 126: max", (out / "proposal.csv").read_text())
        for w in prop["writes"]:
            self.assertEqual(set(w), {"cv", "value"})

    def test_rising_pass_is_part_of_the_result_and_noted(self):
        table = [10, 20, 30, 40, 50, 60] + [100] * 22
        steps = list(range(0, 127, 6))
        measured = {s: 100.0 for s in steps}
        target = {s: 100.0 for s in steps}
        target[24] = 300.0  # only the anchors around step 24 want more
        rep = correct.propose(table, measured, target, tol=0.03, max_ratio=100)
        self.assertEqual(rep["values"], sorted(rep["values"]))
        raised = [a for a in rep["anchors"] if a.get("raised")]
        self.assertTrue(raised)
        self.assertFalse(rep["all_within"])
        prop = correct.proposal("X", rep, 1, 5, 0.03)
        noted = [c for c in prop["changes"] if c.get("note") == correct.RAISED_NOTE]
        self.assertEqual(len(noted), len(raised))
        self.assertTrue(all(set(w) == {"cv", "value"} for w in prop["writes"]))

    def test_a_table_that_only_needs_the_rising_pass_is_not_done(self):
        table = [50, 40] + [100] * 26
        flat = {s: 100.0 for s in range(0, 127, 6)}
        rep = correct.propose(table, flat, flat)
        self.assertEqual(rep["values"][:2], [50, 50])
        self.assertFalse(rep["all_within"])


class MoveAndDrop(unittest.TestCase):
    def test_move_job_has_the_globals_and_no_eval(self):
        d = Path(tempfile.mkdtemp())
        make_job.main(["move", "--loco", "CSX 2738", "--direction", "reverse", "--step", "32",
                       "--until", "BS Switch 33", "--until", "BS East Lead", "--guard", "BS W-1",
                       "--out", str(d / "m.py")])
        text = (d / "m.py").read_text()
        ns: dict = {}
        exec(compile(text.split(make_job.RUNNER_MARK)[0], "job", "exec"), ns)
        self.assertEqual((ns["P_ID"], ns["P_FWD"], ns["P_STEP"]), ("CSX 2738", False, 32))
        self.assertEqual(ns["UNTIL"], ["BS Switch 33", "BS East Lead"])
        self.assertEqual(ns["GUARD"], ["BS W-1"])
        self.assertEqual(ns["FUNCS"], [0])  # no hard-coded 2121 sound mute
        src = mover("move_to.py")
        for bad in FORBIDDEN_EVERYWHERE + ["eval(", "readCV", "writeCV", "F8"]:
            self.assertNotIn(bad, src, bad)
        self.assertIn("setSpeedSetting(0.0)", src)
        self.assertIn("except Exception, e", src)

    def test_drop_job_prints_usage_without_arguments(self):
        for args in ([], ["--fetch"]):
            r = subprocess.run(["bash", str(SM / "drop_job.sh")] + args, capture_output=True, text=True)
            self.assertNotIn("unbound", r.stderr)
            self.assertIn("drop_job.sh JOBFILE", r.stdout + r.stderr)


class SecondReview(unittest.TestCase):
    flat = {s: 100.0 for s in range(0, 127, 6)}

    def test_entries_left_alone_keep_their_value_and_writes_are_empty(self):
        table = [0] + [50] * 27
        rep = correct.propose(table, self.flat, {s: 101.0 for s in self.flat})
        self.assertEqual(rep["values"], table)
        self.assertTrue(rep["all_within"])
        self.assertEqual(correct.proposal("X", rep, 1, 5, 0.03)["writes"], [])

    def test_unmeasured_entries_keep_their_value_too(self):
        rep = correct.propose([0] * 28, {}, {10: 5.0})
        self.assertEqual(rep["values"], [0] * 28)

    def test_a_changed_entry_is_clamped(self):
        rep = correct.propose([0] * 28, self.flat, {s: 200.0 for s in self.flat})
        self.assertEqual(rep["values"][0], 1)  # 0 x anything stays 0 -> the changed entry is raised to 1
        self.assertTrue(all(1 <= v <= 255 for v in rep["values"]))

    def test_nothing_is_extrapolated_outside_the_measured_steps(self):
        self.assertIsNone(correct.interp(130.0, [(8, 1.0), (126, 5.0)]))
        self.assertIsNone(correct.interp(4.0, [(8, 1.0), (126, 5.0)]))
        self.assertEqual(correct.interp(126.0, [(8, 1.0), (126, 5.0)]), 5.0)
        part = {s: 100.0 for s in range(30, 101, 10)}
        rep = correct.propose([100] * 28, part, {s: 200.0 for s in part})
        inside = [a for a in rep["anchors"] if 30 <= a["step"] <= 100]
        outside = [a for a in rep["anchors"] if not 30 <= a["step"] <= 100]
        self.assertTrue(all(a["new"] > a["old"] for a in inside))
        self.assertTrue(all("no usable" in a["note"] for a in outside))
        self.assertTrue(all(a["new"] == a["old"] for a in outside if a["step"] < 30))
        # above the range an entry moves only because the table must keep rising, and says so
        self.assertTrue(all(a.get("raised") for a in outside if a["step"] > 100 and a["new"] != a["old"]))

    def test_drop_job_guards_a_running_runner_and_leaves_the_kill_flag(self):
        src = (SM / "drop_job.sh").read_text()
        self.assertIn("/tmp/speedrun.active", src)
        self.assertIn("--force", src)
        self.assertNotIn("rm -f /tmp/speedrun.kill", src)
        self.assertNotIn("rm /tmp/speedrun.kill'", src)
        for name in ("step_runner.py", "move_to.py", "stop_test.py"):
            j = mover(name)
            self.assertIn("/tmp/speedrun.active", j)
            self.assertIn("own[0]", j)

    def write_csv(self, header, rows):
        p = Path(tempfile.mkdtemp()) / "bl.csv"
        p.write_text(",".join(header) + "\n" + "\n".join(",".join(r) for r in rows) + "\n")
        return p

    def test_without_basis_the_trusted_set_is_exact(self):
        p = self.write_csv(["user_name", "occupancy_sensor", "inches", "flag", "old_source"],
                           [["Track Main West", "x", "220", "assigned", ""],
                            ["Track East Lead", "x", "172", "anyrail", ""]])
        default = analyze.load_lengths(p)
        self.assertIsNone(default["BS Main West"])  # assigned only when passed
        self.assertIsNotNone(default["BS East Lead"])
        both = analyze.load_lengths(p, trusted=("anyrail", "assigned"))
        self.assertIsNotNone(both["BS Main West"])
        only = analyze.load_lengths(p, trusted=("anyrail",))
        self.assertIsNone(only["BS Main West"])
        self.assertIsNotNone(only["BS East Lead"])

    def test_stubs_match_by_flag_and_shared_detector(self):
        p = self.write_csv(["user_name", "occupancy_sensor", "inches", "flag", "old_source"],
                           [["Track East Lead", "Block 1-7", "172", "anyrail", ""],
                            ["Track East Lead East", "BS East Lead", "10", "stub", "unrelated text"],
                            ["Track K-1 West", "BS K-1", "10", "stub", ""],
                            ["Track Main West", "Block 2-1", "220", "anyrail", ""],
                            ["Track Main West Stub", "BS Main West", "bad", "stub", ""]])
        got = analyze.load_lengths(p)
        self.assertAlmostEqual(got["BS East Lead"], 182 * 25.4)
        self.assertAlmostEqual(got["BS Main West"], 220 * 25.4)  # a bad stub length is ignored
        self.assertIsNone(got["BS K-1"])  # a stub does not make an untrusted track trusted


def steady_log(run_header, cfg="", n=8, dt=10.0, t0=3.0, complete=True, sensors=None):
    """A runner log with one step of steady one-block readings (1000 mm each)."""
    sensors = sensors or analyze.ORDER
    lines = [run_header] + ([cfg] if cfg else []) + ["%.1f STEP 24" % (t0 - 1)]
    t = t0
    for i in range(n):
        lines.append("%.1f SENS %s ACTIVE" % (t, sensors[i % len(sensors)]))
        t += dt
    if complete:
        lines.append("%.1f STOP all steps complete" % t)
    return lines


LENGTHS_1000 = {s: 1000.0 for s in analyze.ORDER}


class Round3(unittest.TestCase):
    def test_csv_lengths_swap_only_the_lengths(self):
        lines = steady_log("1.0 RUN loco=L direction=forward",
                           "1.1 CFG k=3 rel=0.2000 max=4 settle=0 low_max=48 high_span=3 warm=3@64")
        run = analyze.parse_log(lines)[0]
        run["lengths"] = dict(LENGTHS_1000)
        csv_len = {s: 2000.0 for s in LENGTHS_1000}
        row = analyze.summarize_runs([run], csv_len, k=5, rel=0.0001, csv_lengths=True)[0]["rows"][0]
        self.assertEqual(row["reason"], "settled")        # k=3, 20% from the log's CFG
        self.assertAlmostEqual(row["median"], 200.0)      # 2000 mm / 10 s from the CSV lengths
        logged = analyze.summarize_runs([run], csv_len)[0]["rows"][0]
        self.assertAlmostEqual(logged["median"], 100.0)

    def test_default_trusted_set_is_anyrail_and_inferred_everywhere(self):
        self.assertEqual(analyze.DEFAULT_TRUSTED, ("anyrail", "inferred"))
        d = Path(tempfile.mkdtemp())
        p = d / "bl.csv"
        p.write_text("user_name,occupancy_sensor,inches,basis,flag\nTrack Main West,x,220,assigned,assigned\n")
        self.assertIsNone(analyze.load_lengths(p)["BS Main West"])
        self.assertIsNotNone(analyze.load_lengths(p, trusted=("assigned",))["BS Main West"])

    # ---- correction ----
    flat = {s: 100.0 for s in range(0, 127, 6)}

    def test_a_cut_never_raises_an_entry(self):
        table = [0, 1] + [100] * 26
        meas = dict(self.flat)
        meas[4.5] = 200.0   # entry 1 (old 0) and nearby run fast
        meas[9.0] = 200.0   # entry 2 (old 1) runs fast
        rep = correct.propose(table, meas, self.flat)
        self.assertEqual(rep["values"][0], 0)
        self.assertEqual(rep["values"][1], 1)
        writes = {w["cv"] for w in correct.proposal("X", rep, 1, 5, 0.03)["writes"]}
        self.assertFalse(writes & {67, 68})   # nothing to write for the two untouched entries

    def test_a_cut_pulls_higher_entries_that_were_within_down_with_it(self):
        meas = dict(self.flat)
        meas[22.5] = 130.0  # entry 5 runs fast: cut to 77
        rep = correct.propose([100] * 28, meas, self.flat)
        self.assertEqual(rep["values"][:6], [77] * 5 + [100])
        self.assertEqual(rep["values"], sorted(rep["values"]))
        self.assertFalse(rep["blocked"])
        self.assertEqual(correct.status(rep, 1, 5), "continue")
        prop = correct.proposal("X", rep, 1, 5, 0.03)
        self.assertTrue(any(c.get("note") == correct.LOWERED_NOTE for c in prop["changes"]))
        self.assertTrue(all(set(w) == {"cv", "value"} for w in prop["writes"]))

    def test_a_cut_blocked_by_a_predecessor_that_must_rise(self):
        meas = dict(self.flat)
        meas[18.0] = 80.0   # entry 4 runs slow: it must rise to 125
        meas[22.5] = 130.0  # entry 5 runs fast: wants 77, below entry 4
        rep = correct.propose([100] * 28, meas, self.flat)
        a4, a5 = rep["anchors"][3], rep["anchors"][4]
        self.assertEqual(a4["new"], 100)          # its raise is capped at the blocked entry's old value
        self.assertEqual(a5["new"], 100)          # the blocked entry keeps its old value
        self.assertIn(correct.BLOCKED_NOTE, a5["note"])
        self.assertIn(correct.CAPPED_NOTE, a4["note"])
        self.assertEqual(rep["blocked"], [a5["cv"]])
        self.assertEqual(rep["values"], sorted(rep["values"]))
        self.assertEqual(correct.status(rep, 1, 5), "blocked")
        prop = correct.proposal("X", rep, 1, 5, 0.03)
        self.assertEqual(prop["status"], "blocked")
        self.assertEqual(prop["writes"], [])       # nothing is written for a blocked proposal

    def test_an_entry_not_cut_is_still_raised_to_its_predecessor(self):
        rep = correct.propose([50, 40] + [100] * 26, self.flat, self.flat)
        self.assertEqual(rep["values"][:2], [50, 50])
        self.assertTrue(rep["anchors"][1]["raised"])

    # ---- runs ----
    def two_runs(self):
        a = steady_log("1.0 RUN loco=L direction=forward", complete=False)
        b = steady_log("100.0 RUN loco=L direction=forward", dt=5.0, t0=103.0)
        c = steady_log("200.0 RUN loco=L direction=forward", dt=20.0, t0=203.0, complete=False)
        return analyze.parse_log(a + b + c, source="x.log")

    def test_the_same_loco_and_direction_twice_are_two_runs(self):
        runs = self.two_runs()
        self.assertEqual(len(runs), 3)
        self.assertEqual([r["complete"] for r in runs], [False, True, False])
        sm = analyze.summarize_runs(runs, LENGTHS_1000)
        self.assertEqual([s["run"] for s in sm], [1, 2, 3])
        latest = analyze.latest_runs(sm)[("L", "forward")]
        self.assertEqual(latest[0]["run"], 2)           # the latest complete one
        self.assertAlmostEqual(latest[0]["median"], 200.0)

    def test_profile_and_drift_carry_the_run_and_correct_reads_the_latest_complete(self):
        d = Path(tempfile.mkdtemp())
        sm = analyze.summarize_runs(self.two_runs(), LENGTHS_1000)
        analyze.write_outputs(analyze.latest_runs(sm), None, d, sm)
        rows = list(csv.DictReader(open(d / "profile.csv")))
        self.assertEqual({r["run"] for r in rows}, {"1", "2", "3"})
        got, _ = correct.read_profile(d / "profile.csv", "L", "forward")
        self.assertAlmostEqual(got[24], 200.0)           # run 2
        got3, _ = correct.read_profile(d / "profile.csv", "L", "forward", run=3)
        self.assertAlmostEqual(got3[24], 50.0)
        self.assertIn("run", open(d / "drift.csv").readline())

    def test_drift_compares_within_a_run_only(self):
        lines = ["1.0 RUN loco=L direction=forward", "2.0 STEP 126", "3.0 STEP 126",
                 "10.0 RUN loco=L direction=forward", "11.0 STEP 126"]
        runs = analyze.parse_log(lines)
        self.assertEqual([[s["occurrence"] for s in r["steps"]] for r in runs], [[1, 2], [1]])

    # ---- runner text ----
    def test_step_line_and_reader_restart_happen_under_the_lock_in_that_order(self):
        src = (SM / "jython" / "step_runner.py").read_text()
        self.assertLess(src.index('L("STEP %d" % st)'), src.index("reader.restart("))
        self.assertIn("frozen = list(readings)", src)
        self.assertIn("lock.acquire()", src)
        self.assertNotIn("readings[-STOP_K:]", src)

    def test_events_after_the_decision_belong_to_the_step_whose_line_is_last(self):
        lines = ["1.0 RUN loco=L direction=forward", "2.0 STEP 24", "3.0 SENS BS Main West ACTIVE",
                 "4.0 STEPDONE 24 reason=settled n=5", "4.5 SENS BS Switch 1 ACTIVE",
                 "5.0 STEP 32", "5.5 SENS BS Brick-Plane ACTIVE"]
        steps = analyze.parse_log(lines)[0]["steps"]
        self.assertEqual([s for _, s in steps[0]["events"]], ["BS Main West", "BS Switch 1"])
        self.assertEqual([s for _, s in steps[1]["events"]], ["BS Brick-Plane"])

    def test_stall_timer_only_follows_loop_sensors_lighting(self):
        src = (SM / "jython" / "step_runner.py").read_text()
        body = src.split("def propertyChange")[1].split("def wait")[0]
        self.assertEqual(body.count("last[0] = now"), 1)
        self.assertIn("if st == 2 and self.n in ORDER: last[0] = now", body)

    def test_finally_stops_then_turns_functions_off_then_releases(self):
        kit = (SM / "jython" / "jobkit.py").read_text()
        fin = kit.split("def end_job")[1]
        i0, i1, i2 = fin.index("setSpeedSetting(0.0)"), fin.index("(False)"), fin.index("t.release(tl)")
        self.assertTrue(i0 < i1 < i2)
        for name in ("step_runner.py", "move_to.py", "stop_test.py"):
            src = (SM / "jython" / name).read_text()
            self.assertIn("end_job(t, tl, FUNCS)", src.split("finally:")[-1], name)
            self.assertIn("tl = None", src)

    def test_preflight_aborts_after_a_timeout(self):
        src = (SM / "jython" / "preflight.py").read_text()
        i = src.index("FAIL timeout")
        self.assertIn("ABORTED", src[i:i + 200])
        self.assertIn("return", src[i:i + 200])


class Round4(unittest.TestCase):
    flat = {s: 100.0 for s in range(0, 127, 6)}

    def test_writes_only_come_with_status_continue(self):
        slow = {s: 80.0 for s in self.flat}
        rep = correct.propose([100] * 28, slow, self.flat)
        cont = correct.proposal("X", rep, 1, 5, 0.03)
        self.assertEqual(cont["status"], "continue")
        self.assertTrue(cont["writes"])
        last = correct.proposal("X", rep, 5, 5, 0.03)
        self.assertEqual(last["status"], "max_rounds")
        self.assertEqual(last["writes"], [])
        self.assertTrue(last["changes"])      # the details stay in changes

    def test_stuck_when_nothing_can_change(self):
        slow = {s: 50.0 for s in self.flat}
        rep = correct.propose([255] * 28, slow, self.flat)
        self.assertEqual(correct.status(rep, 1, 5), "stuck")
        prop = correct.proposal("X", rep, 1, 5, 0.03)
        self.assertEqual((prop["status"], prop["writes"]), ("stuck", []))
        self.assertIn("no entry can change", prop["reason"])
        fast = {s: 200.0 for s in self.flat}
        rep = correct.propose([1] * 28, fast, self.flat)   # all at the floor
        self.assertEqual(correct.status(rep, 1, 5), "stuck")

    def test_stuck_exits_3(self):
        rows = [["B", "reverse", str(s), "", 1, 5, 5, 50.0, 1.0, True, "settled"] for s in (24, 64, 126)]
        rows += [["A", "forward", str(s), "", 1, 5, 5, 100.0, 1.0, True, "settled"] for s in (24, 64, 126)]
        p = profile_csv(rows)
        code = correct.main(["--table", ",".join(["255"] * 28), "--profile", str(p), "--loco", "B",
                             "--direction", "reverse", "--target-loco", "A", "--target-direction",
                             "forward", "--out", str(p.parent / "o")])
        self.assertEqual(code, 3)

    def test_a_zero_entry_that_runs_slow_starts_from_its_neighbour_and_converges(self):
        def speed_of(table, step):
            pts = [(0.0, 0.0)] + [(126.0 * (k + 1) / 28, v) for k, v in enumerate(table)]
            return 430.0 * (0.08 + 0.92 * correct.interp(float(step), pts) / 255.0)  # the decoder's start voltage
        target_table = [round(255 * k / 28) for k in range(1, 29)]
        steps = range(2, 127, 2)
        target = {s: speed_of(target_table, s) for s in steps}
        table = [0, 0] + target_table[2:]
        first = correct.propose(table, {s: speed_of(table, s) for s in steps}, target)
        self.assertGreater(first["values"][0], 3)     # not a creep of +1
        st = ""
        for rnd in range(1, 6):
            rep = correct.propose(table, {s: speed_of(table, s) for s in steps}, target)
            st = correct.status(rep, rnd, 5)
            if st == "done":
                break
            table = rep["values"]
        self.assertEqual(st, "done", (rnd, table[:6]))

    def test_preflight_log_must_be_complete(self):
        good = ["1.0 PREFLIGHT X cvs=3", "1.1 CVS 2,25", "2.0 CV 2 0", "3.0 CV 25 FAIL timeout", "4.0 END"]
        self.assertEqual(pc_problems(good, {2, 25}), ([], []))
        self.assertIn("no END line", pc_problems(good[:-1], {2, 25})[0][0])
        aborted = good[:3] + ["3.5 ABORTED after a read timeout", "4.0 END"]
        probs, missing = pc_problems(aborted, {2, 25})
        self.assertTrue(any("ABORTED" in p for p in probs))
        self.assertEqual(missing, [25])
        self.assertTrue(any("ERROR" in p for p in pc_problems(good + ["5.0 ERROR boom"], {2, 25})[0]))

    def test_preflight_cli_fails_on_a_short_log_and_lists_the_missing(self):
        d = Path(tempfile.mkdtemp())
        ros = d / "r.xml"
        ros.write_text('<locomotive-config><locomotive id="L"><values><CVvalue name="2" value="0"/>'
                       '<CVvalue name="3" value="0"/></values></locomotive></locomotive-config>')
        log = d / "p.log"
        log.write_text("1.0 CV 2 0\n2.0 END\n")
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = pc_main(["--log", str(log), "--roster-xml", str(ros)])
        self.assertEqual(code, 1)
        self.assertIn("missing CVs: 3,4,5,6,25", buf.getvalue())

    def test_every_job_kind_carries_the_active_marker(self):
        d = Path(tempfile.mkdtemp())
        csvp = d / "bl.csv"
        csvp.write_text("user_name,occupancy_sensor,inches,flag,old_source\nTrack Main West,x,220,anyrail,\n")
        make_job.main(["steps", "--loco", "L", "--direction", "forward", "--guard", "none",
                       "--lengths", str(csvp), "--out", str(d / "s.py")])
        make_job.main(["move", "--loco", "L", "--direction", "forward", "--guard", "none",
                       "--until", "BS Switch 33", "--out", str(d / "m.py")])
        make_job.main(["preflight", "--loco", "L", "--out", str(d / "p.py")])
        for name in ("s.py", "m.py", "p.py"):
            self.assertIn("/tmp/speedrun.active", (d / name).read_text(), name)
        pre = (SM / "jython" / "preflight.py").read_text()
        self.assertIn("os.remove", pre)
        self.assertIn('L("CVS "', pre)

    def test_guard_is_required_and_none_is_explicit(self):
        d = Path(tempfile.mkdtemp())
        csvp = d / "bl.csv"
        csvp.write_text("user_name,occupancy_sensor,inches,flag,old_source\nTrack Main West,x,220,anyrail,\n")
        base = ["steps", "--loco", "L", "--direction", "forward", "--lengths", str(csvp), "--out", str(d / "s.py")]
        with self.assertRaises(SystemExit):
            make_job.main(base)
        make_job.main(base + ["--guard", "none"])
        self.assertEqual(effective_settings((d / "s.py").read_text())["GUARD"], [])
        with self.assertRaises(SystemExit):
            make_job.main(base + ["--guard", "none", "--guard", "BS W-1"])
        with self.assertRaises(SystemExit):
            make_job.main(["move", "--loco", "L", "--direction", "forward", "--until", "BS X",
                           "--out", str(d / "m.py")])
        for name in ("step_runner.py", "move_to.py", "stop_test.py"):
            self.assertIn('L("NO GUARD")', mover(name))

    def test_steps_must_be_whole_numbers_1_to_126(self):
        d = Path(tempfile.mkdtemp())
        csvp = d / "bl.csv"
        csvp.write_text("user_name,occupancy_sensor,inches,flag,old_source\nTrack Main West,x,220,anyrail,\n")
        base = ["steps", "--loco", "L", "--direction", "forward", "--lengths", str(csvp), "--guard", "none",
                "--out", str(d / "s.py")]
        for bad in ("0", "127", "2.5", "abc", "24,,48", "24,200"):
            with self.assertRaises(SystemExit, msg=bad):
                make_job.main(base + ["--steps", bad])
        make_job.main(base + ["--steps", "2,126"])
        for bad in ("0", "127", "x"):
            with self.assertRaises(SystemExit, msg=bad):
                make_job.main(["move", "--loco", "L", "--direction", "forward", "--guard", "none",
                               "--until", "BS X", "--step", bad, "--out", str(d / "m.py")])

    def test_one_listener_per_bean_carries_both_roles(self):
        src = mover("step_runner.py")
        self.assertIn("def __init__(self, n, isg)", src)
        self.assertIn("if n == un or n == sn: found[n] = s", src)
        self.assertIn("isg = (un in guard) or (sn in guard)", src)
        self.assertIn("if self.isg and st == 2", src)
        self.assertEqual(src.count("addPropertyChangeListener"), 1)

    def test_analyze_docstring_matches_the_code(self):
        doc = analyze.__doc__
        self.assertIn("anyrail,inferred", doc)
        self.assertIn("assigned", doc)
        self.assertEqual(analyze.DEFAULT_TRUSTED, ("anyrail", "inferred"))


if __name__ == "__main__":
    unittest.main()
