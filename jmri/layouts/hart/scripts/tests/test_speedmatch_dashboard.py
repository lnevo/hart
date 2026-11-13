"""Speed-match dashboard: log parser, run state machine, scale maths, replay, ssh poller.

No network and no ssh: the poller gets a fake fetcher."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "speedmatch" / "dashboard"
sys.path.insert(0, str(DASH))
import dashsources as src  # noqa: E402
import dashstate as st  # noqa: E402

T = 1794300000.0


def L(dt, msg):
    return "%.3f %s" % (T + dt, msg)


def feed(run, lines):
    for ln in lines:
        run.feed_line(ln)
    return run


class ParserTests(unittest.TestCase):
    def test_every_contract_line(self):
        cases = {
            "RUN loco=2121 direction=reverse": ("RUN", "loco=2121 direction=reverse"),
            "CFG route=loop1 mode=distance": ("CFG", "route=loop1 mode=distance"),
            'LENGTHS {"BS A": 100}': ("LENGTHS", '{"BS A": 100}'),
            "WARMUP 64 secs=40": ("WARMUP", "64 secs=40"),
            "WARMUP_DONE": ("WARMUP_DONE", ""),
            "WARMUP_LAP 2": ("WARMUP_LAP", "2"),
            "STEP 8": ("STEP", "8"),
            "SETTLE 8 secs=6": ("SETTLE", "8 secs=6"),
            "MEASURE 8 from=BS_A": ("MEASURE", "8 from=BS_A"),
            "SENS BS A ACTIVE": ("SENS", "BS A ACTIVE"),
            "BLOCK 8 block=Track_A mm=100 dt=2 mm_s=50": ("BLOCK", "8 block=Track_A mm=100 dt=2 mm_s=50"),
            "READ 1 50.0 dt=2 mm=100 blocks=1": ("READ", "1 50.0 dt=2 mm=100 blocks=1"),
            "STEPDONE 8 reason=target n=6 mm=600 s=12 mm_s=50 relsd=0.01": ("STEPDONE", "8 reason=target n=6 mm=600 s=12 mm_s=50 relsd=0.01"),
            "PASS step=8 from=A to=B": ("PASS", "step=8 from=A to=B"),
            "PASSDONE reason=ok": ("PASSDONE", "reason=ok"),
            "STOP sensor lit": ("STOP", "sensor lit"),
            "END": ("END", ""),
            "ERROR boom": ("ERROR", "boom"),
            "ABORTED kill flag": ("ABORTED", "kill flag"),
            "NO GUARD": ("NO_GUARD", ""),
        }
        for msg, (kind, rest) in cases.items():
            p = st.parse_line("123.5 " + msg)
            self.assertEqual(p, (123.5, kind, rest), msg)

    def test_junk_lines_are_ignored(self):
        self.assertIsNone(st.parse_line(""))
        self.assertIsNone(st.parse_line("not a time here"))
        run = st.Run("x")
        self.assertFalse(run.feed_line("garbage"))
        run.feed_line(L(0, "SOMETHING_NEW a=b"))  # unknown kind tolerated
        self.assertEqual(run.lines, 1)

    def test_kv_underscores_become_spaces(self):
        self.assertEqual(st.kv(["block=Track_East_Lead", "mm=5"]), {"block": "Track East Lead", "mm": "5"})

    def test_log_kind(self):
        self.assertEqual(st.kind_of_log("/tmp/steprun_2121_forward_x.log"), "steprun")
        self.assertEqual(st.kind_of_log("/tmp/stoptest_a.log"), "stoptest")
        self.assertEqual(st.kind_of_log("/tmp/preflight_a.log"), "preflight")
        self.assertEqual(st.kind_of_log("/tmp/pass_a.log"), "pass")


class StateMachineTests(unittest.TestCase):
    def head(self):
        return [L(0, "RUN loco=2121 direction=forward"),
                L(1, "CFG route=loop1 mode=distance steps=8,12 target_mm=600 min_blocks=2 warm_s=30"),
                L(1, 'LENGTHS {"BS East Main Ext": 1000, "BS Switch 7b": 200}')]

    def test_warmup_settle_measure_stepdone(self):
        r = feed(st.Run("steprun_a.log"), self.head() + [L(2, "WARMUP 64 secs=30")])
        self.assertEqual(r.status, "warming")
        self.assertEqual(r.steps, [8, 12])
        self.assertEqual(r.route, "loop1")
        feed(r, [L(32, "WARMUP_DONE"), L(33, "STEP 8"), L(33, "SETTLE 8 secs=6")])
        self.assertEqual(r.status, "settling")
        self.assertAlmostEqual(r.to_dict(T + 35)["settle_left"], 4.0)
        feed(r, [L(39, "MEASURE 8 from=BS_East_Main_Ext"), L(40, "SENS BS East Main Ext ACTIVE")])
        self.assertEqual(r.status, "measuring")
        self.assertEqual(r.active, "BS East Main Ext")
        feed(r, [L(60, "BLOCK 8 block=BS_East_Main_Ext mm=1000 dt=20 mm_s=50"),
                 L(64, "BLOCK 8 block=BS_Switch_7b mm=200 dt=4 mm_s=50"),
                 L(65, "STEPDONE 8 reason=settled n=2 mm=1200 s=24 mm_s=50 relsd=0.0")])
        self.assertEqual(r.done[8]["mm_s"], 50)
        d = r.to_dict(T + 66)
        self.assertEqual(d["curve"], [{"step": 8, "mm_s": 50}])
        self.assertEqual(d["done_steps"], 1)
        crossed = {b["sensor"]: b["mm_s"] for b in d["blocks"] if b["mm_s"] is not None}
        self.assertEqual(crossed, {"BS East Main Ext": 50, "BS Switch 7b": 50})
        self.assertAlmostEqual(d["speed_mph"], 50 * 3.6 * 87 / 1609.34)

    def test_old_mode_read_and_median(self):
        r = feed(st.Run("o"), [L(0, "RUN loco=2738 direction=reverse"), L(1, "STEP 16"),
                               L(5, "READ 1 70.5 dt=10 mm=705 blocks=3"),
                               L(9, "STEPDONE 16 reason=k n=2 median=71.2")])
        self.assertEqual(r.reads[0]["mm_s"], 70.5)
        self.assertEqual(r.done[16]["mm_s"], 71.2)
        self.assertEqual(r.road(), "CSX 2738")

    def test_old_warmup_laps(self):
        r = feed(st.Run("o"), [L(0, "WARMUP 64 laps=2"), L(5, "WARMUP_LAP 1"), L(9, "WARMUP_LAP 2"), L(10, "WARMUP_DONE")])
        self.assertEqual(r.status, "settling")
        self.assertIsNone(r.warm)

    def test_stop_error_abort_guard_banners(self):
        r = feed(st.Run("a"), [L(0, "RUN loco=2121 direction=forward"), L(1, "STOP sensor timeout"), L(2, "END")])
        self.assertEqual(r.status, "stopped")  # END does not overwrite a stop
        self.assertEqual(r.banner[0], "stop")
        self.assertTrue(r.finished())
        e = feed(st.Run("b"), [L(0, "ERROR no throttle")])
        self.assertEqual((e.status, e.banner[0]), ("error", "error"))
        a = feed(st.Run("c"), [L(0, "ABORTED kill flag")])
        self.assertEqual(a.status, "aborted")
        g = feed(st.Run("d"), [L(0, "NO GUARD")])
        self.assertEqual(g.banner, ("notice", "No guard sensors on this run"))

    def test_end_means_done(self):
        r = feed(st.Run("a"), [L(0, "RUN loco=2121 direction=forward"), L(9, "END")])
        self.assertEqual(r.status, "done")

    def test_eta_from_mean_step_time(self):
        r = feed(st.Run("a"), self.head() + [L(2, "STEP 8"), L(12, "STEPDONE 8 reason=t n=1 mm=1 s=1 mm_s=5")])
        r.cfg["steps"] = "8,12,16"
        r.steps = [8, 12, 16]
        r.feed(T + 12, "STEP", "12")
        # one step took 10 s; step 12 just started, 16 still to go -> 10 + 10
        self.assertAlmostEqual(r.eta(T + 12), 20.0)
        self.assertIsNone(st.Run("b").eta(T))

    def test_store_picks_live_run_to_focus(self):
        s = st.Store()
        s.feed("a", L(0, "RUN loco=2121 direction=forward"))
        s.feed("a", L(5, "END"))
        s.feed("b", L(9, "RUN loco=2738 direction=forward"))
        self.assertEqual(s.snapshot(T + 10)["focus"], "b")


class ScaleTests(unittest.TestCase):
    def test_mph(self):
        self.assertAlmostEqual(st.mph_ho(100.0), 100 * 3.6 * 87 / 1609.34)
        self.assertAlmostEqual(st.mph_ho(430.0), 83.7, places=1)  # step 126 of CSX 2121
        self.assertIsNone(st.mph_ho(None))


class ReplayTests(unittest.TestCase):
    def test_merged_in_timestamp_order(self):
        a = ("a.log", [L(0, "RUN loco=1 direction=forward"), L(10, "END")])
        b = ("b.log", [L(5, "RUN loco=2 direction=forward"), L(7, "END")])
        sched = src.replay_schedule([b, a], rate=10)
        self.assertEqual([x[2] for x in sched], ["a.log", "b.log", "b.log", "a.log"])
        self.assertEqual([round(x[0], 3) for x in sched], [0, 0.5, 0.7, 1.0])

    def test_long_gaps_are_capped(self):
        a = ("a.log", [L(0, "RUN loco=1 direction=forward"), L(86400, "END")])
        sched = src.replay_schedule([a], rate=10, max_gap=100)
        self.assertEqual(sched[1][0], 10.0)

    def test_source_releases_lines_with_the_clock(self):
        now = [0.0]
        rs = src.ReplaySource([("a.log", [L(0, "RUN loco=2121 direction=forward"), L(20, "END")])],
                              rate=10, clock=lambda: now[0])
        store = st.Store()
        rs.poll(store)
        self.assertEqual(store.runs["a.log"].status, "starting")
        now[0] = 1.0
        rs.poll(store)
        self.assertEqual(store.runs["a.log"].status, "starting")
        now[0] = 2.0
        rs.poll(store)
        self.assertEqual(store.runs["a.log"].status, "done")
        self.assertTrue(rs.finished)
        self.assertEqual(rs.now, T + 20)


class DemoTests(unittest.TestCase):
    def test_demo_logs_parse_and_finish(self):
        logs = src.demo_logs()
        self.assertEqual(len(logs), 6)
        store = st.Store()
        for rid, lines in logs:
            for ln in lines:
                store.feed(rid, ln)
        self.assertEqual(src.DEMO_STEPS, [8, 16, 24, 32, 48, 64, 96, 126])
        self.assertEqual(len(store.runs), 6)  # four step runs, two passes
        for run in store.runs.values():
            self.assertEqual(run.status, "done", run.id)
            if run.kind == "steprun":
                self.assertEqual(sorted(run.done), src.DEMO_STEPS)
        top = store.runs["steprun_CSX_2121_forward_demo.log"].done[126]["mm_s"]
        self.assertAlmostEqual(top, 429.8 * 1.122, delta=429.8 * 1.122 * 0.05)

    def test_warmup_only_before_a_locos_first_run(self):
        logs = dict(src.demo_logs())
        has = {n: any(" WARMUP " in x for x in ls) for n, ls in logs.items()}
        self.assertTrue(has["steprun_CSX_2121_forward_demo.log"])
        self.assertFalse(has["steprun_CSX_2121_reverse_demo.log"])
        self.assertTrue(has["steprun_CSX_2738_forward_demo.log"])
        self.assertFalse(has["steprun_CSX_2738_reverse_demo.log"])
        self.assertIn("WARMUP 48 secs=60", [x.split(" ", 1)[1] for x in logs["steprun_CSX_2121_forward_demo.log"]])

    def test_settle_is_momentum_time_and_passes_use_loop2(self):
        logs = dict(src.demo_logs())
        ls = [x.split(" ", 1)[1] for x in logs["steprun_CSX_2121_reverse_demo.log"]]
        self.assertIn("SETTLE 8 secs=%.1f" % (0.896 * 26 * 8 / 126 + 2), ls)  # no warm-up: from step 0
        self.assertIn("SETTLE 16 secs=%.1f" % (0.896 * 26 * 8 / 126 + 2), ls)
        for n in (24, 48):
            p = [x.split(" ", 1)[1] for x in logs["pass_CSX_2121_forward_step%d_demo.log" % n]]
            self.assertIn("CFG route=loop2 mode=pass step=%d max_s=300" % n, p)
            self.assertIn("PASS step=%d from=BS Switch 5 to=BS Switch 15" % n, p)
        r = st.Run("p")
        for x in logs["pass_CSX_2121_forward_step24_demo.log"]:
            r.feed_line(x)
        rows = r.to_dict(r.t_last)["pass"]["rows"]
        self.assertEqual([x["sensor"] for x in rows], ["BS Switch 5", "BS Scale", "BS Switch 7", "BS Barn",
                                                       "BS Switch 13", "BS Switch 15", "BS S-R"])
        self.assertTrue(all(x["t_rel"] is not None for x in rows))


class RunnerContractTests(unittest.TestCase):
    def test_extra_gap_and_reasons(self):
        r = feed(st.Run("a"), [
            L(0, "RUN loco=2121 direction=forward"),
            L(1, "STEP 16"), L(2, "SETTLE 16 secs=3.0"), L(5, "MEASURE 16 from=BS Switch 35a"),
            L(9, "EXTRA 16 relsd=0.0412"),
            L(10, "STEPDONE 16 reason=settled n=4 mm=6100.0 s=40.00 mm_s=152.5 relsd=0.0200"),
            L(11, "STEP 8"), L(70, "STEPDONE 8 reason=max n=0 mm=0.0 s=0.00 mm_s=0.0 relsd=0.0000"),
            L(71, "STEP 24"), L(130, "STEPDONE 24 reason=max n=2 mm=3810.0 s=60.00 mm_s=63.5 relsd=0.0100"),
            L(131, "STEP 32"), L(140, "STEPDONE 32 reason=timed n=3 mm=4000.0 s=30.00 mm_s=133.3 relsd=0.0100"),
            L(141, "STEP 48"), L(150, "STEPDONE 48 reason=stalled n=1 mm=500.0 s=5.00 mm_s=100.0 relsd=0.0")])
        self.assertEqual(r.measure_from, "BS Switch 35a")  # spaces kept
        d = r.to_dict(T + 151)
        self.assertEqual([c["step"] for c in d["curve"]], [16, 32])  # settled and timed
        self.assertEqual({f["step"]: f["reason"] for f in d["flagged"]}, {8: "max", 24: "max", 48: "stalled"})
        self.assertIsNone(r.done[8]["mm_s"])  # a gap, not 0 mm/s
        self.assertEqual(r.speed, 100.0)  # live speed follows the latest reading
        r2 = feed(st.Run("b"), [L(0, "STEP 16"), L(5, "EXTRA 16 relsd=0.0412")])
        self.assertAlmostEqual(r2.to_dict(T + 6)["extra"], 0.0412)
        r2.feed(T + 7, "STEP", "24")
        self.assertIsNone(r2.to_dict(T + 8)["extra"])

    def test_run_complete_stop_is_not_a_stop(self):
        r = feed(st.Run("a"), [L(0, "RUN loco=2121 direction=forward"), L(1, "STOP all steps complete"), L(2, "END")])
        self.assertEqual((r.status, r.banner), ("done", None))

    def test_loco_logged_as_road_name(self):
        r = feed(st.Run("a"), [L(0, "RUN loco=CSX_2121 direction=forward")])
        self.assertEqual((r.loco, r.road()), ("2121", "CSX 2121"))

    def test_pass_job(self):
        r = feed(st.Run("pass_CSX_2121_forward_step24_x.log"), [
            L(0, "RUN loco=2121 direction=forward"),
            L(0.1, "CFG route=loop2 mode=pass step=24 max_s=300"),
            L(1, "PASS step=24 from=BS Switch 5 to=BS Switch 15"),
            L(5, "SENS BS Switch 5 ACTIVE"), L(9, "SENS BS Scale ACTIVE"), L(11, "SENS BS Switch 7 ACTIVE")])
        self.assertEqual(r.kind, "pass")
        d = r.to_dict(T + 12)
        self.assertEqual((d["pass"]["from"], d["pass"]["to"]), ("BS Switch 5", "BS Switch 15"))
        rows = {x["sensor"]: x for x in d["pass"]["rows"]}
        self.assertAlmostEqual(rows["BS Scale"]["t_rel"], 8.0)
        self.assertAlmostEqual(rows["BS Scale"]["dt"], 2.0)
        self.assertIsNone(rows["BS Barn"]["t_rel"])
        feed(r, [L(20, "PASSDONE reason=max"), L(21, "STOP max"), L(22, "END")])
        self.assertEqual(r.status, "stopped")
        self.assertIn("max", r.banner[1])
        ok = feed(st.Run("q"), [L(0, "PASS step=24 from=BS Switch 5 to=BS Switch 15"), L(9, "PASSDONE reason=passed"),
                                L(10, "STOP passed"), L(11, "END")])
        self.assertEqual((ok.status, ok.banner), ("done", None))

    def test_runner_simulation_matches_analyze(self):
        # the Jython runner of PR 422 on its virtual clock (test_speedmatch_distance's harness)
        import io
        import tempfile
        from contextlib import redirect_stdout
        import test_speedmatch_distance as td
        tmp = Path(tempfile.mkdtemp())
        csvp, out, log = tmp / "bl.csv", tmp / "job.py", tmp / "run.log"
        td.loop_csv(csvp, td.analyze.LOOP)
        with redirect_stdout(io.StringIO()):
            td.make_job.main(["steps", "--loco", "CSX 2121", "--direction", "forward", "--mode", "distance",
                              "--guard", "none", "--steps", "8,24,48", "--warm-s", "5", "--warm-step", "24",
                              "--out", str(out), "--log", str(log), "--lengths", str(csvp)])
        td.FakeLayout(td.ORDER1, td.LEN1, 2).run(out.read_text(), tmp)
        lines = log.read_text().splitlines()
        run = st.Run("steprun_CSX_2121_forward_sim.log")
        feed(run, lines)
        self.assertEqual(run.status, "done")
        self.assertEqual(run.loco, "2121")
        runs = td.analyze.parse_log(lines, source="sim")
        rows = td.analyze.summarize_runs(runs, td.LEN1)[0]["rows"]
        self.assertEqual([r["step"] for r in rows], [8, 24, 48])
        for row in rows:
            got = run.done[row["step"]]
            if row["median"] is None:
                self.assertIsNone(got["mm_s"], row)
            else:
                self.assertAlmostEqual(got["mm_s"], row["median"], places=0)
            self.assertEqual(got["valid"], row["settled"])
        self.assertIn(run.done[8]["reason"], ("timed", "max"))  # too slow for 6000 mm
        on_curve = {c["step"] for c in run.to_dict(run.t_last)["curve"]}
        self.assertEqual(on_curve, {st_ for st_, v in run.done.items() if v["reason"] in ("settled", "timed")})
        self.assertIn("FREEZE 8", [x.split(" ", 1)[1] for x in lines])


class FinalContractTests(unittest.TestCase):
    def test_freeze_ignores_late_blocks_until_stepdone(self):
        r = feed(st.Run("a"), [L(0, "RUN loco=2121 direction=forward"), L(1, "STEP 24"), L(2, "SETTLE 24 secs=3.0"),
                               L(5, "MEASURE 24 from=BS A"),
                               L(9, "BLOCK 24 block=BS_A mm=1000 dt=4 mm_s=250"), L(10, "FREEZE 24")])
        self.assertEqual(r.status, "computing")
        feed(r, [L(10.2, "SENS BS B ACTIVE"), L(10.3, "BLOCK 24 block=BS_B mm=900 dt=3.6 mm_s=250")])
        self.assertEqual(len(r.blocks), 1)  # the late block did not count
        self.assertNotEqual(r.active, "BS B")
        feed(r, [L(10.5, "STEPDONE 24 reason=settled n=1 mm=1000.0 s=4.00 mm_s=250.0 relsd=0.0")])
        self.assertEqual(r.status, "measuring")
        self.assertEqual(r.done[24]["mm_s"], 250.0)
        feed(r, [L(11, "STEP 32")])
        self.assertFalse(r.frozen)

    def test_path_drives_the_pass_rows(self):
        r = feed(st.Run("p"), [
            L(0, "RUN loco=2121 direction=forward"), L(0.1, "CFG route=loop2 mode=pass step=24 max_s=300"),
            L(0.5, "PATH BS Switch 5,BS Scale,BS Switch 7,BS Barn"),
            L(1, "PASS step=24 from=BS Switch 5 to=BS Barn"), L(3, "SENS BS Switch 5 ACTIVE")])
        rows = r.to_dict(T + 4)["pass"]["rows"]
        self.assertEqual([x["sensor"] for x in rows], ["BS Switch 5", "BS Scale", "BS Switch 7", "BS Barn", "BS Switch 13"])

    def test_wrong_way(self):
        for lines in ([L(0, "PASSDONE reason=wrong_way")], [L(0, "STOP wrong way")]):
            r = feed(st.Run("p"), [L(-1, "PASS step=24 from=BS Switch 5 to=BS Switch 15")] + lines + [L(1, "END")])
            self.assertEqual((r.status, r.banner), ("stopped", ("error", "Pass went the wrong way, loco stopped")))

    def test_demo_step_8_ends_timed_and_is_on_the_curve(self):
        store = st.Store()
        for rid, lines in src.demo_logs():
            for ln in lines:
                store.feed(rid, ln)
        r = store.runs["steprun_CSX_2121_forward_demo.log"]
        self.assertEqual(r.done[8]["reason"], "timed")
        self.assertIn(8, [c["step"] for c in r.to_dict(r.t_last)["curve"]])
        pr = store.runs["pass_CSX_2121_forward_step24_demo.log"]
        self.assertEqual(pr.pass_path[0], "BS Switch 5")
        self.assertEqual(pr.pass_path[-1], "BS Switch 15")


class ReviewFixTests(unittest.TestCase):
    def test_stop_after_error_keeps_the_error(self):
        for first, level in (("ERROR boom", "error"), ("ABORTED kill flag", "error")):
            r = feed(st.Run("a"), [L(0, "RUN loco=2121 direction=forward"), L(1, first), L(2, "STOP boom"),
                                   L(3, "PASSDONE reason=max"), L(4, "END")])
            self.assertIn(r.status, ("error", "aborted"))
            self.assertEqual(r.banner[0], level)
            self.assertTrue(r.banner[1].startswith(("Error", "Aborted")))
        r = feed(st.Run("b"), [L(0, "RUN loco=2121 direction=forward"), L(1, "STOP"), L(2, "END")])
        self.assertEqual((r.status, r.banner), ("done", None))  # an empty STOP is never "stop"
        r = feed(st.Run("c"), [L(0, "STOP sensor lit"), L(1, "STOP")])
        self.assertEqual((r.status, r.banner[1]), ("stopped", "Stopped: sensor lit"))

    def test_no_guard_is_a_notice_not_a_trip(self):
        r = feed(st.Run("a"), [L(0, "NO GUARD")])
        self.assertEqual(r.banner, ("notice", "No guard sensors on this run"))
        r = feed(st.Run("b"), [L(0, "ERROR x"), L(1, "NO GUARD")])
        self.assertEqual(r.banner[0], "error")  # a notice never hides an error

    def test_num_rejects_inf_and_nan(self):
        for bad in ("inf", "-inf", "nan", "1e999"):
            self.assertIsNone(st.num(bad))
        self.assertEqual(st.num("12.0"), 12)
        r = feed(st.Run("a"), [L(0, "STEP 8"), L(1, "STEPDONE 8 reason=settled n=2 mm=inf s=nan mm_s=inf relsd=nan")])
        self.assertIsNone(r.done[8]["mm_s"])
        self.assertEqual(r.to_dict(T + 2)["curve"], [])

    def test_a_bad_line_does_not_stop_the_feed(self):
        s = st.Store()
        orig = st.Run.feed

        def boom(self, t, kind, rest):
            if kind == "BAD":
                raise ValueError("boom")
            return orig(self, t, kind, rest)

        st.Run.feed = boom
        try:
            s.feed("a", L(0, "BAD x"))
            s.feed("a", L(1, "RUN loco=2121 direction=forward"))
        finally:
            st.Run.feed = orig
        self.assertEqual(s.bad_lines, 1)
        self.assertEqual(s.runs["a"].loco, "2121")

    def test_hub_poll_survives_any_exception(self):
        import server

        class Boom:
            mode = "live"

            def poll(self, store):
                raise RuntimeError("bad parse")

        hub = server.Hub(Boom(), 1.5)
        hub.poll_once()
        self.assertEqual((hub.ok, hub.message), (False, "dashboard parse error, retrying"))
        hub.source = src.ReplaySource([("a.log", [L(0, "RUN loco=2121 direction=forward")])], clock=lambda: 0.0)
        hub.poll_once()
        self.assertTrue(hub.ok)

    def test_live_clock_ignores_pi_mac_offset(self):
        t = [1000.0]
        old = st.clock
        st.clock = lambda: t[0]
        try:
            r = feed(st.Run("a"), [L(0, "RUN loco=2121 direction=forward"), L(1, "SETTLE 8 secs=10")])
            # the Pi's clock is years away from this Mac's: only the log time and elapsed Mac time count
            t[0] += 4.0
            self.assertAlmostEqual(r.est_now(), T + 1 + 4.0)
            self.assertAlmostEqual(r.to_dict(r.est_now())["settle_left"], 6.0)
        finally:
            st.clock = old

    def test_newest_run_wins_focus_and_stale_runs_do_not(self):
        t = [0.0]
        old = st.clock
        st.clock = lambda: t[0]
        try:
            s = st.Store()
            s.feed("old", L(0, "RUN loco=2121 direction=forward"))
            s.feed("old", L(1, "STEP 8"))
            s.feed("new", L(100, "RUN loco=2738 direction=forward"))
            self.assertEqual(s.snapshot()["focus"], "new")  # newest RUN, though "old" is unfinished too
            self.assertEqual(s.snapshot(focus="old")["focus"], "old")  # a manual choice
            t[0] += 400.0  # no new line for more than five minutes, on both
            snap = s.snapshot()
            self.assertTrue(all(r["stale"] for r in snap["runs"]))
            s.feed("old", L(500, "STEP 12"))  # the older log moves again; "new" is stale
            snap = s.snapshot()
            self.assertEqual(snap["focus"], "old")
            self.assertEqual({r["id"]: r["stale"] for r in snap["runs"]}, {"old": False, "new": True})
            only = [r for r in snap["runs"] if r["id"] == "old"][0]
            self.assertIn("events", only)  # full detail only for the focused run
            self.assertNotIn("events", [r for r in snap["runs"] if r["id"] == "new"][0])
            s.pi_clock = (T + 10000.0, t[0])  # first read of an old unfinished log: the Pi clock shows it
            s2 = st.Store()
            s2.pi_clock = s.pi_clock
            s2.feed("z", L(0, "RUN loco=2121 direction=forward"))
            self.assertTrue(s2.snapshot()["runs"][0]["stale"])
        finally:
            st.clock = old

    def test_route_default_and_pass_without_cfg(self):
        r = feed(st.Run("a"), [L(0, "RUN loco=2121 direction=forward"), L(1, "CFG route=nowhere mode=distance")])
        self.assertTrue(r.to_dict(T + 2)["blocks"])  # an unknown route falls back to the default
        self.assertEqual(r.resolved_route(), st.DEFAULT_ROUTE)
        p = feed(st.Run("pass_x.log"), [
            L(0, "RUN loco=2121 direction=forward"),
            L(1, "PATH BS Switch 5,BS Scale,BS Switch 7"), L(2, "PASS step=24 from=BS Switch 5 to=BS Switch 7"),
            L(3, "SENS BS Switch 5 ACTIVE")])
        self.assertEqual(p.resolved_route(), "loop2")  # no CFG: found from the PATH names
        rows = p.to_dict(T + 4)["pass"]["rows"]
        self.assertEqual([x["sensor"] for x in rows][:3], ["BS Switch 5", "BS Scale", "BS Switch 7"])
        q = feed(st.Run("pass_y.log"), [L(0, "PATH Nowhere A,Nowhere B"), L(1, "PASS step=8 from=Nowhere A to=Nowhere B")])
        self.assertEqual([x["sensor"] for x in q.to_dict(T + 2)["pass"]["rows"]], ["Nowhere A", "Nowhere B"])
        self.assertTrue(q.to_dict(T + 2)["blocks"] is not None)  # no KeyError

    def test_demo_pass_stops_at_the_sensor_after_to_with_wrap(self):
        names = ["A", "B", "C", "D"]
        self.assertEqual(src.pass_sequence(names, "C", "A"), ["C", "D", "A", "B"])  # wraps the ring
        self.assertEqual(src.pass_sequence(names, "B", "D"), ["B", "C", "D", "A"])
        self.assertEqual(src.pass_sequence(names, "D", "B"), ["D", "A", "B", "C"])
        logs = dict(src.demo_logs())
        last = [x for x in logs["pass_CSX_2121_forward_step24_demo.log"] if " SENS " in x][-1]
        self.assertTrue(last.endswith("SENS BS S-R ACTIVE"))

    def test_invalid_reason_follows_liverule(self):
        for reason, ok in (("settled", True), ("timed", True), ("max", False), ("stalled", False)):
            r = feed(st.Run("a"), [L(0, "STEP 8"), L(1, "STEPDONE 8 reason=%s n=2 mm=100 s=2 mm_s=50 relsd=0" % reason)])
            self.assertEqual(r.done[8]["valid"], ok, reason)
        r = feed(st.Run("o"), [L(0, "STEP 8"), L(1, "STEPDONE 8 n=2 median=71.2")])  # an older log: no reason
        self.assertTrue(r.done[8]["valid"])


class SshPollerTests(unittest.TestCase):
    def test_incremental_tail_and_partial_line(self):
        path = "/tmp/steprun_2121_forward_x.log"
        content = (L(0, "RUN loco=2121 direction=forward") + "\n" + L(1, "STEP 8") + "\n" + L(2, "SETT")).encode()
        calls = []

        def fetch(cmd):
            calls.append(cmd)
            if "@@FILE" in cmd:
                return ("@@NOW 1794300100\n@@FILE %s %d\n" % (path, len(content))).encode()
            off = int(cmd.split()[2].lstrip("+")) - 1
            return content[off:]

        poller = src.SshSource(fetch)
        store = st.Store()
        self.assertEqual(poller.poll(store), (True, None))
        run = store.runs[path]
        self.assertEqual(run.lines, 2)  # the unfinished third line waits
        self.assertEqual(run.step, 8)
        content += b"LE 8 secs=6\n"  # the rest of line three arrives
        poller.poll(store)
        self.assertEqual(run.lines, 3)
        self.assertEqual(run.status, "settling")
        n = len(calls)
        poller.poll(store)  # nothing grew: only the listing call
        self.assertEqual(len(calls), n + 1)

    def test_only_reads_never_writes(self):
        cmds = [src.list_cmd(), src.tail_cmd("/tmp/a b.log", 10)]
        for c in [x.replace("2>/dev/null", "") for x in cmds]:
            for bad in (" rm ", ">", "touch", "mv ", "tee"):
                self.assertNotIn(bad, c)
        self.assertIn("'/tmp/a b.log'", cmds[1])

    def test_unreachable_is_reported_and_recovers(self):
        up = [False]

        def fetch(cmd):
            if not up[0]:
                raise OSError("Connection refused")
            return b""

        poller = src.SshSource(fetch)
        ok, msg = poller.poll(st.Store())
        self.assertFalse(ok)
        self.assertIn("Pi not reachable, retrying", msg)
        up[0] = True
        self.assertEqual(poller.poll(st.Store()), (True, None))


if __name__ == "__main__":
    unittest.main()
