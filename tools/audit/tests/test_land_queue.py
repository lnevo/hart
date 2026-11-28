"""make land's merge queue (tools/agent/land_queue.py) and the background job (tools/agent/land.py's detach).

Every queue lives in a temp folder, never /tmp/hart-land-queue; GitHub is test_land's FakeGitHub; no job is started.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_land as T  # noqa: E402

LAND = T.LAND
import land_queue as Q  # noqa: E402  (land.py put tools/agent on the path)

GONE = 999_999_999      # a PID no process has
JOB_PID = 424_242       # the stub job's PID


def queue(root: Path, sleep: Any = None, alive: Any = None, said: list[str] | None = None) -> Any:
    return Q.LandQueue(root, (said if said is not None else []).append, sleep=sleep or (lambda s: None),
                       alive=alive or Q.pid_alive)


class Tickets(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(dir=T.LOCKS.name)) / "queue"

    def test_tickets_are_numbered_in_order_and_hold_who_took_them(self) -> None:
        q = queue(self.root)
        one, two = q.take(11, "hart-a"), q.take(12, "hart-b")
        self.assertEqual((1, 2), (one.number, two.number))
        self.assertEqual({"pid": os.getpid(), "pr": 12, "session": "hart-b", "state": "queued", "head_since": None},
                         {k: v for k, v in json.loads(two.path.read_text()).items() if k not in ("since", "token")})
        self.assertNotEqual(one.token, two.token)
        q.release(one)
        self.assertEqual(3, q.take(13, "hart-c").number, "a number is never reused while a later ticket stands")

    def test_a_number_is_never_reused_after_the_highest_ticket_is_cleared(self) -> None:
        q = queue(self.root, alive=lambda pid: False)
        hung = q.take(11, "hart-hung")
        q.clear(hung, "its PID is gone")
        fresh = q.take(12, "hart-new")
        self.assertEqual(2, fresh.number)
        # the cleared land, still running, can neither write nor remove the new ticket, nor make its own again
        with self.assertRaises(Q.NotOurs):
            q.update(hung, state="merging")
        q.release(hung)
        self.assertFalse(hung.path.exists())
        self.assertEqual("queued", json.loads(fresh.path.read_text())["state"])

    def test_update_and_release_act_only_on_a_file_with_the_lands_token(self) -> None:
        q = queue(self.root)
        mine = q.take(11, "hart-a")
        other = Q.Ticket.read(mine.path)
        assert other is not None
        stranger = Q.Ticket(**{**other.__dict__, "token": "someone-else"})
        with self.assertRaises(Q.NotOurs):
            q.update(stranger, state="head")
        q.release(stranger)
        self.assertTrue(mine.path.exists())
        q.release(mine)
        with self.assertRaises(Q.NotOurs):
            q.update(mine, state="head")
        self.assertFalse(mine.path.exists(), "a missing ticket is never made again")

    def test_a_live_ticket_past_the_ceiling_since_it_was_taken_is_cleared(self) -> None:
        said: list[str] = []
        base = queue(self.root)
        old = base.take(11, "hart-old")
        old = Q.Ticket(**{**old.__dict__, "since": 1.0})
        base.update(old)
        q = queue(self.root, sleep=lambda s: self.fail("waited"), said=said)
        q.wait_turn(q.take(12, "hart-b"))
        self.assertFalse(old.path.exists())
        self.assertIn(f"been in the queue for over {Q.LOCK_CEILING // 60} min", said[0])

    def test_concurrent_takers_never_share_a_number(self) -> None:
        got: list[int] = []
        threads = [threading.Thread(target=lambda i=i: got.append(queue(self.root).take(i, "t").number))
                   for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(list(range(1, 21)), sorted(got))
        self.assertEqual(["numbers"], [p.name for p in self.root.iterdir() if not p.name.endswith(Q.SUFFIX)])

    def test_the_lowest_live_ticket_goes_first_and_the_next_waits_with_no_time_limit(self) -> None:
        said: list[str] = []
        slept: list[float] = []
        first = queue(self.root).take(11, "hart-a")

        def sleep(seconds: float) -> None:      # hours past any old limit, then the head ends
            slept.append(seconds)
            if sum(slept) >= 5 * 3600:
                first.path.unlink()

        q = queue(self.root, sleep=sleep, said=said)
        mine = q.take(12, "hart-b")
        head, waited = q.wait_turn(mine)
        self.assertTrue(waited)
        self.assertGreaterEqual(sum(slept), 5 * 3600)
        self.assertEqual("head", head.state)
        self.assertIsNotNone(head.head_since)
        self.assertIn("waiting in the merge queue: place 2, ticket 2; the head is ticket 1 (PR #11, hart-a", said[0])
        self.assertEqual(5 * 3600 // Q.LOCK_SAY, len(said), "one line a minute, not one a poll")

    def test_a_ticket_whose_pid_is_gone_is_skipped_with_a_line(self) -> None:
        said: list[str] = []
        dead = queue(self.root).take(11, "hart-gone", pid=GONE)
        q = queue(self.root, sleep=lambda s: self.fail("waited behind a dead ticket"), said=said)
        _, waited = q.wait_turn(q.take(12, "hart-b"))
        self.assertFalse(waited)
        self.assertFalse(dead.path.exists())
        self.assertIn("skipped ticket 1 (PR #11, hart-gone", said[0])
        self.assertIn("its PID is gone; cleared it", said[0])

    def test_a_ticket_that_changed_since_it_was_judged_is_left_alone(self) -> None:
        q = queue(self.root, alive=lambda pid: False)
        judged = q.take(11, "hart-a")
        q.update(judged, state="merging")
        q.clear(judged, "its PID is gone")
        self.assertTrue(judged.path.exists())

    def test_a_live_head_past_the_ceiling_is_cleared(self) -> None:
        said: list[str] = []
        base = queue(self.root)
        hung = base.update(base.take(11, "hart-hung"), state="head", head_since=1.0)
        q = queue(self.root, sleep=lambda s: self.fail("waited"), said=said)
        q.wait_turn(q.take(12, "hart-b"))
        self.assertFalse(hung.path.exists())
        self.assertIn(f"has been the head for over {Q.LOCK_CEILING // 60} min", said[0])

    def test_a_ticket_that_is_not_json_is_dead(self) -> None:
        self.root.mkdir(parents=True)
        (self.root / f"000001{Q.SUFFIX}").write_text("half", encoding="utf-8")
        q = queue(self.root, sleep=lambda s: self.fail("waited"))
        _, waited = q.wait_turn(q.take(12, "hart-b"))
        self.assertFalse(waited)

    def test_status_lists_tickets_states_and_log_tails(self) -> None:
        logs = self.root.parent / "logs"
        logs.mkdir()
        (logs / "12.log").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
        q = queue(self.root)
        q.take(11, "hart-gone", pid=GONE)
        q.update(q.take(12, "hart-b"), state="merging")
        lock = self.root.parent / "land.lock"
        lock.mkdir()
        (lock / "owner").write_text("4242 1 9 hart-old\n", encoding="utf-8")
        lines = Q.status(q, logs, lock)
        self.assertEqual(f"merge queue {self.root}: 2 ticket(s)", lines[0])
        self.assertTrue(lines[1].startswith(f"  ticket 1: PR #11, hart-gone, queued, PID {GONE} gone"), lines[1])
        self.assertTrue(lines[2].startswith(f"  ticket 2: PR #12, hart-b, merging, PID {os.getpid()} alive"),
                        lines[2])
        self.assertEqual(["    two", "    three", "    four"], lines[3:6])
        self.assertEqual(f"old merge lock {lock}: held by hart-old for PR #9 (PID 4242)", lines[6])
        self.assertEqual([f"merge queue {self.root / 'none'}: empty"], Q.status(queue(self.root / "none"), logs,
                                                                                 lock / "none"))


@mock.patch.dict(os.environ, {"HART_CI_REPO": T.SLUG, "HART_SESSION_NAME": "hart-test"})
class Landing(unittest.TestCase):
    """The land steps under the queue: the check is waited for behind others; the merge only at the head."""

    def setUp(self) -> None:
        self.lock = Path(tempfile.mkdtemp(dir=T.LOCKS.name)) / "land.lock"
        self.root = self.lock.parent / "queue"

    def test_a_land_waits_for_its_check_behind_the_head_then_merges(self) -> None:
        ahead = queue(self.root).take(11, "hart-other")
        gh = T.FakeGitHub()
        seen: list[bool] = []

        def sleep(_seconds: float) -> None:     # the head ends after this land's check passed
            seen.append(any("/check-runs?" in " ".join(c) for c in gh.calls))
            ahead.path.unlink(missing_ok=True)

        lnd, _ = T.lander(gh, lock=self.lock, lock_sleep=sleep, queue=self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            code = lnd.land(12, watch_main=False)
        self.assertEqual(0, code, lnd.out)
        self.assertEqual([True], seen, "the check was not waited for while behind the head")
        self.assertIn("waiting in the merge queue: place 2", "\n".join(lnd.out))
        main_checks = [c for c in gh.calls if c == ["api", f"repos/{T.SLUG}/commits/main"]]
        self.assertEqual(2, len(main_checks), "main is checked again at the head after a wait")
        self.assertEqual([], list(self.root.glob(f"*{Q.SUFFIX}")), "the ticket is released")

    def test_the_old_lock_held_by_an_older_land_is_waited_for_at_the_head(self) -> None:
        old = Q.MergeLock(self.lock, 11, lambda line: None, holder="hart-old-code")
        self.assertTrue(old.claim())
        gh = T.FakeGitHub()
        states: list[str] = []

        def sleep(_seconds: float) -> None:     # the older land still holds the lock: no merge yet
            self.assertFalse(any(c[:2] == ["pr", "merge"] for c in gh.calls))
            states.extend(t.state for t in queue(self.root).tickets())
            old.release()

        lnd, _ = T.lander(gh, lock=self.lock, lock_sleep=sleep, queue=self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, lnd.land(12, watch_main=False))
        self.assertEqual(["head"], states)
        self.assertIn("hart-old-code holds it for PR #11", "\n".join(lnd.out))

    def test_a_refusal_releases_the_ticket(self) -> None:
        gh = T.FakeGitHub(check_runs=[[T.check_run("completed", "failure")]])
        lnd, _ = T.lander(gh, lock=self.lock, queue=self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, lnd.land(12))
        self.assertEqual([], list(self.root.glob(f"*{Q.SUFFIX}")))

    def test_a_missing_ticket_stops(self) -> None:
        lnd, _ = T.lander(T.FakeGitHub(), lock=self.lock, queue=self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, lnd.land(12, ticket=self.root / f"000009{Q.SUFFIX}"))
        self.assertIn("is not in the merge queue", lnd.out[0])


@mock.patch.dict(os.environ, {"HART_SESSION_NAME": "hart-test"})
class Detached(unittest.TestCase):
    def setUp(self) -> None:
        base = Path(tempfile.mkdtemp(dir=T.LOCKS.name))
        self.root, self.logs = base / "queue", base / "logs"

    def args(self, *extra: str) -> argparse.Namespace:
        return LAND.parser().parse_args(["12", *extra])

    def adopting(self, started: list[Any], then_release: bool = False) -> Any:
        """A spawn stub whose job (PID JOB_PID) puts its own PID on the ticket, as land.py --ticket does first."""
        def spawn(cmd: list[str], **kw: Any) -> Any:
            started.append((cmd, kw))
            path = Path(cmd[cmd.index("--ticket") + 1])
            q = queue(self.root)
            held = Q.Ticket.read(path)
            assert held is not None
            held = q.update(held, pid=JOB_PID, state="started")
            if then_release:            # the job refused at once and gave its ticket back
                q.release(held)
            return mock.Mock(pid=JOB_PID)
        return spawn

    def test_make_land_takes_a_ticket_starts_the_job_and_returns(self) -> None:
        started: list[Any] = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = LAND.detach(self.args("--squash", "--wave", "w3", "--dash-out", "/d"), self.root, self.logs,
                               self.adopting(started))
        self.assertEqual(0, code)
        cmd, kw = started[0]
        ticket = self.root / f"000001{Q.SUFFIX}"
        self.assertEqual(["12", "--watch", "--ticket", str(ticket), "--poll", str(LAND.POLL), "--squash",
                          "--wave", "w3", "--dash-out", "/d"], cmd[2:])
        self.assertTrue(kw["start_new_session"])
        held = Q.Ticket.read(ticket)
        assert held is not None
        self.assertEqual((JOB_PID, 12, "hart-test", "started"), (held.pid, held.pr, held.session, held.state),
                         "the parent wrote its own PID back over the job's")
        self.assertIn("make land PR=12: ticket 1", (self.logs / "12.log").read_text())
        self.assertIn("Exit 0 means queued, not merged", buf.getvalue())
        self.assertIn("make land-wait PR=12", buf.getvalue())

    def test_a_job_that_ends_before_the_parent_returns_leaves_no_ghost_ticket(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            LAND.detach(self.args(), self.root, self.logs, self.adopting([], then_release=True))
        self.assertEqual([], list(self.root.glob(f"*{Q.SUFFIX}")))

    def test_a_stale_result_is_removed_before_the_job_starts(self) -> None:
        Q.write_result(12, 99, 4, self.logs)
        with contextlib.redirect_stdout(io.StringIO()):
            LAND.detach(self.args(), self.root, self.logs, self.adopting([]))
        self.assertIsNone(Q.read_result(12, self.logs))

    def test_a_pr_with_a_live_ticket_is_not_queued_again(self) -> None:
        first = queue(self.root).take(12, "hart-other")
        started: list[Any] = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(0, LAND.detach(self.args(), self.root, self.logs, self.adopting(started)))
        self.assertEqual([], started)
        self.assertIn(f"#12 is already in the merge queue as ticket {first.number} (PR #12, hart-other", buf.getvalue())
        self.assertIn(str(self.logs / "12.log"), buf.getvalue())
        self.assertEqual([first.path], list(self.root.glob(f"*{Q.SUFFIX}")))

    @mock.patch.dict(os.environ, {"HART_CI_REPO": T.SLUG})
    def test_a_watched_land_for_a_queued_pr_is_refused_too(self) -> None:
        queue(self.root).take(12, "hart-other")
        gh = T.FakeGitHub()
        lnd = LAND.Lander(gh=gh, queue_dir=self.root, lock_path=self.root.parent / "land.lock")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, lnd.land(12))
        self.assertIn("already in the merge queue", lnd.out[0])
        self.assertEqual([], gh.calls)

    def test_a_job_that_cannot_start_gives_its_ticket_back(self) -> None:
        def spawn(cmd: list[str], **kw: Any) -> Any:
            raise OSError("no python")

        with self.assertRaisesRegex(OSError, "no python"):
            LAND.detach(self.args(), self.root, self.logs, spawn)
        self.assertEqual([], list(self.root.glob(f"*{Q.SUFFIX}")))

    def test_main_detaches_unless_watch_and_a_watched_run_writes_its_result(self) -> None:
        with mock.patch.object(LAND, "detach", return_value=0) as detach, \
                mock.patch.object(LAND.Lander, "land", return_value=4) as land, \
                mock.patch.object(LAND, "write_result") as result, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, LAND.main(["12"]))
            detach.assert_called_once()
            land.assert_not_called()
            result.assert_not_called()
            ticket = str(self.root / "000003.ticket")
            self.assertEqual(4, LAND.main(["12", "--watch", "--ticket", ticket]))
            detach.assert_called_once()
            self.assertEqual(Path(ticket), land.call_args.kwargs["ticket"])
            self.assertEqual((12, 4), (result.call_args.args[0], result.call_args.args[2]))
            LAND.main(["12", "--watch"])
            self.assertIsNone(land.call_args.kwargs["ticket"])


class Waiting(unittest.TestCase):
    """make land-wait: the job's exit code, once its ticket is gone."""

    def setUp(self) -> None:
        base = Path(tempfile.mkdtemp(dir=T.LOCKS.name))
        self.root, self.logs = base / "queue", base / "logs"

    def test_it_waits_for_the_ticket_then_exits_with_the_jobs_code(self) -> None:
        mine = queue(self.root).take(12, "hart-a")
        slept: list[float] = []

        def sleep(seconds: float) -> None:      # the job ends: result first, then the ticket goes
            slept.append(seconds)
            Q.write_result(12, mine.number, 4, self.logs)
            mine.path.unlink()

        said: list[str] = []
        self.assertEqual(4, Q.wait(queue(self.root, sleep=sleep, said=said), 12, self.logs))
        self.assertEqual(1, len(slept))
        self.assertIn("ended with exit 4", said[-1])

    def test_a_finished_land_answers_at_once(self) -> None:
        Q.write_result(12, 3, 0, self.logs)
        self.assertEqual(0, Q.wait(queue(self.root, sleep=lambda s: self.fail("waited")), 12, self.logs))

    def test_no_job_and_no_result_or_another_tickets_result_is_2(self) -> None:
        said: list[str] = []
        self.assertEqual(2, Q.wait(queue(self.root, said=said), 12, self.logs))
        self.assertIn("no result for a land of #12", said[0])
        mine = queue(self.root).take(12, "hart-a")

        def sleep(_seconds: float) -> None:
            Q.write_result(12, mine.number + 5, 0, self.logs)
            mine.path.unlink()

        self.assertEqual(2, Q.wait(queue(self.root, sleep=sleep), 12, self.logs))


if __name__ == "__main__":
    unittest.main()
