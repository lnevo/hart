"""tools/hosts/deploy/ci_pass.py: the gate skips G4 only on CI's full passing check.sh run for the exact commit shipped.

Each test builds a throwaway git repo (its origin a GitHub URL) and answers gh with canned GitHub API replies; nothing
reaches GitHub. The API replies follow the shapes of a real main push run (2026-11-24, run 45488560774); the job
log (fixtures/ci_pass/main_pass.txt) is a real one, run 45741317490 (attempt 2), main's first passing push run in
the shape check.sh prints since ADR-037 stage 6 (one panels-<step> job per panels step); the others are edited copies,
one failure each.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hosts/deploy"))
import ci_pass  # noqa: E402

SLUG = "owner/repo"
RUN_ID = 111
JOB_ID = 222


def git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return env


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args], env=git_env(),
                          capture_output=True, text=True, check=True).stdout.strip()


FIXTURES = Path(__file__).resolve().parent / "fixtures/ci_pass"
# The plugin commit main pinned at 05e73a40, the commit of the real log in main_pass.txt (its tables step printed
# "plugin: submodule at 09bcf066"); each test repo pins it too.
PIN = "09bcf066d71545fb2081e89fce5bb7e75bac1e79"


def fixture(name: str) -> str:
    """A job log as GitHub serves it. main_pass.txt is check.yml run 45741317490 (attempt 2, job 139655918018, push of
    05e73a40 to main, 2026-11-26 UTC), trimmed as before: the log's first three lines, the check.sh step's env block,
    the panels-<step> jobs and the static jobs after them up to levels-page, the step's last lines (from ruff) and the
    stamp manifest step; no token lines. The others are edited copies of it (one failure each)."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def edited(old: str, new: str, name: str = "main_pass.txt") -> str:
    """The fixture with `old` (which must be in it, once) replaced by `new`."""
    text = fixture(name)
    assert text.count(old) == 1, f"{name} holds {text.count(old)} copies of {old!r}, not one"
    return text.replace(old, new)


class FakeGitHub:
    """Answers the four gh calls ci_pass makes; each reply can be replaced, or set to an exception, per test."""

    def __init__(self, sha: str) -> None:
        self.sha = sha
        self.calls: list[list[str]] = []
        self.runs: dict[str, Any] = {"total_count": 1, "workflow_runs": [self.run()]}
        self.jobs: dict[str, Any] = {"total_count": 1, "jobs": [{
            "id": JOB_ID, "name": "check", "head_sha": sha, "status": "completed", "conclusion": "success",
            "steps": [{"name": "Run ./tools/check.sh", "conclusion": "success"},
                      {"name": "Save the check stamps for pull requests on this commit", "conclusion": "success"}]}]}
        self.caches: dict[str, Any] = {"total_count": 1, "actions_caches": [{"key": f"check-stamps-{sha}", "ref": "refs/heads/main"}]}
        self.log = fixture("main_pass.txt")
        self.fail: dict[str, Exception] = {}

    def run(self, **over) -> dict:
        r = {"id": RUN_ID, "run_number": 7, "head_sha": self.sha, "head_branch": "main", "event": "push",
             "path": ".github/workflows/check.yml", "status": "completed", "conclusion": "success"}
        r.update(over)
        return r

    def __call__(self, args: list[str], timeout: int) -> str:
        self.calls.append(args)
        path = next(a for a in args if a.startswith("repos/"))
        for name, reply in (("/workflows/check.yml/runs", self.runs), (f"/runs/{RUN_ID}/jobs", self.jobs),
                            ("/actions/caches", self.caches), (f"/jobs/{JOB_ID}/logs", self.log)):
            if path.endswith(name):
                if name in self.fail:
                    raise self.fail[name]
                return reply if isinstance(reply, str) else json.dumps(reply)
        raise AssertionError(f"unexpected gh call: {args}")


class GhRepoCase(unittest.TestCase):
    """A throwaway repo pinning the plugin, its origin on GitHub, and a FakeGitHub for its one commit."""

    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo, True)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "update-index", "--add", "--cacheinfo", f"160000,{PIN},{ci_pass.PLUGIN}")
        git(self.repo, "commit", "-q", "-m", "first, pinning the plugin")
        (self.repo / ci_pass.PLUGIN).mkdir(parents=True)     # an unpopulated submodule: git status lists nothing
        git(self.repo, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        self.gh = FakeGitHub(self.sha)


class CiPassTest(GhRepoCase):
    def verdict(self, sha: str | None = None) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = ci_pass.main(["--commit", sha or self.sha], root=self.repo, gh=self.gh)
        return rc, out.getvalue() + err.getvalue()

    def assert_runs_g4(self, text: str, lead: str = "no CI pass") -> str:
        rc, out = self.verdict()
        self.assertEqual(1, rc, out)
        self.assertTrue(out.startswith(f"ran G4: {lead} for {self.sha[:12]}: "), out)
        self.assertIn(text, out)
        return out

    # ---- the pass ----

    def test_a_full_pass_for_this_commit_skips(self) -> None:
        rc, out = self.verdict()
        self.assertEqual(0, rc, out)
        self.assertEqual(f"skipped G4: CI full pass for {self.sha[:12]} (check.yml run {RUN_ID}, "
                         f"stamps check-stamps-{self.sha[:12]}...)\n", out)
        self.assertIn(f"head_sha={self.sha}", self.gh.calls[0])

    def test_the_ssh_origin_url_is_read_too(self) -> None:
        git(self.repo, "remote", "set-url", "origin", f"git@github.com:{SLUG}.git")
        self.assertEqual(0, self.verdict()[0])

    # ---- the commit ----

    def test_a_pass_for_another_commit_does_not_count(self) -> None:
        self.gh.runs["workflow_runs"] = [self.gh.run(head_sha="f" * 40)]
        self.assert_runs_g4("CI has no push run")

    def test_the_checkout_at_another_commit_does_not_count(self) -> None:
        rc, out = self.verdict("e" * 40)
        self.assertEqual(1, rc)
        self.assertIn(f"the checkout is at {self.sha[:12]}, not the commit eeeeeeeeeeee", out)
        self.assertEqual([], self.gh.calls, "asked GitHub about a commit the checkout is not")

    def test_an_uncommitted_file_does_not_count(self) -> None:
        (self.repo / "tables.xml").write_text("edited\n", encoding="utf-8")
        self.assert_runs_g4("1 uncommitted or untracked path(s) (first: ?? tables.xml)")
        self.assertEqual([], self.gh.calls)

    def test_a_pull_request_or_branch_run_does_not_count(self) -> None:
        for over in ({"event": "pull_request"}, {"head_branch": "feature"}, {"path": ".github/workflows/other.yml"}):
            with self.subTest(over=over):
                self.gh.runs["workflow_runs"] = [self.gh.run(**over)]
                self.assert_runs_g4("CI has no push run")

    def test_a_failed_or_unfinished_newest_run_does_not_count(self) -> None:
        older = self.gh.run(id=100, run_number=6)
        for over, text in (({"conclusion": "failure"}, f"CI's run {RUN_ID} ended failure"),
                           ({"status": "in_progress", "conclusion": None}, f"CI's run {RUN_ID} is in_progress")):
            with self.subTest(over=over):
                self.gh.runs = {"total_count": 2, "workflow_runs": [older, self.gh.run(**over)]}
                self.assert_runs_g4(text)

    def test_a_failed_job_or_check_step_does_not_count(self) -> None:
        job = self.gh.jobs["jobs"][0]
        job["steps"][0]["conclusion"] = "skipped"
        self.assert_runs_g4("check.sh step in job 222 ended skipped")
        job["conclusion"] = "failure"
        self.assert_runs_g4("CI's job 222 ended failure")

    # ---- the stamps ----

    def test_missing_stamps_do_not_count(self) -> None:
        self.gh.caches = {"total_count": 0, "actions_caches": []}
        self.assert_runs_g4("no check stamps check-stamps-")

    def test_stamps_on_another_ref_or_key_do_not_count(self) -> None:
        for entry in ({"key": f"check-stamps-{self.sha}", "ref": "refs/pull/5/merge"},
                      {"key": f"check-stamps-{self.sha}-x", "ref": "refs/heads/main"}):
            with self.subTest(entry=entry):
                self.gh.caches = {"total_count": 1, "actions_caches": [entry]}
                self.assert_runs_g4("no check stamps")

    # ---- a partial run ----

    def test_the_real_main_log_passes(self) -> None:
        """The log of a real passing push run of main (main_pass.txt) is a pass: the check reads check.sh as it
        prints today, not a shape of its own."""
        ci_pass.check_log(fixture("main_pass.txt"), PIN)

    def test_a_partial_or_skipping_run_does_not_count(self) -> None:
        record = "  CHECK_RECORD_TO: /home/runner/work/hart/hart/.cache/ci/main-stamps"
        cases = (
            (edited("  CHECK_SKIP_NOTE: \n", "  CHECK_SKIP_NOTE: \n  CHECK_ONLY: unit-\n"), "CHECK_ONLY: a partial run"),
            (edited(record, "  CHECK_RECORD_TO: "), "recorded no stamps"),
            (edited(record, "  NOT_RECORDING: 1"), "recorded no stamps"),
            (fixture("pr_skip_from.txt"), "skipped jobs on older stamps (CHECK_SKIP_FROM set)"),
            (fixture("schematic_not_required.txt"), "SCHEMATIC_REQUIRED '0', not 1 as G4 runs"),
        )
        for log, text in cases:
            with self.subTest(text=text):
                self.gh.log = log
                self.assert_runs_g4(text)

    def test_a_run_that_did_not_run_g4s_tables_check_does_not_count(self) -> None:
        """G4 is build_tables.py --check with the plugin at its pin: the panels-tables job must show it ran and
        passed. Each fixture is the main log with one thing wrong."""
        cases = (
            (fixture("panels_missing.txt"), "0 '--- panels-tables (Ns)' job headings, not one"),
            (fixture("panels_current_on_main.txt"), "skipped the panels-tables job (current on older stamps)"),
            (fixture("tables_step_skipped.txt"), "skipped the panels-tables job (current on older stamps)"),
            (fixture("tables_plugin_skipped.txt"), "panels-tables job was skipped or failed: SKIPPED tables check"),
            (fixture("tables_other_plugin.txt"), "did not draw with the commit's plugin pin 09bcf066 (it printed "
                                                 "'plugin: /tmp/other-plugin (SCHEMATIC_PLUGIN)')"),
            (fixture("truncated.txt"), "does not end ALL PASSED (last line 'plugin: submodule at 09bcf066')"),
            (edited("ALL PASSED", "FAILED"), "does not end ALL PASSED (last line 'FAILED')"),
            (edited("--- panels-tables (3s)", "--- panels-tables FAILED (3s)"), "its panels-tables job FAILED"),
            (edited("--- panels-tables (3s)", "--- panels-tables (3s)\n--- panels-tables (1s)"),
             "2 '--- panels-tables (Ns)' job headings"),
            (edited("--- panels-tables (3s)", "--- tables-renamed (3s)"), "0 '--- panels-tables (Ns)' job headings"),
            (edited("ok: jmri/layouts/hart/output/tables.xml current (", "STALE ("),
             "did not print that tables.xml is current"),
        )
        for log, text in cases:
            with self.subTest(text=text):
                self.gh.log = log
                self.assert_runs_g4(text)

    def test_the_tables_proof_is_the_tables_jobs_own_lines(self) -> None:
        """Another job's lines (the stamps block after it, the next job) prove nothing for G4, and a log of the shape
        before stage 6 (one panels job, "== tables" in it) is no pass."""
        log = fixture("main_pass.txt")
        mine = log[log.index("--- panels-tables (3s)"):log.index("--- stamps (panels-tables):")]
        ok = next(line for line in mine.splitlines() if "ok: jmri/layouts/hart/output/tables.xml current (" in line)
        self.gh.log = log.replace(ok + "\n", "")
        self.assert_runs_g4("did not print that tables.xml is current")
        old = fixture("main_pass.txt").replace("--- panels-tables (3s)", "== tables").replace(
            "--- panels-hands (0s)", "--- panels (69s)")
        self.gh.log = old
        self.assert_runs_g4("0 '--- panels-tables (Ns)' job headings, not one")

    def test_a_commit_with_another_plugin_pin_does_not_count(self) -> None:
        """CI drew with 09bcf066; a commit pinning another plugin is not what that log checked."""
        other = "a" * 40
        git(self.repo, "update-index", "--cacheinfo", f"160000,{other},{ci_pass.PLUGIN}")
        git(self.repo, "commit", "-q", "-m", "another pin")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        self.gh = FakeGitHub(self.sha)
        self.assert_runs_g4("did not draw with the commit's plugin pin aaaaaaaa")

    def test_a_commit_that_pins_no_plugin_does_not_count(self) -> None:
        git(self.repo, "rm", "-q", "--cached", ci_pass.PLUGIN)
        git(self.repo, "commit", "-q", "-m", "no plugin")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        self.gh = FakeGitHub(self.sha)
        self.assert_runs_g4("the commit pins no schematic-maps plugin at external/model-railroad-skills (no entry)")
        self.assertEqual([], self.gh.calls, "asked GitHub about a commit G4 cannot check")

    # ---- unreadable ----

    def test_gh_failing_is_unreadable(self) -> None:
        for name in ("/workflows/check.yml/runs", f"/runs/{RUN_ID}/jobs", "/actions/caches", f"/jobs/{JOB_ID}/logs"):
            with self.subTest(call=name):
                self.gh.fail = {name: ci_pass.Unreadable("gh api repos/x failed (exit 1): HTTP 401")}
                self.assert_runs_g4("HTTP 401", lead="CI stamps unreadable")

    def test_malformed_replies_are_unreadable(self) -> None:
        cases = (
            ("runs", "<html>rate limited</html>", "the check.yml runs is not JSON"),
            ("runs", "[]", "not a JSON object"),
            ("runs", {"total_count": 1}, "has no list 'workflow_runs'"),
            ("runs", {"total_count": 150, "workflow_runs": [None]}, "more than one page"),
            ("runs", {"total_count": 1, "workflow_runs": ["x"]}, "not an object"),
            ("jobs", {"jobs": []}, "0 jobs named 'check'"),
            ("caches", {"total_count": 0}, "has no list 'actions_caches'"),
            ("log", "no groups here", "0 check.sh steps"),
        )
        for attr, reply, text in cases:
            with self.subTest(text=text):
                self.gh = FakeGitHub(self.sha)
                setattr(self.gh, attr, reply)
                self.assert_runs_g4(text, lead="CI stamps unreadable")

    def test_records_of_another_shape_are_unreadable(self) -> None:
        """Every GitHub record the check reads is typed: an entry that is not an object, or a field of another type,
        is unreadable, never skipped or taken as it is."""
        def run_with(**over: object) -> None:
            self.gh.runs = {"total_count": 1, "workflow_runs": [self.gh.run(**over)]}
        cases: tuple[tuple[Callable[[], object], str], ...] = (
            (lambda: run_with(id="111"), "a check.yml run has no int 'id'"),
            (lambda: run_with(run_number=True), "a check.yml run has no int 'run_number'"),
            (lambda: run_with(conclusion=0), "a check.yml run has 'conclusion' 0, not a string or null"),
            (lambda: self.gh.jobs["jobs"].append("x"), "run 111's jobs hold an entry that is not an object"),
            (lambda: self.gh.jobs["jobs"][0]["steps"].append(None), "job 222 hold an entry that is not an object"),
            (lambda: self.gh.jobs["jobs"][0]["steps"][0].pop("name"), "a step of job 222 has no str 'name'"),
            (lambda: self.gh.caches["actions_caches"].append(7), "CI's cache list hold an entry that is not an object"),
            (lambda: self.gh.caches["actions_caches"][0].pop("ref"), "a CI cache entry has no str 'ref'"),
        )
        for change, text in cases:
            with self.subTest(text=text):
                self.gh = FakeGitHub(self.sha)
                change()
                self.assert_runs_g4(text, lead="CI stamps unreadable")

    def test_a_job_for_another_commit_is_unreadable(self) -> None:
        self.gh.jobs["jobs"][0]["head_sha"] = "f" * 40
        self.assert_runs_g4("job 222 names commit ffffffffffff", lead="CI stamps unreadable")

    def test_an_origin_off_github_is_unreadable(self) -> None:
        git(self.repo, "remote", "set-url", "origin", "https://example.invalid/owner/repo.git")
        self.assert_runs_g4("origin is not a GitHub repository", lead="CI stamps unreadable")

    def test_a_git_failure_is_named_not_a_traceback(self) -> None:
        shutil.rmtree(self.repo / ".git")
        out = self.assert_runs_g4("git rev-parse --verify HEAD^{commit} failed (exit", lead="the checkout cannot be read")
        self.assertNotIn("Traceback", out)

    def test_a_submodule_at_another_commit_counts_and_edits_inside_one_do_not(self) -> None:
        """Local edits inside a submodule (sts-docker's compose data) do not block the skip; a submodule checked out
        at another commit than the one recorded does."""
        sub = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, sub, True)
        git(sub, "init", "-q", "-b", "main")
        git(sub, "commit", "-q", "--allow-empty", "-m", "one")
        git(self.repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "ext")
        git(self.repo, "commit", "-q", "-m", "add ext")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        self.gh = FakeGitHub(self.sha)
        (self.repo / "ext/local.txt").write_text("compose data\n", encoding="utf-8")
        self.assertEqual(0, self.verdict()[0], "an untracked file inside a submodule blocked the skip")
        git(self.repo / "ext", "commit", "-q", "--allow-empty", "-m", "two")
        self.assert_runs_g4("uncommitted or untracked path(s) (first: M ext)")

    def test_an_unexpected_failure_is_exit_3_with_its_reason(self) -> None:
        def boom(args, timeout):
            raise KeyError("a bug")
        rc, out = self.verdict_with(boom)
        self.assertEqual(3, rc, out)
        self.assertIn(f"ran G4: the CI pass check failed for {self.sha[:12]}: KeyError", out)

    def verdict_with(self, gh) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            rc = ci_pass.main(["--commit", self.sha], root=self.repo, gh=gh)
        return rc, out.getvalue()

    def test_a_bad_commit_is_refused_up_front(self) -> None:
        for bad in ("abc", self.sha.upper(), self.sha + "0", "HEAD"):
            with self.subTest(bad=bad):
                rc, out = self.verdict(bad)
                self.assertEqual(2, rc)
                self.assertIn("--commit must be a full 40-character commit sha", out)
        self.assertEqual([], self.gh.calls)


class MainRedTest(GhRepoCase):
    """--main-red (the gate's G0c): exit 4 only for a finished push run on main that ended failure, cancelled or
    timed_out; exit 0 with the reason for every other case, a bad commit and a bug here included."""

    URL = f"https://github.com/{SLUG}/actions/runs/{RUN_ID}"
    NOT_BLOCKING = ci_pass.NOT_BLOCKING

    def red(self, sha: str | None = None) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            rc = ci_pass.main(["--main-red", "--commit", sha or self.sha], root=self.repo, gh=self.gh)
        return rc, out.getvalue()

    def newest(self, **over) -> None:
        """The newest run for the commit takes `over`; an older passing run stands beside it."""
        self.gh.runs = {"total_count": 2, "workflow_runs": [self.gh.run(id=100, run_number=6), self.gh.run(**over)]}

    def test_a_red_run_stops_and_names_it(self) -> None:
        for conclusion in ci_pass.RED:
            with self.subTest(conclusion=conclusion):
                self.newest(conclusion=conclusion, html_url=self.URL)
                rc, out = self.red()
                self.assertEqual(4, rc, out)
                self.assertEqual(f"STOP: main is red: the push run of .github/workflows/check.yml on main for "
                                 f"{self.sha[:12]} ended {conclusion} ({self.URL}). Fix forward or revert first, then "
                                 "deploy the fixed main. Nothing was sent to any host.\n", out)

    def test_the_url_falls_back_to_the_run_id(self) -> None:
        self.newest(conclusion="failure")
        rc, out = self.red()
        self.assertEqual(4, rc)
        self.assertIn(f"({self.URL})", out)

    def test_a_green_run_passes(self) -> None:
        self.newest(html_url=self.URL)
        self.assertEqual((0, f"main red check: main's push run for {self.sha[:12]} passed ({self.URL})\n"), self.red())
        self.assertEqual(1, len(self.gh.calls), "asked more than the runs list")

    def test_a_run_still_going_is_not_waited_for(self) -> None:
        for status in ("queued", "in_progress", "waiting"):
            with self.subTest(status=status):
                self.newest(status=status, conclusion=None)
                rc, out = self.red()
                self.assertEqual(0, rc, out)
                self.assertEqual(f"main red check: main's push run for {self.sha[:12]} is {status} ({self.URL}); "
                                 f"not waiting for it, {self.NOT_BLOCKING}\n", out)

    def test_an_older_red_run_does_not_count_when_the_newest_passed(self) -> None:
        self.gh.runs = {"total_count": 2, "workflow_runs": [self.gh.run(), self.gh.run(id=100, run_number=6,
                                                                                         conclusion="failure")]}
        self.assertEqual(0, self.red()[0])

    def test_another_ending_goes_on(self) -> None:
        for conclusion in ("startup_failure", "neutral", "skipped", "action_required", "stale", None):
            with self.subTest(conclusion=conclusion):
                self.newest(conclusion=conclusion)
                rc, out = self.red()
                self.assertEqual(0, rc, out)
                self.assertIn(f"ended {conclusion} ({self.URL}), not failure, cancelled, timed_out; "
                              f"{self.NOT_BLOCKING}", out)

    def test_no_run_yet_for_the_commit_does_not_block(self) -> None:
        """Not queued yet, a branch or a pull request's run only: none of them blocks."""
        for runs in ([], [self.gh.run(event="pull_request", conclusion="failure")],
                     [self.gh.run(head_branch="feature", conclusion="failure")]):
            with self.subTest(runs=runs):
                self.gh.runs = {"total_count": len(runs), "workflow_runs": runs}
                rc, out = self.red()
                self.assertEqual(0, rc, out)
                self.assertEqual(f"main red check: no push run of check.yml on main for {self.sha[:12]} yet; "
                                 f"{self.NOT_BLOCKING}\n", out)

    def test_a_github_error_does_not_block_and_is_named(self) -> None:
        for err in ("gh (the GitHub CLI) is not installed", "gh api -X failed (exit 1): HTTP 401: Bad credentials",
                    "gh api -X took over 30 s"):
            with self.subTest(err=err):
                self.gh.fail = {"/workflows/check.yml/runs": ci_pass.Unreadable(err)}
                rc, out = self.red()
                self.assertEqual(0, rc, out)
                self.assertEqual(f"main red check: could not ask GitHub ({err}); {self.NOT_BLOCKING}\n", out)
        for reply, text in (("<html>", "is not JSON"), ({"total_count": 1, "workflow_runs": [{"head_sha": self.sha,
                            "event": "push", "head_branch": "main", "path": ".github/workflows/check.yml",
                            "run_number": 1}]}, "has no str 'status'")):
            with self.subTest(text=text):
                self.gh = FakeGitHub(self.sha)
                self.gh.runs = reply  # type: ignore[assignment]
                rc, out = self.red()
                self.assertEqual(0, rc, out)
                self.assertIn(text, out)
                self.assertTrue(out.startswith("main red check: could not ask GitHub ("), out)

    def test_an_origin_off_github_does_not_block(self) -> None:
        git(self.repo, "remote", "set-url", "origin", "https://example.invalid/owner/repo.git")
        rc, out = self.red()
        self.assertEqual(0, rc, out)
        self.assertIn("could not ask GitHub (origin is not a GitHub repository", out)
        self.assertEqual([], self.gh.calls)

    def test_hart_ci_repo_names_the_repository(self) -> None:
        """The site deploy's tests run in a repo whose origin is a local folder: HART_CI_REPO names the one to ask."""
        git(self.repo, "remote", "set-url", "origin", "/tmp/not-github.git")
        self.addCleanup(os.environ.pop, "HART_CI_REPO", None)
        os.environ["HART_CI_REPO"] = SLUG
        self.newest(conclusion="failure")
        self.assertEqual(4, self.red()[0])
        self.assertIn(f"repos/{SLUG}/actions/workflows/check.yml/runs", self.gh.calls[-1])
        os.environ["HART_CI_REPO"] = "not a slug"
        rc, out = self.red()
        self.assertEqual(0, rc)
        self.assertIn("HART_CI_REPO is not owner/name", out)

    def test_it_reads_no_checkout_state(self) -> None:
        """A dirty checkout or another HEAD does not hide a red main: the question is about the commit's run."""
        (self.repo / "tables.xml").write_text("edited\n", encoding="utf-8")
        other = "e" * 40
        self.gh = FakeGitHub(other)
        self.gh.runs = {"total_count": 1, "workflow_runs": [self.gh.run(conclusion="failure")]}
        self.assertEqual(4, self.red(other)[0])

    def test_a_bug_does_not_block_and_names_itself(self) -> None:
        def boom(args, timeout):
            raise KeyError("a bug")
        self.gh = boom  # type: ignore[assignment]
        rc, out = self.red()
        self.assertEqual(0, rc, out)
        self.assertEqual(f"main red check: failed for {self.sha[:12]}: KeyError: 'a bug'; {self.NOT_BLOCKING}\n", out)

    def test_a_bad_call_does_not_block(self) -> None:
        """A --main-red call argparse refuses still prints the gate's line and exits 0; without --main-red a bad call
        is exit 2, and an abbreviation does not stand for --main-red."""
        for argv, text in ((["--main-red"], "the following arguments are required: --commit"),
                           (["--main-red", "--commit"], "argument --commit: expected one argument"),
                           (["--main-red", "--commit", self.sha, "--extra"], "unrecognized arguments: --extra")):
            with self.subTest(argv=argv):
                out = io.StringIO()
                with redirect_stdout(out), redirect_stderr(out):
                    rc = ci_pass.main(argv, root=self.repo, gh=self.gh)
                self.assertEqual(0, rc, out.getvalue())
                self.assertEqual(f"main red check: a bad call ({text}); {self.NOT_BLOCKING}\n", out.getvalue())
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            rc = ci_pass.main(["--main", "--commit", self.sha], root=self.repo, gh=self.gh)
        self.assertEqual(2, rc, out.getvalue())
        self.assertIn("unrecognized arguments: --main", out.getvalue())
        self.assertEqual([], self.gh.calls)

    def test_a_crash_before_the_checks_handler_does_not_block(self) -> None:
        """A failure while the call is read, before main_red_verdict's own handler, still ends in the line."""
        out = io.StringIO()
        with unittest.mock.patch.object(ci_pass, "parser", side_effect=RuntimeError("no parser")), \
                redirect_stdout(out), redirect_stderr(out):
            rc = ci_pass.main(["--main-red", "--commit", self.sha], root=self.repo, gh=self.gh)
        self.assertEqual(0, rc, out.getvalue())
        self.assertEqual(f"main red check: failed before the check: RuntimeError: no parser; {self.NOT_BLOCKING}\n",
                         out.getvalue())

    def test_the_script_run_alone_prints_the_line_for_a_bad_call(self) -> None:
        done = subprocess.run([sys.executable, str(ROOT / "tools/hosts/deploy/ci_pass.py"), "--main-red"],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"main red check: a bad call (the following arguments are required: --commit); "
                         f"{self.NOT_BLOCKING}\n", done.stdout)
        self.assertEqual("", done.stderr)

    def test_a_bad_commit_does_not_block(self) -> None:
        rc, out = self.red("HEAD")
        self.assertEqual(0, rc)
        self.assertEqual("main red check: --commit must be a full 40-character commit sha, not 'HEAD'; "
                         f"{self.NOT_BLOCKING}\n", out)
        self.assertEqual([], self.gh.calls)


class RunGhTest(unittest.TestCase):
    """The real gh runner: a missing gh or a failing call is Unreadable with its message, never a traceback."""

    def setUp(self) -> None:
        self.bin = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.bin, True)
        self.path = os.environ.get("PATH", "")
        self.addCleanup(os.environ.__setitem__, "PATH", self.path)

    def test_no_gh(self) -> None:
        os.environ["PATH"] = str(self.bin)
        with self.assertRaisesRegex(ci_pass.Unreadable, "gh \\(the GitHub CLI\\) is not installed") as cm:
            ci_pass.run_gh(["api", "repos/x"], 5)
        self.assertIsInstance(cm.exception.__cause__, FileNotFoundError)

    def test_a_failing_gh_names_its_last_error_line(self) -> None:
        gh = self.bin / "gh"
        gh.write_text('#!/bin/sh\necho "noise" >&2\necho "HTTP 404: Not Found" >&2\nexit 1\n', encoding="utf-8")
        gh.chmod(0o755)
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{self.path}"
        with self.assertRaisesRegex(ci_pass.Unreadable, r"gh api repos/x failed \(exit 1\): HTTP 404: Not Found"):
            ci_pass.run_gh(["api", "repos/x"], 5)

    def test_bytes_that_are_not_utf8_are_unreadable(self) -> None:
        gh = self.bin / "gh"
        gh.write_text("#!/bin/sh\nprintf 'log \\377\\376 bytes\\n'\n", encoding="utf-8")
        gh.chmod(0o755)
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{self.path}"
        with self.assertRaisesRegex(ci_pass.Unreadable, "not UTF-8") as cm:
            ci_pass.run_gh(["api", "repos/x/logs"], 5)
        self.assertIsInstance(cm.exception.__cause__, UnicodeDecodeError)

    def test_a_hung_gh_times_out(self) -> None:
        gh = self.bin / "gh"
        gh.write_text("#!/bin/sh\nexec sleep 5\n", encoding="utf-8")
        gh.chmod(0o755)
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{self.path}"
        with self.assertRaisesRegex(ci_pass.Unreadable, "took over 1 s"):
            ci_pass.run_gh(["api", "repos/x"], 1)


if __name__ == "__main__":
    unittest.main()
