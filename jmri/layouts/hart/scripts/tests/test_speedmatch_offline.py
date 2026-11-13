"""Speed-match tools, offline part: the default guard list, the roster profile writer, the stop
test job and its comparison. Shares helpers with test_speedmatch.py.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_speedmatch import FORBIDDEN_EVERYWHERE, SM, analyze, make_job, mover  # noqa: E402

sys.path.insert(0, str(SM))
import profile_to_roster as p2r  # noqa: E402
import stoptest_compare as stc  # noqa: E402

TABLES = SM.parents[1] / "output" / "tables.xml"


class DefaultGuard(unittest.TestCase):
    def test_every_name_is_a_sensor_in_tables_xml(self):
        names = set(re.findall(r"<userName>(BS [^<]*)</userName>", TABLES.read_text()))
        for n in make_job.DEFAULT_GUARD:
            self.assertIn(n, names, n)

    def test_no_loop_sensor_is_in_it(self):
        loop = set(analyze.ORDER)
        loop |= {"BS Switch 23a", "BS Switch 37 / BS McKeesport", "BS Switch 39 / BS McKees Rocks"}
        for n in make_job.DEFAULT_GUARD:
            self.assertNotIn(n, loop, n)
            self.assertNotIn(n.split(" / ")[0], loop)
        self.assertEqual(len(set(make_job.DEFAULT_GUARD)), len(make_job.DEFAULT_GUARD))

    def test_every_block_sensor_off_the_loop_is_in_it(self):
        names = set(re.findall(r"<userName>(BS [^<]*)</userName>", TABLES.read_text()))
        off_loop = names - set(analyze.ORDER)
        self.assertEqual(off_loop - set(make_job.DEFAULT_GUARD), set())

    def test_default_expands_and_combines(self):
        self.assertEqual(make_job.guards(["default"]), make_job.DEFAULT_GUARD)
        got = make_job.guards(["BS Extra", "default", "BS W-1"])
        self.assertEqual(got[0], "BS Extra")
        self.assertEqual(got.count("BS W-1"), 1)
        self.assertEqual(len(got), len(make_job.DEFAULT_GUARD) + 1)
        with self.assertRaises(SystemExit):
            make_job.guards(["none", "default"])

    def test_default_reaches_the_job(self):
        d = Path(tempfile.mkdtemp())
        make_job.main(["move", "--loco", "L", "--direction", "forward", "--guard", "default",
                       "--until", "BS Switch 33", "--out", str(d / "m.py")])
        ns: dict = {}
        exec(compile((d / "m.py").read_text().split(make_job.RUNNER_MARK)[0], "job", "exec"), ns)
        self.assertEqual(ns["GUARD"], make_job.DEFAULT_GUARD)


def rows_for(loco, direction, run, steps, complete=True, reason="settled"):
    return [{"loco": loco, "direction": direction, "step": str(s), "reason": reason,
             "median_mm_s": str(10.0 * int(str(s).split("#")[0])), "run": str(run), "run_complete": str(complete)}
            for s in steps]


def as_csv(rows):
    d = Path(tempfile.mkdtemp())
    p = d / "profile.csv"
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, ["loco", "direction", "step", "reason", "median_mm_s", "run", "run_complete"])
        w.writeheader()
        w.writerows(rows)
    return p


class ProfileToRoster(unittest.TestCase):
    def test_latest_complete_run_settled_steps_only(self):
        rows = (rows_for("A", "forward", 1, [2, 4]) + rows_for("A", "forward", 3, [2, 4, 126])
                + rows_for("A", "forward", 5, [2], complete=False)
                + rows_for("A", "forward", 3, ["126#2"])
                + rows_for("A", "forward", 3, [64], reason="max")
                + rows_for("A", "reverse", 2, [2, 4, 126]))
        rows[0]["median_mm_s"] = "999"  # run 1 is not the latest
        pl = p2r.build_payload(as_csv(rows), "A")
        self.assertEqual([p["step"] for p in pl["points"]], [2, 4, 126])
        self.assertEqual(pl["points"][0], {"step": 2, "forward_mm_s": 20.0, "reverse_mm_s": 20.0})

    def test_steps_in_one_direction_only_are_left_out_and_named(self):
        rows = rows_for("A", "forward", 1, [2, 4, 8]) + rows_for("A", "reverse", 2, [2, 4])
        pl = p2r.build_payload(as_csv(rows), "A")
        self.assertEqual([p["step"] for p in pl["points"]], [2, 4])
        self.assertEqual(pl["skipped_steps"], [8])

    def test_refuses_a_missing_direction_or_no_complete_run(self):
        with self.assertRaises(p2r.ProfileRefusal):
            p2r.build_payload(as_csv(rows_for("A", "forward", 1, [2])), "A")
        with self.assertRaises(p2r.ProfileRefusal):
            p2r.build_payload(as_csv(rows_for("A", "forward", 1, [2]) + rows_for("A", "reverse", 2, [2], complete=False)), "A")
        with self.assertRaises(p2r.ProfileRefusal):
            p2r.build_payload(as_csv(rows_for("A", "forward", 1, [2], reason="max") + rows_for("A", "reverse", 2, [2])), "A")
        with self.assertRaises(p2r.ProfileRefusal):  # nothing in common
            p2r.build_payload(as_csv(rows_for("A", "forward", 1, [2]) + rows_for("A", "reverse", 2, [4])), "A")
        with self.assertRaises(p2r.ProfileRefusal):  # another loco's rows do not count
            p2r.build_payload(as_csv(rows_for("B", "forward", 1, [2]) + rows_for("B", "reverse", 2, [2])), "A")

    def test_the_csv_is_read_by_correct_read_profile(self):
        self.assertIn("correct.read_profile", (SM / "profile_to_roster.py").read_text())

    def test_cli_reads_the_analysis_csv_and_refuses_with_a_message(self):
        d = Path(tempfile.mkdtemp())
        head = ["loco", "direction", "step", "travel", "blocks_per_reading", "readings", "readings_used",
                "median_mm_s", "rel_sd_pct", "settled", "reason", "run", "run_complete", "log"]
        with open(d / "profile.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(head)
            w.writerow(["A", "forward", "126", "east", 1, 5, 5, 430.0, 1.0, True, "settled", 1, True, "x"])
            w.writerow(["A", "reverse", "126", "west", 1, 5, 5, 425.5, 1.0, True, "settled", 2, True, "x"])
        p2r.main([str(d / "profile.csv"), "--loco", "A", "--out", str(d / "p.json")])
        self.assertEqual(json.loads((d / "p.json").read_text())["points"],
                         [{"step": 126, "forward_mm_s": 430.0, "reverse_mm_s": 425.5}])
        with self.assertRaises(SystemExit) as cm:
            p2r.main([str(d / "profile.csv"), "--loco", "B", "--out", str(d / "q.json")])
        self.assertIn("refused", str(cm.exception))

    def test_key_is_the_throttle_setting_times_1000(self):
        self.assertEqual(p2r.throttle_key(126), 1000)
        self.assertEqual(p2r.throttle_key(63), 500)
        self.assertEqual(p2r.throttle_key(2), 16)


class ProfileJob(unittest.TestCase):
    def payload(self, **kw):
        d = Path(tempfile.mkdtemp())
        pl = {"roster_id": "CSX 2121", "points": [
            {"step": 2, "forward_mm_s": 8.0, "reverse_mm_s": 9.0},
            {"step": 126, "forward_mm_s": 430.0, "reverse_mm_s": 425.0}]}
        pl.update(kw)
        (d / "p.json").write_text(json.dumps(pl))
        return d

    def settings(self, d, *extra):
        make_job.main(["profile", "--payload", str(d / "p.json"), "--out", str(d / "j.py"), *extra])
        text = (d / "j.py").read_text()
        ns: dict = {}
        exec(compile(text.split("# write_profile.py")[0], "job", "exec"), ns)
        return text, ns

    def test_settings_and_dry_run_by_default(self):
        text, ns = self.settings(self.payload())
        self.assertEqual(ns["P_ID"], "CSX 2121")
        self.assertIs(ns["APPLY"], False)
        self.assertEqual([(p["key"], p["forward"], p["reverse"]) for p in ns["POINTS"]],
                         [(16, 8.0, 9.0), (1000, 430.0, 425.0)])
        _, ns = self.settings(self.payload(), "--apply")
        self.assertIs(ns["APPLY"], True)

    def test_refuses_a_point_with_a_missing_speed(self):
        d = self.payload(points=[{"step": 2, "forward_mm_s": 8.0}])
        with self.assertRaises(SystemExit):
            make_job.main(["profile", "--payload", str(d / "p.json"), "--out", str(d / "j.py")])
        d = self.payload(points=[])
        with self.assertRaises(SystemExit):
            make_job.main(["profile", "--payload", str(d / "p.json"), "--out", str(d / "j.py")])

    def test_script_only_touches_the_roster_entry(self):
        src = (SM / "jython" / "write_profile.py").read_text()
        for bad in FORBIDDEN_EVERYWHERE + ["Throttle", "setSpeedSetting", "readCV", "writeCV", "Programmer",
                                           "emergency", "OpsMode"]:
            self.assertNotIn(bad, src, bad)
        for need in ["clearCurrentProfile", "updateFile()", "writeRoster()", "APPLY is not True",
                     "/tmp/speedrun.active", "os.remove", 'L("END")', "java.lang.Throwable", "except Exception, e",
                     'show("OLD"', 'show("NEW"']:
            self.assertIn(need, src, need)
        self.assertLess(src.index("APPLY is not True"), src.index("clearCurrentProfile"))
        self.assertNotRegex(src, r"\bf[\"']")


class StopTestJob(unittest.TestCase):
    def build(self, *extra):
        d = Path(tempfile.mkdtemp())
        make_job.main(["stoptest", "--loco", "CSX 2121", "--direction", "reverse", "--step", "96",
                       "--trigger", "BS Switch 33", "--out", str(d / "s.py"), *extra])
        text = (d / "s.py").read_text()
        ns: dict = {}
        exec(compile(text.split(make_job.RUNNER_MARK)[0], "job", "exec"), ns)
        return text, ns

    def test_settings(self):
        _, ns = self.build("--guard", "default")
        self.assertEqual((ns["P_ID"], ns["P_FWD"], ns["P_STEP"], ns["TRIGGER"]),
                         ("CSX 2121", False, 96, "BS Switch 33"))
        self.assertEqual(ns["GUARD"], make_job.DEFAULT_GUARD)
        self.assertEqual((ns["SETTLE_S"], ns["QUIET_S"]), (30.0, 10.0))
        self.assertEqual(ns["FUNCS"], [0])
        _, ns = self.build("--guard", "none", "--settle-s", "20", "--mute-sound")
        self.assertEqual((ns["GUARD"], ns["SETTLE_S"], ns["FUNCS"]), ([], 20.0, [0, 8]))

    def test_guard_is_required_and_the_trigger_cannot_be_a_guard_or_off_loop(self):
        d = Path(tempfile.mkdtemp())
        base = ["stoptest", "--loco", "L", "--direction", "forward", "--step", "32", "--out", str(d / "s.py")]
        with self.assertRaises(SystemExit):
            make_job.main(base + ["--trigger", "BS Switch 33"])
        with self.assertRaises(SystemExit):
            make_job.main(base + ["--trigger", "BS Switch 33", "--guard", "BS Switch 33"])
        with self.assertRaises(SystemExit):
            make_job.main(base + ["--trigger", "BS W-1", "--guard", "none"])

    def test_script_stops_with_its_own_throttle_and_arms_after_go(self):
        src = (SM / "jython" / "stop_test.py").read_text()
        kit = mover("stop_test.py")
        for bad in FORBIDDEN_EVERYWHERE + ["readCV", "writeCV", "Programmer", "emergency", "OpsMode"]:
            self.assertNotIn(bad, kit, bad)
        for need in ["/tmp/speedrun.kill", "trigger already ACTIVE", "STOPCMD", "SETTLE_S", "QUIET_S",
                     "settled, then guard", "trigger ACTIVE when armed", "lit before arming, ignored"]:
            self.assertIn(need, src, need)
        # the throttle is given to the stop only after the loco was sent off
        self.assertLess(src.index("t.setSpeedSetting(P_STEP / 126.0)"), src.index('box["t"] = t; box["armed"] = True'))
        self.assertLess(src.index('box["armed"] = True'), src.index("trigger ACTIVE when armed"))
        # the trigger and the guards are compared as beans, and the log uses the resolved name
        self.assertIn("found[g] == trig", src)
        self.assertIn("trig.getUserName() or trig.getSystemName()", src)
        self.assertNotRegex(kit, r"\bf[\"']")

    def test_trigger_must_be_a_loop_sensor_by_user_name(self):
        d = Path(tempfile.mkdtemp())
        base = ["stoptest", "--loco", "L", "--direction", "forward", "--step", "32", "--guard", "none",
                "--out", str(d / "s.py")]
        with self.assertRaises(SystemExit) as cm:
            make_job.main(base + ["--trigger", "M2S1302"])
        self.assertIn("system names are refused", str(cm.exception))
        with self.assertRaises(SystemExit):
            make_job.main(base + ["--trigger", "BS Switch 7"])  # off the loop (Switch 7b is on it)
        make_job.main(base + ["--trigger", "BS Switch 33"])


class Jobkit(unittest.TestCase):
    MOVERS = ("step_runner.py", "move_to.py", "stop_test.py")

    def test_each_job_has_the_kit_once_and_the_runners_keep_no_copy(self):
        d = Path(tempfile.mkdtemp())
        csvp = d / "bl.csv"
        csvp.write_text("user_name,occupancy_sensor,inches,flag,old_source\nTrack Main West,x,220,anyrail,\n")
        make_job.main(["steps", "--loco", "L", "--direction", "forward", "--guard", "none",
                       "--lengths", str(csvp), "--out", str(d / "a.py")])
        make_job.main(["move", "--loco", "L", "--direction", "forward", "--guard", "none",
                       "--until", "BS Switch 33", "--out", str(d / "b.py")])
        make_job.main(["stoptest", "--loco", "L", "--direction", "forward", "--step", "32", "--guard", "none",
                       "--trigger", "BS Switch 33", "--out", str(d / "c.py")])
        for name in ("a.py", "b.py", "c.py"):
            text = (d / name).read_text()
            self.assertEqual(text.count("# jobkit.py - "), 1, name)
            self.assertEqual(text.count("def end_job("), 1, name)
            self.assertEqual(text.count("class TL("), 1, name)
        for name in self.MOVERS:
            src = (SM / "jython" / name).read_text()
            for dup in ("class TL(", "def L(", "requestThrottle", "/tmp/speedrun.active\", \"w\"", "getNamedBeanSet",
                        "removePropertyChangeListener", "throttle released", "NAMES = "):
                self.assertNotIn(dup, src, "%s keeps its own copy of %s" % (name, dup))

    def test_throttle_timeout_is_a_reason_and_a_late_throttle_is_released(self):
        kit = (SM / "jython" / "jobkit.py").read_text()
        self.assertIn('why[0] or "no throttle"', kit)
        self.assertIn("gave_up", kit)
        late = kit.split("def notifyThrottleFound")[1].split("def notifyFailed")[0]
        self.assertIn("t.release(self)", late)
        self.assertIn("late = self.gave_up", late)
        self.assertNotRegex(kit, r"\bf[\"']")


def stop_log(shift, enters, rest_active, never_stopped=False):
    lines = ["100.0 STOPTEST loco=CSX 2121 direction=reverse step=96 trigger=BS Switch 33",
             "101.0 GO CSX 2121 step 96", "109.0 SENS BS Switch 7b ACTIVE"]
    if not never_stopped:
        lines += ["110.0 STOPCMD trigger BS Switch 33", "110.01 SENS BS Switch 33 ACTIVE"]
    for sensor, dt in enters:
        lines.append("%.2f SENS %s ACTIVE" % (110.0 + dt + shift, sensor))
        if sensor != rest_active:
            lines.append("%.2f SENS %s INACTIVE" % (110.0 + dt + shift + 0.5, sensor))
    lines += ["140.0 STOP settle time", "140.0 speed 0", "140.1 END"]
    return lines


class RunOrder(unittest.TestCase):
    def test_latest_means_latest_by_log_time_not_command_line_order(self):
        def log(t, speed_scale):
            ev = ["%.1f RUN loco=A direction=forward" % t, "%.1f STEP 24" % (t + 1)]
            for i, n in enumerate(analyze.ORDER[:6]):
                ev.append("%.1f SENS %s ACTIVE" % (t + 2 + i * speed_scale, n))
                ev.append("%.1f SENS %s INACTIVE" % (t + 2.1 + i * speed_scale, n))
            ev.append("%.1f STOP all steps complete" % (t + 100))
            return ev
        lengths = {n: 1000.0 for n in analyze.ORDER}
        old, new = log(1000.0, 10.0), log(5000.0, 5.0)
        runs = []
        for lines, name in ((new, "new.log"), (old, "old.log")):  # newest first on the command line
            runs += analyze.parse_log(lines, source=name)
        summaries = analyze.summarize_runs(runs, lengths)
        self.assertEqual([r["log"] for r in summaries], ["old.log", "new.log"])
        self.assertEqual([r["run"] for r in summaries], [1, 2])
        self.assertEqual(analyze.latest_runs(summaries)[("A", "forward")], summaries[1]["rows"])


class StopCompare(unittest.TestCase):
    A = [("BS East Lead", 0.72), ("BS Switch 35a", 6.42), ("BS Switch 37 / BS McKeesport", 7.26), ("BS K-2", 8.22)]
    B = [("BS East Lead", 0.74), ("BS Switch 35a", 6.42), ("BS Switch 37 / BS McKeesport", 7.26), ("BS K-2", 8.13)]

    def test_seconds_after_the_command_and_resting_block(self):
        r = stc.parse_stoptest(stop_log(0, self.A, "BS K-2"))
        self.assertEqual(r["loco"], "CSX 2121")
        self.assertEqual(r["enters"][0], ("BS East Lead", 0.72))
        self.assertNotIn("BS Switch 7b", dict(r["enters"]))  # lit before the command
        self.assertEqual(r["rest"], "BS K-2")
        self.assertTrue(r["complete"])

    def test_table_compares_two_logs(self):
        a = stc.parse_stoptest(stop_log(0, self.A, "BS K-2"))
        b = stc.parse_stoptest(stop_log(0, self.B, "BS K-2"))
        t = stc.table(a, b)
        self.assertIn("| enters East Lead | 0.72 | 0.74 | +0.02 |", t)
        self.assertIn("| enters K-2 | 8.22 | 8.13 | -0.09 |", t)
        self.assertIn("| comes to rest | in K-2 | in K-2 | same block |", t)

    def test_the_trigger_is_left_out_whatever_its_name(self):
        lines = stop_log(0, self.A, "BS K-2")
        lines.insert(4, "110.02 SENS BS Switch 33 ACTIVE")
        r = stc.parse_stoptest(lines)
        self.assertNotIn("BS Switch 33", dict(r["enters"]))

    def test_a_log_without_a_stop_command_is_refused(self):
        d = Path(tempfile.mkdtemp())
        (d / "a.log").write_text("\n".join(stop_log(0, [], "x", never_stopped=True)))
        (d / "b.log").write_text("\n".join(stop_log(0, self.B, "BS K-2")))
        with self.assertRaises(SystemExit):
            stc.main([str(d / "a.log"), str(d / "b.log")])
        (d / "a.log").write_text("\n".join(stop_log(0, self.A, "BS K-2")))
        stc.main([str(d / "a.log"), str(d / "b.log"), "--out", str(d / "t.md")])
        self.assertIn("comes to rest", (d / "t.md").read_text())


if __name__ == "__main__":
    unittest.main()
