"""tools/ops/orient.py: claims under a project page's Status line, worktrees in progress, the parts that need the
network, and the session-start hook's short form.

Temporary repos stand in for hart; gh, the hosts and the operating flag are replaced, so nothing here touches the
network or the real worktrees.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(ROOT / "tools/ops"))   # orient.py imports orient_pages from its own folder, as when it runs
OR = load(ROOT / "tools/ops/orient.py", "hart_orient_test")
import orient_pages as PAGES  # noqa: E402
WT = load(ROOT / "tools/agent/worktrees.py", "hart_worktrees_for_orient_test")
HOOK = load(ROOT / ".claude/hooks/worktree_sweep.py", "hart_sweep_hook_for_orient_test")


def sh(*args: str, cwd) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def page(body: str) -> str:
    return textwrap.dedent(body).lstrip("\n")


CLAIM = "Claimed: agent/claude/x, /r/wt/x, since 2026-11-25 08:00"


class ParsePageTest(unittest.TestCase):
    def problems(self, text: str) -> list[str]:
        return [msg for _, msg in OR.parse_page("p.md", page(text)).problems]

    def test_claims_directly_under_the_status_line(self):
        got = OR.parse_page("p.md", page(f"""
            # Title

            Status: active
            {CLAIM}
            Claimed: agent/claude/y, /r/wt/y, since 2026-11-25 09:30

            Text.
            """))
        self.assertEqual(got.status, "active")
        self.assertEqual([(c.branch, c.path, c.since, c.line) for c in got.claims],
                         [("agent/claude/x", "/r/wt/x", "2026-11-25 08:00", 4),
                          ("agent/claude/y", "/r/wt/y", "2026-11-25 09:30", 5)])
        self.assertEqual(got.problems, [])

    def test_a_blank_line_between_makes_it_misplaced(self):
        self.assertEqual(self.problems(f"""
            Status: active

            {CLAIM}
            """), ["Claimed line not directly under the Status line"])

    def test_a_claim_later_in_the_page_is_misplaced(self):
        got = OR.parse_page("p.md", page(f"""
            Status: active
            {CLAIM}

            ## Steps

            {CLAIM.replace('/x,', '/z,')}
            """))
        self.assertEqual(len(got.claims), 1)
        self.assertEqual(got.problems, [(6, "Claimed line not directly under the Status line")])

    def test_near_misses_are_reported_not_skipped(self):
        for line in ("**Claimed:** agent/claude/x, /r/wt/x, since 2026-11-25 08:00",
                     "**Claimed**: agent/claude/x, /r/wt/x, since 2026-11-25 08:00",
                     "- Claimed: agent/claude/x, /r/wt/x, since 2026-11-25 08:00",
                     "> Claimed: agent/claude/x, /r/wt/x, since 2026-11-25 08:00",
                     "Claimed: agent/claude/x /r/wt/x since 2026-11-25 08:00",
                     "Claimed: agent/claude/x, /r/wt/x, since 2026-11-25"):
            with self.subTest(line=line):
                got = self.problems(f"Status: active\n{line}\n")
                self.assertEqual(len(got), 1)
                self.assertIn("malformed Claimed line", got[0])

    def test_a_wrapped_claim_is_malformed(self):
        got = OR.parse_page("p.md", "Status: active\nClaimed: agent/claude/x, /r/wt/x, since\n2026-11-25 08:00\n")
        self.assertEqual(got.claims, [])
        self.assertEqual(len(got.problems), 1)

    def test_bad_fields(self):
        self.assertIn("not absolute", self.problems("Status: active\nClaimed: agent/claude/x, ./wt/x, since 2026-11-25 08:00\n")[0])
        self.assertIn("not absolute", self.problems("Status: active\nClaimed: agent/claude/x, ../wt/x, since 2026-11-25 08:00\n")[0])
        self.assertIn("not a real date", self.problems("Status: active\nClaimed: agent/claude/x, /r/x, since 2026-13-01 08:00\n")[0])
        self.assertIn("invalid branch", self.problems("Status: active\nClaimed: agent/../x, /r/x, since 2026-11-25 08:00\n")[0])

    def test_fences_and_comments_are_not_read(self):
        got = OR.parse_page("p.md", page(f"""
            ```
            Status: done
            {CLAIM}
            ```
            Status: active
            <!-- {CLAIM} -->
            <!--
            {CLAIM}
            -->
            ~~~~
            {CLAIM}
            ```
            still fenced: {CLAIM}
            ~~~~
            """))
        self.assertEqual((got.status, got.claims, got.problems), ("active", [], []))

    def test_a_comment_marker_in_inline_code_opens_no_comment(self):
        got = OR.parse_page("p.md", "Wrap it in `<!--` and ``a ` <!-- b``; an open ` tick.\nStatus: active\n"
                                    f"{CLAIM}\n")
        self.assertEqual((got.status, len(got.claims), got.problems), ("active", 1, []))
        self.assertEqual(PAGES.comment_start("`x` <!-- y"), 4)
        self.assertEqual(PAGES.comment_start("` <!-- y"), 2)  # an unclosed backtick is literal

    def test_a_claim_on_a_page_that_is_not_active(self):
        self.assertEqual(self.problems(f"Status: done (2026-11-24)\n{CLAIM}\n"),
                         ["claimed, but the page's Status is done, not active"])
        self.assertEqual(self.problems(f"# T\n{CLAIM}\n"), ["Claimed line not directly under the Status line"])

    def test_bold_status_bullets_are_not_the_status_line(self):
        got = OR.parse_page("p.md", "# T\n\n- **Status:** Active\n\nStatus: parked\n")
        self.assertEqual(got.status, "parked")


class CoordinatorLineTest(unittest.TestCase):
    """The merge queue's holder: a Coordinator line in the run directly under an active Status line."""

    def test_a_coordinator_under_an_active_status_with_a_claim(self):
        got = OR.parse_page("p.md", page(f"""
            Status: active
            Coordinator: hart-4e, since 2026-11-27 22:20
            {CLAIM}
            """))
        self.assertEqual([PAGES.Coordinator("p.md", 2, "hart-4e", "2026-11-27 22:20")], got.coordinators)
        self.assertEqual(1, len(got.claims))
        self.assertEqual(([], []), (got.problems, got.queue_problems))

    def test_each_line_that_holds_no_queue_is_a_warning(self):
        for text, words in (
            ("Status: done (2026-11-27)\nCoordinator: hart-6d, since 2026-11-27 18:13\n",
             "Coordinator hart-6d on a page whose Status is done, not active"),
            ("Status: active\nCoordinator: hart-4e\n", "malformed Coordinator line"),
            ("Status: active\n\nCoordinator: hart-4e, since 2026-11-27 22:20\n", "not directly under the Status"),
            ("Status: active\nCoordinator: hart-4e, since 2026-13-40 22:20\n", "not a real date and time"),
        ):
            with self.subTest(text):
                got = OR.parse_page("p.md", text)
                self.assertEqual([], got.coordinators)
                self.assertEqual(1, len(got.queue_problems), got.queue_problems)
                self.assertIn(words, got.queue_problems[0][1])
                self.assertEqual([], got.problems)


class Repo(unittest.TestCase):
    """A repo with origin/main and a projects page, plus worktrees; orient's ROOT points at it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.main = self.base / "main"
        self.main.mkdir()
        sh("git", "init", "-q", "-b", "main", cwd=self.main)
        sh("git", "config", "user.email", "t@example.com", cwd=self.main)
        sh("git", "config", "user.name", "t", cwd=self.main)
        (self.main / "wiki/projects").mkdir(parents=True)
        (self.main / "wiki/projects/work.md").write_text("# Work\n\nStatus: active\n\nBody.\n")
        (self.main / "wiki/projects/old.md").write_text("# Old\n\nStatus: done (2026-11-01)\n")
        sh("git", "add", ".", cwd=self.main)
        sh("git", "commit", "-q", "-m", "init", cwd=self.main)
        sh("git", "update-ref", "refs/remotes/origin/main", "HEAD", cwd=self.main)
        for patch in (mock.patch.object(OR, "ROOT", self.main), mock.patch.object(OR, "ROOT_MAIN", self.main),
                      mock.patch.object(OR, "load_worktrees_module", return_value=WT)):
            patch.start()
            self.addCleanup(patch.stop)

    def worktree(self, name: str, commits: int = 0) -> Path:
        path = self.base / name
        sh("git", "worktree", "add", "-q", "-b", f"agent/claude/{name}", str(path), "origin/main", cwd=self.main)
        for i in range(commits):
            (path / f"f{i}").write_text("x")
            sh("git", "add", f"f{i}", cwd=path)
            sh("git", "commit", "-q", "-m", f"c{i}", cwd=path)
        return path


class ClaimTest(Repo):
    def test_claim_then_unclaim(self):
        wt = self.worktree("t1")
        page_path = OR.resolve_page("work", wt, str(wt))
        when = datetime(2026, 11, 25, 8, 5)
        msg = OR.claim(page_path, OR.current_branch(wt), wt, when)
        self.assertIn("claimed work.md", msg)
        text = page_path.read_text()
        self.assertEqual(text.splitlines()[3], f"Claimed: agent/claude/t1, {wt}, since 2026-11-25 08:05")
        self.assertIn("already claimed", OR.claim(page_path, "agent/claude/t1", wt, when))
        self.assertEqual(page_path.read_text(), text)
        OR.claim(page_path, "agent/claude/other", Path("/r/other"), when)
        self.assertEqual(len(OR.parse_page("work.md", page_path.read_text()).claims), 2)
        self.assertIn("unclaimed work.md", OR.unclaim(page_path, "agent/claude/t1"))
        claims = OR.parse_page("work.md", page_path.read_text()).claims
        self.assertEqual([c.branch for c in claims], ["agent/claude/other"])
        with self.assertRaisesRegex(OR.OrientError, "no claim by agent/claude/t1"):
            OR.unclaim(page_path, "agent/claude/t1")

    def test_claim_refuses_what_it_cannot_write(self):
        wt = self.worktree("t2")
        with self.assertRaisesRegex(OR.OrientError, "not active"):
            OR.claim(OR.resolve_page("old.md", wt, str(wt)), "agent/claude/t2", wt, datetime.now())
        broken = wt / "wiki/projects/broken.md"
        broken.write_text("Status: active\n**Claimed:** x\n")
        with self.assertRaisesRegex(OR.OrientError, "fix it first"):
            OR.claim(broken, "agent/claude/t2", wt, datetime.now())
        bare = wt / "wiki/projects/bare.md"
        bare.write_text("# No status\n")
        with self.assertRaisesRegex(OR.OrientError, "no Status line"):
            OR.claim(bare, "agent/claude/t2", wt, datetime.now())
        with self.assertRaisesRegex(OR.OrientError, "comma"):
            OR.claim(OR.resolve_page("work", wt, str(wt)), "agent/claude/t2", Path("/r/a,b"), datetime.now())

    def test_pages_resolve_inside_this_worktrees_projects_only(self):
        wt = self.worktree("t3")
        folder = wt / "wiki/projects"
        self.assertEqual(OR.resolve_page("work", wt, "/"), folder / "work.md")
        self.assertEqual(OR.resolve_page("work.md", wt, "/"), folder / "work.md")
        self.assertEqual(OR.resolve_page("./projects/../projects/work.md", wt, str(wt / "wiki")), folder / "work.md")
        self.assertEqual(OR.resolve_page("wiki/projects/work.md", wt, str(wt)), folder / "work.md")
        for bad, cwd in (("../work.md", folder), ("wiki/home.md", wt), (str(self.main / "wiki/projects/work.md"), wt),
                         ("", wt)):
            with self.subTest(bad=bad), self.assertRaises(OR.OrientError):
                OR.resolve_page(bad, wt, str(cwd))
        with self.assertRaisesRegex(OR.OrientError, "does not exist"):
            OR.resolve_page("nope", wt, str(wt))

    def test_branch_checks(self):
        with self.assertRaisesRegex(OR.OrientError, "not main"):
            OR.current_branch(self.main)
        wt = self.worktree("t4")
        sh("git", "checkout", "-q", "--detach", cwd=wt)
        with self.assertRaisesRegex(OR.OrientError, "detached HEAD"):
            OR.current_branch(wt)

    def test_main_reports_domain_errors_without_a_traceback(self):
        wt = self.worktree("t5")
        err = mock.patch("sys.stderr", new_callable=lambda: __import__("io").StringIO())
        with err as stderr, mock.patch("os.getcwd", return_value=str(wt)):
            self.assertEqual(OR.main(["claim", "old"]), 2)
        self.assertIn("orient: ", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


class ReportTest(Repo):
    def test_short_report_shows_claims_and_work_in_progress(self):
        busy = self.worktree("busy", commits=2)
        self.worktree("idle")
        page_path = busy / "wiki/projects/work.md"
        OR.claim(page_path, "agent/claude/busy", busy, datetime(2026, 11, 25, 8, 0))
        (self.main / "wiki/projects/work.md").write_text(
            "Status: active\nClaimed: agent/claude/gone, /nowhere/gone, since 2026-11-24 10:00\n"
            f"Claimed: agent/claude/wrong, {busy}, since 2026-11-24 11:00\n")
        out = "\n".join(OR.report(short=True, here=str(busy)))
        self.assertIn("Claims (3):", out)
        self.assertIn(f"work.md: agent/claude/busy, {busy}, since 2026-11-25 08:00 [worktree present]", out)
        self.assertIn("agent/claude/gone, /nowhere/gone, since 2026-11-24 10:00 [STALE: no worktree", out)
        self.assertIn("[STALE: that worktree is on agent/claude/busy; remove the line in the main checkout]", out)
        self.assertIn("Worktrees in progress (1;", out)
        self.assertIn("agent/claude/busy, 2 ahead", out)
        self.assertIn(f"{busy} (this session)", out)
        self.assertNotIn("agent/claude/idle", out)
        self.assertNotIn("Open PRs", out)
        self.assertNotIn("Waiting to ingest", out)  # the session-start hook: no network, no ingest lines

    def test_the_queue_holder_and_nobody_named(self):
        out = OR.report(short=True, here=str(self.main))
        self.assertIn(OR.QUEUE_NOBODY, out)
        (self.main / "wiki/projects/work.md").write_text(
            "Status: active\nCoordinator: hart-4e, since 2026-11-27 22:20\n")
        (self.main / "wiki/projects/old.md").write_text(
            "Status: done (2026-11-01)\nCoordinator: hart-6d, since 2026-11-27 18:13\n")
        out = OR.report(short=True, here=str(self.main))
        self.assertIn("Queue: hart-4e, since 2026-11-27 22:20 (wiki/projects/work.md)", out)
        warning = [line for line in out if line.startswith("  warning: wiki/projects/old.md:2")]
        self.assertEqual(1, len(warning), out)
        self.assertIn("hart-6d on a page whose Status is done", warning[0])

    def test_stale_copies_in_idle_or_outside_worktrees_give_no_queue_warning(self):
        bad = "Status: done (2026-11-01)\nCoordinator: hart-6d, since 2026-11-27 18:13\n"
        old_page = self.main / "wiki/projects/old.md"
        good = old_page.read_text()
        old_page.write_text(bad)  # main once carried the bad line; a worktree cut then keeps that copy
        sh("git", "commit", "-q", "-am", "bad line", cwd=self.main)
        sh("git", "update-ref", "refs/remotes/origin/main", "HEAD", cwd=self.main)
        home = self.main / ".claude/worktrees"
        self.add_at(home / "old", "agent/claude/old")
        old_page.write_text(good)
        sh("git", "commit", "-q", "-am", "fixed", cwd=self.main)
        sh("git", "update-ref", "refs/remotes/origin/main", "HEAD", cwd=self.main)
        outside = self.worktree("scratch")
        (outside / "wiki/projects/old.md").write_text(bad)  # another session's scratchpad copy, uncommitted

        def warnings() -> list[str]:
            return [line for line in OR.report(short=True, here="/") if line.startswith("  warning:")]
        self.assertEqual(warnings(), [], "an idle worktree on origin/main and one outside home are not read")
        (home / "old/wiki/projects/old.md").write_text(bad + "\n")
        self.assertEqual(len(warnings()), 1, "an uncommitted change under wiki/projects/ makes the copy live")
        (home / "old/wiki/projects/old.md").write_text(bad)
        with mock.patch.object(OR, "lock_state", side_effect=lambda wt, t: "session running"
                               if t.path == str(outside) else ""):
            self.assertIn(f"in {outside}:", "\n".join(warnings()), "a running session's worktree counts wherever it is")

    def add_at(self, path: Path, branch: str) -> None:
        sh("git", "worktree", "add", "-q", "-b", branch, str(path), "origin/main", cwd=self.main)

    def test_the_same_claim_in_many_worktrees_is_listed_once(self):
        first = self.worktree("a1", commits=1)
        OR.claim(first / "wiki/projects/work.md", "agent/claude/a1", first, datetime(2026, 11, 25, 8, 0))
        sh("git", "commit", "-q", "-am", "claim", cwd=first)
        sh("git", "update-ref", "refs/remotes/origin/main", "agent/claude/a1", cwd=self.main)
        self.worktree("a2")  # carries the same claim, from origin/main
        claims, problems = OR.read_claims(OR.read_trees(WT), WT)
        self.assertEqual(len(claims), 1)
        self.assertEqual(problems, [])

    def test_a_live_lock_counts_as_in_progress(self):
        wt = self.worktree("locked")
        sh("git", "worktree", "lock", "--reason", f"claude agent x (pid {os.getpid()} start Mon Jan  1 00:00:00 2001)",
           str(wt), cwd=self.main)
        with mock.patch.object(WT, "lock_session_gone", return_value=False):
            busy = OR.in_progress(OR.read_trees(WT))
        self.assertEqual([(t.branch, t.lock) for t in busy], [("agent/claude/locked", "session running")])
        with mock.patch.object(WT, "lock_session_gone", return_value=True):
            self.assertEqual(OR.in_progress(OR.read_trees(WT)), [])

    def test_a_missing_worktree_folder_is_a_problem(self):
        wt = self.worktree("vanished")
        os.rename(wt, self.base / "elsewhere")
        _, problems = OR.read_claims(OR.read_trees(WT), WT)
        self.assertTrue(any("missing on disk" in p for p in problems), problems)

    def test_a_worktree_the_sweep_removes_while_orient_reads_is_no_problem(self):
        wt = self.worktree("swept")
        trees = OR.read_trees(WT)
        sh("git", "worktree", "remove", "--force", str(wt), cwd=self.main)
        _, problems = OR.read_claims(trees, WT)
        self.assertEqual(problems, [])

    def test_a_worktree_with_no_commit_yet_does_not_stop_orient(self):
        real = WT.worktrees
        unborn = WT.Worktree(str(self.base / "orphan"), "0" * 40, "agent/claude/orphan", True,
                             f"claude agent x (pid {os.getpid()} start x)")
        with mock.patch.object(WT, "worktrees", side_effect=lambda cwd=None: real(cwd) + [unborn]), \
                mock.patch.object(WT, "lock_session_gone", return_value=False):
            trees = OR.read_trees(WT)
            line = OR.tree_line(OR.in_progress(trees)[0], {}, "/")
        tree = trees[-1]
        self.assertEqual((tree.ahead, tree.last), (0, None))
        self.assertIn("agent/claude/orphan, 0 ahead, no commit", line)

    def test_different_bad_lines_in_two_worktrees_are_two_problems(self):
        for name, text in (("b1", "Claimed: one"), ("b2", "Claimed: two")):
            wt = self.worktree(name)
            (wt / "wiki/projects/work.md").write_text(f"Status: active\n{text}\n")
        _, problems = OR.read_claims(OR.read_trees(WT), WT)
        self.assertEqual(len(problems), 2, problems)

    def test_a_stale_claim_names_the_worktree_that_holds_it(self):
        wt = self.worktree("holder")
        (wt / "wiki/projects/work.md").write_text("Status: active\nClaimed: agent/claude/gone, /nowhere, since 2026-11-24 10:00\n")
        (claim, state), = OR.read_claims(OR.read_trees(WT), WT)[0]
        self.assertEqual(state, f"STALE: no worktree at that path; remove the line in {wt}")

    def test_no_origin_main_is_a_stated_case(self):
        """A fresh or CI clone has no origin/main: one line says so, the count is unknown (never 0), and every
        worktree but the main checkout is listed with its branch and lock."""
        self.worktree("w1", commits=1)
        self.worktree("w2")
        sh("git", "update-ref", "-d", "refs/remotes/origin/main", cwd=self.main)
        trees = OR.read_trees(WT)
        self.assertEqual([t.ahead for t in trees], [None, None, None])
        out = OR.report(short=True, here="/")
        self.assertEqual(out[0], OR.BASE_MISSING)
        text = "\n".join(out)
        self.assertIn("Worktrees in progress (2; origin/main not found, so all but the main checkout):", text)
        self.assertIn("agent/claude/w1, commits ahead unknown, last commit", text)
        self.assertIn("agent/claude/w2, commits ahead unknown", text)
        self.assertNotIn(" 0 ahead", text)
        with mock.patch("os.getcwd", return_value="/"), mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(OR.main(["--short"]), 0)

    def test_a_broken_origin_main_lookup_is_an_error(self):
        with mock.patch.object(OR.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 128, "", "fatal: not a git repository")):
            with self.assertRaisesRegex(OR.OrientError, "not a git repository"):
                OR.base_exists()

    def test_a_worktree_failure_stops_before_any_network_call(self):
        calls = []

        def fake(cmd, timeout):
            calls.append(cmd[0])
            return 1, "", "offline"

        with mock.patch.object(OR, "run", side_effect=fake), mock.patch.object(WT, "worktrees", return_value=[]), \
                mock.patch.object(OR, "ROOT", self.base), self.assertRaisesRegex(OR.OrientError, "worktree list"):
            OR.report(short=False, here="/")
        self.assertEqual(calls, ["git"])  # the fetch only; gh, the hosts and the flag were never asked

    def test_git_failures_are_domain_errors(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(OR, "ROOT", Path(tmp)):
            with self.assertRaisesRegex(OR.OrientError, "worktree list"):
                OR.read_trees(WT)
        with mock.patch.object(OR.subprocess, "run", side_effect=OR.subprocess.TimeoutExpired("git", 1)):
            with self.assertRaisesRegex(OR.OrientError, "took over"):
                OR.git("status")
        with mock.patch.object(OR.subprocess, "run", side_effect=FileNotFoundError("git")):
            with self.assertRaisesRegex(OR.OrientError, "git status could not run in") as caught:
                OR.git("status")
        self.assertIsInstance(caught.exception.__cause__, FileNotFoundError)

    def test_full_report_says_when_the_network_parts_fail(self):
        self.worktree("w", commits=1)

        def fake(cmd, timeout):
            if cmd[0] == "gh":
                return 1, "", "To get started with GitHub CLI, please run:  gh auth login\nmore"
            if cmd[0] == "git":
                return 128, "", "fatal: unable to access 'https://github.com/': Could not resolve host"
            if cmd[0].endswith("operating.sh"):
                return 2, "", "operating.sh: cannot read the flag"
            return None, "", "timed out after 40 s"

        with mock.patch.object(OR, "run", side_effect=fake):
            out = OR.report(short=False, here="/")
        text = "\n".join(out)
        self.assertIn("origin/main NOT fetched (fatal: unable to access", text)
        self.assertIn("Operating flag: cannot read the operating flag (operating.sh: cannot read the flag)", text)
        self.assertIn("Open PRs: gh pr list failed (To get started with GitHub CLI", text)
        self.assertIn("deploy status unavailable (timed out after 40 s)", text)
        self.assertIn("Waiting to ingest (what a host holds that the repo lacks):", text)
        self.assertIn("  JMRI tables, Pi: Pi check timed out after 40 s, not checked (make tables-pull-pi)", text)
        self.assertIn("  STS, Pi: not checked: ", text)
        self.assertNotIn("Traceback", text)

    def test_a_full_pr_list_says_it_is_cut(self):
        prs = [{"number": n, "title": "t", "headRefName": f"b{n}", "isDraft": False} for n in range(OR.PR_LIMIT)]

        def fake(cmd, timeout):
            return (0, json.dumps(prs), "") if cmd[0] == "gh" else (0, "", "")

        with mock.patch.object(OR, "run", side_effect=fake):
            text = "\n".join(OR.report(short=False, here="/"))
        self.assertIn(f"Open PRs ({OR.PR_LIMIT}, the first {OR.PR_LIMIT} only):", text)


class NetworkPartsTest(unittest.TestCase):
    def test_open_prs_shapes(self):
        with mock.patch.object(OR, "run", return_value=(0, "not json", "")):
            self.assertIn("not JSON", OR.open_prs())
        with mock.patch.object(OR, "run", return_value=(0, '{"a": 1}', "")):
            self.assertIn("unexpected shape", OR.open_prs())
        with mock.patch.object(OR, "run", return_value=(None, "", "No such file or directory: 'gh'")):
            self.assertEqual(OR.open_prs(), "gh pr list failed (No such file or directory: 'gh')")
        prs = [{"number": 7, "title": "t", "headRefName": "agent/claude/x", "isDraft": False}]
        with mock.patch.object(OR, "run", return_value=(0, json.dumps(prs), "")):
            self.assertEqual(OR.open_prs(), prs)

    def test_operating_flag(self):
        with mock.patch.object(OR, "run", return_value=(0, "operating: by=owner since=x reason=y\n", "")):
            self.assertEqual(OR.operating(), "operating: by=owner since=x reason=y")
        with mock.patch.object(OR, "run", return_value=(1, "not operating\n", "")):
            self.assertEqual(OR.operating(), "not operating")

    def test_deploy_summary(self):
        out = page("""
            == pi
              commit=7b1d9479ba97e1e2f69fc6f87debbdc0a602bacc
              dirty=no
              date=2026-11-25T08:10:08-0500
              source=deploy
              NOTE: shipped from a detached checkout.
              This checkout is 4 commit(s) ahead and 0 behind the deployed one.
              Of them, 2 touch live artifacts; a deploy would ship:
                tools/a.py
                tools/b.py
              WARNING: the host has 1 live-touching commit(s) this checkout lacks; a deploy from here would roll back:
                tools/c.py
            == win
              No deploy stamp (host unreachable, or no deploy since stamps began).
            """)
        self.assertEqual(OR.summarize_deploy(out, 1, ""), [
            "pi: 7b1d9479 at 2026-11-25T08:10:08-0500 (deploy)",
            "  NOTE: shipped from a detached checkout.",
            "  This checkout is 4 commit(s) ahead and 0 behind the deployed one.",
            "  Of them, 2 touch live artifacts; a deploy would ship 2 paths (make deploy-status lists them)",
            "  WARNING: the host has 1 live-touching commit(s) this checkout lacks; a deploy from here would roll back "
            "1 path (make deploy-status lists them)",
            "win:",
            "  No deploy stamp (host unreachable, or no deploy since stamps began).",
        ])
        self.assertEqual(OR.summarize_deploy("", 2, "Unknown option: --x\n"),
                         ["deploy status printed nothing (exit 2: Unknown option: --x)"])
        self.assertEqual(OR.summarize_deploy("== pi\n  No deploy stamp.\n", 3, "boom\n")[-1],
                         "deploy_status.sh exit 3: boom")


class IngestTest(unittest.TestCase):
    """make orient's "waiting to ingest" lines: each source's states (nothing waiting, waiting, the Pi unreachable,
    not checked), from stubbed checks; nothing here runs a check or reaches a host."""
    OK = (0, "", "")
    DOWN = (255, "", "ssh: connect to host pi.example.invalid port 22: Operation timed out\n")

    def lines(self, pi=OK, mac=(0, "nothing\n", "")):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"STS_PI_COPY": tmp}):
            return dict(line.split(": ", 1) for line in OR.ingest_lines(pi, mac))

    def test_nothing_waiting(self):
        got = self.lines()
        self.assertEqual(got["JMRI tables, Pi"], "nothing waiting (make tables-pull-pi)")
        self.assertEqual(got["JMRI tables, Mac"], "nothing waiting (make tables-pull)")
        self.assertEqual(got["Operations Pro, Pi"], "nothing waiting (make ops-pull)")
        self.assertEqual(got["DecoderPro roster, Pi"], "nothing waiting (make roster-pull)")
        self.assertEqual(got["STS, Pi"], "not checked: the live database keeps no change marker, only a dump shows a "
                                         "change; no dump pulled to this Mac yet (make sts-pull)")
        self.assertEqual(self.lines(mac=(0, "absent\n", ""))["JMRI tables, Mac"],
                         "nothing waiting (no ~/JMRI_UserFiles/tables.xml) (make tables-pull)")

    def test_waiting(self):
        got = self.lines(pi=(0, "ops\ntables\nroster\n", ""), mac=(0, "waiting\n", ""))
        self.assertEqual(got["JMRI tables, Pi"], "a PanelPro Store not yet split in (pulled or not) (make tables-pull-pi)")
        self.assertEqual(got["JMRI tables, Mac"], "a PanelPro Store not yet split in (pulled or not) (make tables-pull)")
        self.assertEqual(got["Operations Pro, Pi"], "the Pi's session changed the Operations files since the last "
                                                    "deploy or pull (make ops-pull)")
        self.assertEqual(got["DecoderPro roster, Pi"], "DecoderPro changed the roster since the last deploy (a "
                                                       "programming session or a new loco) (make roster-pull)")
        self.assertEqual(self.lines(pi=(0, "ops\n", ""))["JMRI tables, Pi"], "nothing waiting (make tables-pull-pi)")
        self.assertEqual("nothing waiting (make roster-pull)", self.lines(pi=(0, "ops\n", ""))["DecoderPro roster, Pi"])

    def test_an_unreachable_pi_is_one_line_per_source(self):
        got = self.lines(pi=self.DOWN)
        down = "Pi unreachable, not checked (ssh: connect to host pi.example.invalid port 22: Operation timed out)"
        self.assertEqual(got["JMRI tables, Pi"], f"{down} (make tables-pull-pi)")
        self.assertEqual(got["Operations Pro, Pi"], f"{down} (make ops-pull)")
        self.assertEqual(got["DecoderPro roster, Pi"], f"{down} (make roster-pull)")
        self.assertEqual(got["JMRI tables, Mac"], "nothing waiting (make tables-pull)")  # the Mac is still read

    def test_not_checked(self):
        hung = (None, "", "timed out after 40 s")
        got = self.lines(pi=hung, mac=(1, "", "Could not check it; nothing pulled.\n"))
        self.assertEqual(got["JMRI tables, Pi"], "Pi check timed out after 40 s, not checked (make tables-pull-pi)")
        self.assertEqual(got["JMRI tables, Mac"],
                         "cannot check (exit 1: Could not check it; nothing pulled.) (make tables-pull)")
        self.assertEqual(got["DecoderPro roster, Pi"], "Pi check timed out after 40 s, not checked (make roster-pull)")
        self.assertIn("cannot read the check's answer 'tables junk'",
                      self.lines(pi=(0, "tables junk\n", ""))["Operations Pro, Pi"])
        self.assertTrue(self.lines()["STS, Pi"].startswith("not checked: "))

    def test_the_last_sts_dump(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"STS_PI_COPY": tmp}):
            (Path(tmp) / "db").mkdir()
            for name in ("sts_db3_20261124-210500.sql.gz", "sts_db3_20261125-102733.sql.gz", "other.sql.gz",
                         "sts_db3_99999999-999999.sql.gz",
                         "sts_db3_20261126-000000.sql.gz.part"):
                (Path(tmp) / "db" / name).write_text("")
            self.assertEqual(OR.last_sts_pull(), "last dump 2026-11-25 10:27")

    def test_a_checkout_unlike_origin_main_says_so(self):
        with mock.patch.object(OR, "run", return_value=(0, "", "")):
            self.assertIsNone(OR.ingest_base_note())
        with mock.patch.object(OR, "run", return_value=(1, "", "")) as run:
            self.assertIn("differ from origin/main; merge it in", OR.ingest_base_note())
        self.assertEqual(run.call_args[0][0][:4], ["git", "diff", "--quiet", "origin/main"])
        with mock.patch.object(OR, "run", return_value=(128, "", "fatal: bad revision\n")):
            self.assertIn("cannot tell whether it matches origin/main (fatal: bad revision)", OR.ingest_base_note())

    def test_the_checks_are_the_reused_read_only_ones(self):
        calls = []

        def fake(cmd, timeout):
            calls.append((cmd, timeout))
            return 0, "nothing\n", ""

        with mock.patch.object(OR, "run", side_effect=fake):
            OR.pi_unpulled(), OR.mac_tables()
        self.assertEqual([c[0][1:] for c in calls], [[], ["--status"]])
        self.assertEqual([Path(c[0][0]).relative_to(OR.ROOT).as_posix() for c in calls],
                         ["tools/hosts/deploy/pi_unpulled.sh", "tools/ops/pull_tables.sh"])
        self.assertTrue(all(t == OR.NET_TIMEOUT for _, t in calls))
        self.assertTrue(all(os.access(c[0][0], os.X_OK) for c in calls), calls)  # run directly, so executable


class SiteDeployTest(unittest.TestCase):
    """make orient's website line, read from the main checkout's .deploy-manifest.json (ADR-040)."""

    def lines(self, record: dict | None, git_results=((0, "0\n", ""), (0, "", ""))) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if record is not None:
                (root / ".deploy-manifest.json").write_text(json.dumps(record), encoding="utf-8")
            with mock.patch.object(OR, "ROOT_MAIN", root), mock.patch.object(OR, "run", side_effect=list(git_results)):
                return OR.site_deploy_lines()

    def test_no_record_and_counts_only(self):
        self.assertEqual(self.lines(None), ["website: no deploy record"])
        self.assertEqual(self.lines({"files": 3}), ["website: the last deploy kept counts only (before ADR-040)"])

    def test_record_on_main(self):
        record = {"files": 3, "deploy": {"commit": "0123456789abcdef", "branch": "main", "dirty": False,
                                         "worktree": "/elsewhere", "finished": "2026-11-25T21:40:00Z"}}
        self.assertEqual(self.lines(record), ["website: 01234567 at 2026-11-25T21:40:00Z (main, /elsewhere)"])

    def test_record_behind_and_off_main(self):
        record = {"deploy": {"commit": "0123456789abcdef", "branch": "agent/x", "dirty": True,
                             "worktree": "/w", "finished": "t"}}
        self.assertEqual(self.lines(record, ((0, "2\n", ""), (1, "", ""))), [
            "website: 01234567 at t (agent/x, /w, uncommitted changes)",
            "  origin/main has 2 commit(s) under www/ that the site lacks",
            "  NOTE: the deployed commit is not on origin/main",
        ])


class SiteDeployUnknownCommitTest(SiteDeployTest):
    def test_unknown_commit_is_named(self):
        record = {"deploy": {"commit": "0123456789abcdef", "branch": "main", "worktree": "/w", "finished": "t"}}
        self.assertEqual(self.lines(record, ((128, "", "fatal: bad revision\n"),))[1:],
                         ["  cannot compare the deployed commit with origin/main (fatal: bad revision)"])


class HookTest(unittest.TestCase):
    def proc(self, code: str) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_lines_failure_and_timeout(self):
        import time
        got = HOOK.orient_lines(self.proc("print('Claims (0): none')"), time.monotonic())
        self.assertEqual(got[1:], ["Claims (0): none"])
        got = HOOK.orient_lines(self.proc("import sys; print('orient: git broke', file=sys.stderr); sys.exit(2)"),
                                time.monotonic())
        self.assertEqual(got, ["Orient failed: orient: git broke; run make orient"])
        got = HOOK.orient_lines(self.proc("int('x')"), time.monotonic())
        self.assertEqual(got, ["Orient failed: ValueError: invalid literal for int() with base 10: 'x'; run make orient"])
        with mock.patch.object(HOOK, "ORIENT_TIMEOUT", 0.5):
            got = HOOK.orient_lines(self.proc("import time; time.sleep(30)"), time.monotonic())
        self.assertEqual(got, ["Orient took over 0.5 s and was stopped; run make orient"])
        self.assertEqual(HOOK.orient_lines("Orient did not start (x); run make orient", 0.0),
                         ["Orient did not start (x); run make orient"])

    def test_old_checkout_and_start_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(HOOK.start_orient(tmp, tmp))
        with mock.patch.object(HOOK.subprocess, "Popen", side_effect=OSError("no python")):
            line, _ = HOOK.start_orient(str(ROOT), str(ROOT))
        self.assertEqual(line, "Orient did not start (no python); run make orient")

    def test_the_real_short_form_runs_fast_and_without_network(self):
        import time
        with mock.patch.object(OR.subprocess, "run", wraps=subprocess.run) as run:
            start = time.monotonic()
            lines = OR.report(short=True, here=str(ROOT))
            took = time.monotonic() - start
        self.assertTrue(any(l.startswith("Worktrees in progress") for l in lines))
        self.assertLess(took, HOOK.ORIENT_TIMEOUT)
        programs = {call.args[0][0] for call in run.call_args_list}
        self.assertLessEqual(programs, {"git", "ps"})
        self.assertFalse(any("fetch" in call.args[0] for call in run.call_args_list))


if __name__ == "__main__":
    unittest.main()
