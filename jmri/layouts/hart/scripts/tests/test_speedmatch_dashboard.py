"""Speed-match dashboard: log parser, run state machine, scale maths, replay, ssh poller.

No network and no ssh: the poller gets a fake fetcher."""
from __future__ import annotations

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
                 L(65, "STEPDONE 8 reason=target n=2 mm=1200 s=24 mm_s=50 relsd=0.0")])
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
        self.assertIn("Guard", g.banner[1])

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
        self.assertEqual(len(logs), 4)
        store = st.Store()
        for rid, lines in logs:
            for ln in lines:
                store.feed(rid, ln)
        for run in store.runs.values():
            self.assertEqual(run.status, "done", run.id)
            self.assertEqual(sorted(run.done), src.DEMO_STEPS)
        top = store.runs["steprun_2121_forward_demo.log"].done[126]["mm_s"]
        self.assertAlmostEqual(top, 429.8 * 1.122, delta=429.8 * 1.122 * 0.03)


class SshPollerTests(unittest.TestCase):
    def test_incremental_tail_and_partial_line(self):
        path = "/tmp/steprun_2121_forward_x.log"
        content = (L(0, "RUN loco=2121 direction=forward") + "\n" + L(1, "STEP 8") + "\n" + L(2, "SETT")).encode()
        calls = []

        def fetch(cmd):
            calls.append(cmd)
            if cmd.startswith("for f"):
                return ("@@FILE %s %d\n" % (path, len(content))).encode()
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
