"""Speed-match tools, offline part: the default guard list, the roster profile writer, the stop
test job and its comparison. Shares helpers with test_speedmatch.py.
"""
from __future__ import annotations

import ast
import csv
import json
import re
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lengths_fixture import write_lengths  # noqa: E402
from speedmatch_jython_fake import FakeProfile, FakeRosterEntry, World, run_job  # noqa: E402
from test_speedmatch import SM, ROOT, analyze, make_job  # noqa: E402

sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib.paths import REPO_TABLES_XML  # noqa: E402

sys.path.insert(0, str(SM))
import profile_to_roster as p2r  # noqa: E402
import stoptest_compare as stc  # noqa: E402

TABLES = REPO_TABLES_XML


class DefaultGuard(unittest.TestCase):
    def test_every_name_is_a_sensor_in_tables_xml(self):
        names = set(re.findall(r"<userName>(BS [^<]*)</userName>", TABLES.read_text()))
        for n in make_job.DEFAULT_GUARD:
            self.assertIn(n, names, n)

    def test_no_loop_sensor_is_in_it(self):
        loop = set(analyze.ORDER)
        loop |= {"BS Switch 23a", "BS Switch 37", "BS Switch 39"}
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
        with self.assertRaisesRegex(make_job.JobError, "cannot be combined"):
            make_job.guards(["none", "default"])

    def test_default_reaches_the_job(self):
        d = Path(tempfile.mkdtemp())
        make_job.main(["move", "--loco", "L", "--direction", "forward", "--guard", "default",
                       "--until", "BS Switch 33", "--out", str(d / "m.py")])
        ns: dict = {}
        exec(compile((d / "m.py").read_text().split(make_job.RUNNER_MARK)[0], "job", "exec"), ns)
        self.assertEqual(ns["GUARD"], make_job.DEFAULT_GUARD)


def say(log):
    """The log lines without their time stamps."""
    return [line.split(" ", 1)[1] for line in log]


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

    def test_merge_takes_each_step_from_the_latest_complete_run_that_settled_it(self):
        rows = (rows_for("A", "forward", 1, [8, 16, 24, 48]) + rows_for("A", "forward", 4, [8, 16, 24])
                + rows_for("A", "forward", 6, [16], complete=False)
                + rows_for("A", "reverse", 2, [8, 16, 24, 48]) + rows_for("A", "reverse", 5, [8], reason="max"))
        for r in rows:
            if r["run"] == "4":
                r["median_mm_s"] = str(float(r["median_mm_s"]) + 1)   # the re-run after a CV change
            if r["run"] == "6":
                r["median_mm_s"] = "999"                              # incomplete: never used
        pl = p2r.build_payload(as_csv(rows), "A", merge=True)
        fwd = {p["step"]: p["forward_mm_s"] for p in pl["points"]}
        self.assertEqual(fwd, {8: 81.0, 16: 161.0, 24: 241.0, 48: 480.0})
        src = {s["step"]: (s["forward_run"], s["reverse_run"]) for s in pl["sources"]}
        self.assertEqual(src[16], (4, 2))
        self.assertEqual(src[48], (1, 2))
        self.assertEqual(src[8], (4, 2))   # run 5 did not settle step 8
        # without merge only the latest complete run counts: reverse run 5 settled nothing
        with self.assertRaises(p2r.ProfileRefusal):
            p2r.build_payload(as_csv(rows), "A")

    def test_merge_orders_runs_by_log_time_not_run_number(self):
        rows = rows_for("A", "forward", 1, [16]) + rows_for("A", "forward", 2, [16]) + rows_for("A", "reverse", 3, [16])
        rows[0]["median_mm_s"] = "170"; rows[1]["median_mm_s"] = "150"
        rows[0]["log"] = "steprun_A_forward_20261113_171458.log"   # run 1 is the newer one
        rows[1]["log"] = "steprun_A_forward_20261113_125138.log"
        rows[2]["log"] = "steprun_A_reverse_20261113_120000.log"
        d = Path(tempfile.mkdtemp()) / "profile.csv"
        with open(d, "w", newline="") as fh:
            w = csv.DictWriter(fh, ["loco", "direction", "step", "reason", "median_mm_s", "run", "run_complete", "log"])
            w.writeheader(); w.writerows(rows)
        pl = p2r.build_payload(d, "A", merge=True)
        self.assertEqual(pl["points"][0]["forward_mm_s"], 170.0)
        self.assertEqual(pl["sources"][0]["forward_run"], 1)

    def test_the_csv_is_read_by_correct_read_profile(self):
        csv_path = as_csv(rows_for("A", "forward", 1, [16]) + rows_for("A", "reverse", 2, [16]))
        with mock.patch.object(p2r.correct, "read_profile", wraps=p2r.correct.read_profile) as spy:
            p2r.build_payload(csv_path, "A")
        self.assertEqual([c.args[1:3] for c in spy.call_args_list], [("A", "forward"), ("A", "reverse")])

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

    def test_payload_points_of_the_wrong_shape_are_refused_without_a_traceback(self):
        for points, fragment in (([[8, 10.0, 11.0]], "is not an object"), ({"step": 8}, "is not a list")):
            d = self.payload(points=points)
            with self.assertRaises(SystemExit) as cm:
                make_job.main(["profile", "--payload", str(d / "p.json"), "--out", str(d / "j.py")])
            self.assertIn(fragment, str(cm.exception))
            self.assertFalse((d / "j.py").exists())

    def test_a_payload_that_cannot_be_read_is_refused_without_a_traceback(self):
        d = Path(tempfile.mkdtemp())
        (d / "list.json").write_text("[]")
        (d / "bad.json").write_text("{")
        for name, fragment in (("missing.json", "cannot read the payload"), ("bad.json", "is not JSON"),
                               ("list.json", "is not an object")):
            with self.assertRaises(SystemExit) as cm:
                make_job.main(["profile", "--payload", str(d / name), "--out", str(d / "j.py")])
            self.assertIn(fragment, str(cm.exception))
            self.assertIsInstance(cm.exception.__cause__, make_job.JobError)
        self.assertFalse((d / "j.py").exists())

    def test_a_point_without_a_whole_step_is_a_job_error(self):
        for point in ({"forward_mm_s": 8.0, "reverse_mm_s": 9.0}, {"step": "x", "forward_mm_s": 8.0, "reverse_mm_s": 9.0},
                      {"step": 127, "forward_mm_s": 8.0, "reverse_mm_s": 9.0}):
            with self.assertRaisesRegex(make_job.JobError, "payload point"):
                make_job.profile_point(point)
        self.assertEqual(make_job.profile_point({"step": 63, "forward_mm_s": 1, "reverse_mm_s": 2.5}),
                         {"key": 500, "step": 63, "forward": 1.0, "reverse": 2.5})

    def test_two_points_on_one_throttle_key_are_refused(self):
        d = self.payload(points=[{"step": 2, "forward_mm_s": 8.0, "reverse_mm_s": 9.0}] * 2)
        with self.assertRaisesRegex(SystemExit, "share a throttle key"):
            make_job.main(["profile", "--payload", str(d / "p.json"), "--out", str(d / "j.py")])

    def run_profile(self, *extra, points=None, entry=True, fail_on_update=False, marker=False):
        """The generated job, run against a fake roster that offers nothing but the roster entry."""
        d = self.payload()
        make_job.main(["profile", "--payload", str(d / "p.json"), "--out", str(d / "j.py"), *extra])
        world = World()
        world.files.names |= {"/tmp/speedrun.active"} if marker else set()
        if entry:
            profile = None if points is None else FakeProfile(points, world.calls)
            world.entries["CSX 2121"] = FakeRosterEntry(profile, world.calls, fail_on_update)
        return run_job((d / "j.py").read_text(), world)

    def test_a_dry_run_logs_old_and_new_and_changes_nothing(self):
        res = self.run_profile(points={500: (200.0, 210.0)})
        self.assertEqual(res.world.entries["CSX 2121"].profile.points, {500: (200.0, 210.0)})
        self.assertEqual(res.world.calls, [])
        log = " | ".join(say(res.log))
        for want in ("PROFILE loco=CSX 2121 apply=False", "OLD 1 points", "NEW 2 points",
                     "STOP dry run: nothing changed", "END"):
            self.assertIn(want, log)
        self.assertEqual(res.world.files.markers(), set())  # the marker is gone again

    def test_apply_clears_sets_the_points_then_saves_the_entry_and_the_roster(self):
        res = self.run_profile("--apply", points={500: (200.0, 210.0)})
        self.assertEqual(res.world.entries["CSX 2121"].profile.points, {16: (8.0, 9.0), 1000: (430.0, 425.0)})
        self.assertEqual(res.world.calls, ["clearCurrentProfile", "setSpeed", "setSpeed", "updateFile", "writeRoster"])
        self.assertIn("STOP written", say(res.log))
        self.assertEqual(res.world.files.markers(), set())

    def test_apply_on_an_entry_without_a_profile_makes_one(self):
        res = self.run_profile("--apply")
        self.assertIn("STOP written", say(res.log))
        self.assertEqual(res.world.entries["CSX 2121"].profile.points, {16: (8.0, 9.0), 1000: (430.0, 425.0)})

    def test_a_missing_entry_stops_before_any_write(self):
        res = self.run_profile("--apply", entry=False)
        self.assertIn("STOP roster entry not found: CSX 2121", say(res.log))
        self.assertEqual(res.world.calls, [])

    def test_another_runner_holds_the_marker_and_keeps_it(self):
        res = self.run_profile("--apply", points={}, marker=True)
        self.assertEqual(say(res.log)[-2:], ["STOP another runner is active", "END"])
        self.assertEqual(res.world.calls, [])
        self.assertEqual(res.world.files.markers(), {"/tmp/speedrun.active"})

    def test_a_failed_save_is_logged_and_the_marker_removed(self):
        res = self.run_profile("--apply", points={}, fail_on_update=True)
        self.assertTrue("ERROR disk full" in say(res.log))
        self.assertIn("STOP error", say(res.log))
        self.assertEqual(say(res.log)[-1], "END")
        self.assertEqual(res.world.files.markers(), set())
        self.assertNotIn("writeRoster", res.world.calls)

    def test_the_job_uses_nothing_but_the_roster(self):
        # the fake JMRI has no throttle, power, turnout or CV classes: a job that reached for one logs ERROR
        res = self.run_profile("--apply", points={})
        self.assertFalse([m for m in say(res.log) if m.startswith("ERROR")])


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

    def drive(self, on_go=None, guard="none", sensors_active=(), world=None, replace=None):
        """Run the generated stop test against the fake JMRI: trigger BS Switch 33, guard sensor BS W-1,
        a loop sensor BS K-2. on_go(world, sensors) runs when the throttle gets its first speed."""
        text, _ = self.build("--guard", guard)
        if replace:
            text = text.replace(*replace)
        world = world or World()
        world.entries["CSX 2121"] = object()
        names = (("BS Switch 33", "IS33"), ("BS W-1", "IS1"), ("BS K-2", "IS2"))
        s = {n: world.sensor(n, sysn, 2 if n in sensors_active else 4) for n, sysn in names}
        if on_go:
            world.throttle.on_speed = lambda v: on_go(world, s) if v > 0 else None
        return run_job(text, world), s

    def test_the_loco_runs_to_the_trigger_and_is_stopped_with_its_own_throttle(self):
        def go(world, s):
            world.clock.after(5.0, lambda: s["BS Switch 33"].fire(2))
            world.clock.after(6.0, lambda: s["BS K-2"].fire(2))
        res, _ = self.drive(go)
        log = say(res.log)
        stop_at = log.index("STOPCMD trigger BS Switch 33")
        self.assertIn("SENS BS K-2 ACTIVE", log[stop_at:])
        self.assertIn("STOP quiet", log)
        self.assertEqual(res.world.throttle.speeds(), [96 / 126.0, 0.0, 0.0])  # go, the trigger's stop, the end
        self.assertTrue(res.world.throttle.released())
        self.assertEqual(res.world.files.markers(), set())
        self.assertFalse([m for m in log if m.startswith(("ERROR", "LISTENER ERROR"))])
        self.assertEqual([s.listeners for s in res.world.sensors], [[], [], []])  # listeners removed at the end

    def test_a_trigger_lit_before_the_loco_was_sent_off_is_ignored_and_ends_the_run(self):
        res, _ = self.drive(lambda world, s: s["BS Switch 33"].fire(2))
        log = say(res.log)
        self.assertIn("TRIGGER BS Switch 33 lit before arming, ignored", log)
        self.assertIn("STOP trigger ACTIVE when armed: BS Switch 33", log)
        self.assertFalse([m for m in log if m.startswith("STOPCMD")])
        self.assertEqual(res.world.throttle.speeds(), [96 / 126.0, 0.0])

    def test_a_guard_lighting_ends_the_run_with_speed_zero(self):
        res, _ = self.drive(lambda world, s: world.clock.after(3.0, lambda: s["BS W-1"].fire(2)), guard="BS W-1")
        self.assertIn("STOP guard BS W-1", say(res.log))
        self.assertEqual(res.world.throttle.speeds(), [96 / 126.0, 0.0])

    def test_the_kill_file_ends_the_run(self):
        res, _ = self.drive(lambda world, s: world.clock.after(2.0, lambda: world.files.names.add("/tmp/speedrun.kill")))
        self.assertIn("STOP killed", say(res.log))
        self.assertEqual(res.world.throttle.speeds()[-1], 0.0)

    def test_the_trigger_never_lighting_ends_the_run_at_max_s(self):
        res, _ = self.drive(lambda world, s: None)
        self.assertTrue(any(m.startswith("STOP time: trigger not reached") for m in say(res.log)))
        self.assertEqual(res.world.throttle.speeds(), [96 / 126.0, 0.0])

    def test_nothing_moves_when_the_trigger_or_a_guard_is_not_ready(self):
        cases = (
            ({"sensors_active": ("BS Switch 33",)}, "STOP trigger already ACTIVE: BS Switch 33"),
            ({"guard": "BS W-1", "sensors_active": ("BS W-1",)}, "STOP guard already ACTIVE: BS W-1"),
            ({"guard": "BS Nowhere"}, "STOP guard sensor not found: BS Nowhere"),
            ({"guard": "BS W-1", "replace": ("GUARD = ['BS W-1']", "GUARD = ['IS33']")},
             "STOP trigger is also a guard: IS33"),
        )
        for kwargs, stop in cases:
            res, _ = self.drive(**kwargs)
            self.assertIn(stop, say(res.log), kwargs)
            self.assertEqual(res.world.throttle_requests, [], kwargs)
            self.assertEqual(res.world.throttle.calls, [], kwargs)
            self.assertEqual(res.world.files.markers(), set(), kwargs)

    def test_no_throttle_is_a_reason_and_no_speed_is_sent(self):
        world = World()
        world.answer_throttle = False
        res, _ = self.drive(world=world)
        self.assertIn("STOP no throttle", say(res.log))
        self.assertEqual(world.throttle.calls, [])

    def test_the_job_calls_only_the_throttle_methods_a_stop_test_may(self):
        # the fake throttle raises on any other call (e-stop, power, CV); the job would log it as ERROR
        res, _ = self.drive(lambda world, s: world.clock.after(5.0, lambda: s["BS Switch 33"].fire(2)))
        self.assertFalse([m for m in say(res.log) if "ERROR" in m or "failed" in m])

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
        # Structure of the generated text and of the runner sources: no run shows a second copy.
        d = Path(tempfile.mkdtemp())
        csvp = d / "bl.csv"
        write_lengths(csvp, {"Track Main West": (231, 220)})
        make_job.main(["steps", "--loco", "L", "--direction", "forward", "--guard", "none",
                       "--lengths", str(csvp), "--out", str(d / "a.py")])
        make_job.main(["move", "--loco", "L", "--direction", "forward", "--guard", "none",
                       "--until", "BS Switch 33", "--out", str(d / "b.py")])
        make_job.main(["stoptest", "--loco", "L", "--direction", "forward", "--step", "32", "--guard", "none",
                       "--trigger", "BS Switch 33", "--out", str(d / "c.py")])
        for name in ("a.py", "b.py", "c.py"):
            text = (d / name).read_text()
            self.assertEqual(text.count("# jobkit.py - "), 1, name)
            defined = [n.name for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
            self.assertEqual(defined.count("end_job"), 1, name)
            self.assertEqual(defined.count("TL"), 1, name)
        kit = {n.name for n in ast.parse((SM / "jython" / "jobkit.py").read_text()).body
               if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for name in self.MOVERS:
            tree = ast.parse((SM / "jython" / name).read_text())
            own = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
            assigned = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
            self.assertEqual(own & kit - {"SL"}, set(), "%s keeps its own copy of a kit function" % name)
            self.assertEqual(assigned & {"NAMES", "reg", "why", "ab", "own", "hit"}, set(), name)

    def kit(self):
        world = World()
        world.entries["X"] = object()
        res = run_job("LOGF = '/kit.log'\nORDER = []\n" + (SM / "jython" / "jobkit.py").read_text(), world)
        return res.ns, world

    def test_a_throttle_that_arrives_is_returned(self):
        ns, world = self.kit()
        t, _ = ns["request_throttle"]("X")
        self.assertIs(t, world.throttle)

    def test_throttle_timeout_is_a_reason_and_a_late_throttle_is_released(self):
        ns, world = self.kit()
        world.answer_throttle = False
        t, tl = ns["request_throttle"]("X")
        self.assertIsNone(t)
        self.assertEqual(ns["why"][0], "no throttle")
        tl.notifyThrottleFound(world.throttle)  # it arrives after the caller gave up
        self.assertTrue(world.throttle.released())
        self.assertIsNone(tl.t)
        self.assertIn("late throttle released", say(world.files.written("/kit.log").splitlines()))

    def test_an_unknown_roster_entry_is_a_reason(self):
        ns, world = self.kit()
        self.assertEqual(ns["request_throttle"]("Y"), (None, None))
        self.assertEqual(ns["why"][0], "roster entry not found: Y")
        self.assertEqual(world.throttle_requests, [])

    def test_the_jython_sources_have_no_f_strings(self):
        # Jython 2.7 cannot parse them, and only the source shows it: the jobs are never run under Jython here
        for path in sorted((SM / "jython").glob("*.py")):
            nodes = ast.walk(ast.parse(path.read_text()))
            self.assertFalse([n for n in nodes if isinstance(n, ast.JoinedStr)], path.name)


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
    A = [("BS East Lead", 0.72), ("BS Switch 35a", 6.42), ("BS Switch 37", 7.26), ("BS K-2", 8.22)]
    B = [("BS East Lead", 0.74), ("BS Switch 35a", 6.42), ("BS Switch 37", 7.26), ("BS K-2", 8.13)]

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
