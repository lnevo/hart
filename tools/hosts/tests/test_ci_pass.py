"""tools/hosts/deploy/ci_pass.py: the gate skips G4 only on CI's full passing check.sh run for the exact commit shipped.

Each test builds a throwaway git repo (its origin a GitHub URL) and answers gh with canned GitHub API replies; nothing
reaches GitHub. The replies follow the shapes of a real main push run (2026-11-24, run 45488560774).
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
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

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


def log_text(env: dict[str, str] | None = None, out: list[str] | None = None) -> str:
    """A job log as GitHub serves it: a timestamp on every line, the check.sh step's group with its env block."""
    env = {"SCHEMATIC_REQUIRED": "1", "CHECK_SKIP_FROM": "", "CHECK_SKIP_NOTE": "",
           "CHECK_RECORD_TO": "/home/runner/work/repo/repo/.cache/ci/main-stamps"} if env is None else env
    out = [
        "--- static (20s)",
        "--- tables-browser",
        "--- tables",
        "plugin: submodule at 19261998",
        "ok: jmri/layouts/hart/output/tables.xml current (69 signal mast logics, 1 digicon masts)",
        "--- levels-svg",
        "levels_svg: SKIPPED, the plan is not on this machine",
        "--- unit-hosts (40s)",
        "1 job(s) printed SKIPPED and checked only part of their inputs: static",
        "ALL PASSED",
    ] if out is None else out
    lines = ["##[group]Run actions/checkout@v4", "##[endgroup]",
             "##[group]Run ./tools/check.sh", "\x1b[36;1m./tools/check.sh\x1b[0m", "shell: /usr/bin/bash -e {0}", "env:",
             *(f"  {k}: {v}" for k, v in env.items()), "##[endgroup]", *out,
             "##[group]Run python3 tools/ci/stamp_gate.py manifest .cache/ci/main-stamps --sha \"$GITHUB_SHA\"",
             "##[endgroup]"]
    return "\n".join(f"2026-11-24T21:14:52.{i:07d}Z {line}" for i, line in enumerate(lines)) + "\n"


class FakeGitHub:
    """Answers the four gh calls ci_pass makes; each reply can be replaced, or set to an exception, per test."""

    def __init__(self, sha: str) -> None:
        self.sha = sha
        self.calls: list[list[str]] = []
        self.runs = {"total_count": 1, "workflow_runs": [self.run()]}
        self.jobs = {"total_count": 1, "jobs": [{
            "id": JOB_ID, "name": "check", "head_sha": sha, "status": "completed", "conclusion": "success",
            "steps": [{"name": "Run ./tools/check.sh", "conclusion": "success"},
                      {"name": "Save the check stamps for pull requests on this commit", "conclusion": "success"}]}]}
        self.caches = {"total_count": 1, "actions_caches": [{"key": f"check-stamps-{sha}", "ref": "refs/heads/main"}]}
        self.log = log_text()
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


class CiPassTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo, True)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "first")
        git(self.repo, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
        self.sha = git(self.repo, "rev-parse", "HEAD")
        self.gh = FakeGitHub(self.sha)

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

    def test_a_partial_or_skipping_run_does_not_count(self) -> None:
        base = {"CHECK_SKIP_FROM": "", "CHECK_RECORD_TO": "/stamps"}
        for env, text in (({**base, "CHECK_ONLY": "unit-"}, "CHECK_ONLY: a partial run"),
                          ({**base, "CHECK_SKIP_FROM": "/old"}, "skipped jobs on older stamps"),
                          ({**base, "CHECK_RECORD_TO": ""}, "recorded no stamps"),
                          ({"CHECK_SKIP_FROM": ""}, "recorded no stamps")):
            with self.subTest(env=env):
                self.gh.log = log_text(env=env)
                self.assert_runs_g4(text)

    def test_a_run_that_did_not_check_the_tables_does_not_count(self) -> None:
        cases = (
            (["--- static (20s)", "ALL PASSED"], "0 '--- tables' checks"),
            (["static: current, skipped", "--- tables", "ok: jmri/layouts/hart/output/tables.xml current (1)",
              "ALL PASSED"], "no run of the static job"),
            (["--- static (2s)", "--- tables", "SKIPPED tables check: no plugin", "ALL PASSED"], "printed SKIPPED"),
            (["--- static (2s)", "--- tables", "STALE: tables.xml", "ALL PASSED"], "did not print that tables.xml is current"),
            (["--- static (2s)", "--- tables", "ok: jmri/layouts/hart/output/tables.xml current (1)", "FAILED"],
             "no ALL PASSED line"),
        )
        for out, text in cases:
            with self.subTest(text=text):
                self.gh.log = log_text(out=out)
                self.assert_runs_g4(text)

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

    def test_a_bad_commit_is_refused_up_front(self) -> None:
        for bad in ("abc", self.sha.upper(), self.sha + "0", "HEAD"):
            with self.subTest(bad=bad):
                rc, out = self.verdict(bad)
                self.assertEqual(2, rc)
                self.assertIn("--commit must be a full 40-character commit sha", out)
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
        with self.assertRaisesRegex(ci_pass.Unreadable, "gh \\(the GitHub CLI\\) is not installed"):
            ci_pass.run_gh(["api", "repos/x"], 5)

    def test_a_failing_gh_names_its_last_error_line(self) -> None:
        gh = self.bin / "gh"
        gh.write_text('#!/bin/sh\necho "noise" >&2\necho "HTTP 404: Not Found" >&2\nexit 1\n', encoding="utf-8")
        gh.chmod(0o755)
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{self.path}"
        with self.assertRaisesRegex(ci_pass.Unreadable, r"gh api repos/x failed \(exit 1\): HTTP 404: Not Found"):
            ci_pass.run_gh(["api", "repos/x"], 5)

    def test_a_hung_gh_times_out(self) -> None:
        gh = self.bin / "gh"
        gh.write_text("#!/bin/sh\nexec sleep 5\n", encoding="utf-8")
        gh.chmod(0o755)
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{self.path}"
        with self.assertRaisesRegex(ci_pass.Unreadable, "took over 1 s"):
            ci_pass.run_gh(["api", "repos/x"], 1)


if __name__ == "__main__":
    unittest.main()
