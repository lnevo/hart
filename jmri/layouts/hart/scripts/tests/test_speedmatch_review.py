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
from test_speedmatch import FORBIDDEN_EVERYWHERE, SM, analyze, correct, lr, make_job  # noqa: E402


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
        p.write_text("user_name,occupancy_sensor,inches,flag,old_source\nTrack Main West,x,220,assigned,\n")
        return d, p

    def test_owner_settings_beat_the_liverule_defaults(self):
        d, p = self.lengths_csv()
        make_job.main(["steps", "--loco", "CSX 2121", "--direction", "forward", "--out", str(d / "j.py"),
                       "--lengths", str(p), "--k", "7", "--rel", "0.05", "--max", "20", "--settle", "4",
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
        self.assertIn('reason == "settled" and readings', src)


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
        src = (SM / "jython" / "step_runner.py").read_text()
        for name in ("UNKNOWN", "INCONSISTENT"):
            self.assertIn('"%s"' % name, src)
        self.assertIn("state[self.n] = st", src)
        self.assertIn("LENGTHS ", src)


class Guards(unittest.TestCase):
    def test_guard_sensors_are_found_by_any_name_and_checked_at_start(self):
        for name in ("step_runner.py", "move_to.py"):
            src = (SM / "jython" / name).read_text()
            self.assertIn("guard already ACTIVE", src)
            self.assertIn("not found", src)
        src = (SM / "jython" / "step_runner.py").read_text()
        self.assertIn("getSystemName", src)
        self.assertIn("g is not None or", src)  # listened to whatever its name starts with


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
        exec(compile(text.split("# move_to.py")[0], "job", "exec"), ns)
        self.assertEqual((ns["P_ID"], ns["P_FWD"], ns["P_STEP"]), ("CSX 2738", False, 32))
        self.assertEqual(ns["UNTIL"], ["BS Switch 33", "BS East Lead"])
        self.assertEqual(ns["GUARD"], ["BS W-1"])
        self.assertEqual(ns["FUNCS"], [0])  # no hard-coded 2121 sound mute
        src = (SM / "jython" / "move_to.py").read_text()
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
        for name in ("step_runner.py", "move_to.py"):
            j = (SM / "jython" / name).read_text()
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
        both = analyze.load_lengths(p)
        self.assertIsNotNone(both["BS Main West"])
        self.assertIsNotNone(both["BS East Lead"])
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


if __name__ == "__main__":
    unittest.main()
