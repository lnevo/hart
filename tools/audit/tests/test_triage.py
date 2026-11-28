"""tools/agent/triage.py: verdicts from a stub `claude` on PATH (confirmed, wrong, error, timeout), the jobs limit,
the session-cap wait and its deadline, the ancestor-free count, the verifier worktree, the SHA check, the Makefile
quoting, the brief and the whole run. No real verifier starts."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "agent"))
import triage  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
HEAD = triage.Head(branch="agent/claude/topic", sha=SHA)

# The stub picks its answer from a word in the prompt's summary.
STUB_CLAUDE = r'''#!/usr/bin/env python3
import json, sys, time
import os, subprocess
prompt = sys.argv[sys.argv.index("-p") + 1]
if "STUB-SLEEP" in prompt:
    time.sleep(30)
if "STUB-ORPHAN" in prompt:  # a child that keeps the pipes open after the parent is killed
    subprocess.Popen(["sleep", "30"])
    time.sleep(30)
if "STUB-CWD" in prompt:
    print(json.dumps({"is_error": False, "result": "WRONG\ncwd " + os.getcwd(), "num_turns": 1}))
    sys.exit(0)
if "STUB-CRASH" in prompt:
    print("boom", file=sys.stderr)
    sys.exit(3)
if "STUB-ERROR" in prompt:
    print(json.dumps({"is_error": True, "subtype": "error_max_budget_usd", "result": "", "total_cost_usd": 0.75}))
    sys.exit(1)
word = "CONFIRMED" if "STUB-CONFIRM" in prompt else "PLAUSIBLE" if "STUB-PLAUSIBLE" in prompt else "WRONG"
text = f"**{word}**\nlib.py:12 reads the guard.\nFix: check x before y."
print(json.dumps({"is_error": False, "result": text, "total_cost_usd": 0.12, "num_turns": 4, "duration_ms": 7000}))
'''
STUB_GH = f'''#!/bin/sh
echo '{{"headRefName": "agent/claude/topic", "headRefOid": "{SHA}"}}'
'''
STUB_GIT = f'''#!/bin/sh
case "$1" in
  rev-parse) echo {SHA} ;;
  cat-file) [ -n "$STUB_GIT_NO_SHA" ] && exit 1 ;;
  worktree) [ "$2" = add ] && mkdir -p "$4" && echo "$4" >> "$STUB_GIT_LOG" ;;
esac
exit 0
'''


def finding(summary: str, file: str = "tools/x.py", line: int = 3) -> triage.Finding:
    return triage.Finding(file=file, line=line, summary=summary, failure_scenario="when y", severity="high")


class StubPath(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        bin_dir = Path(self.tmp.name, "bin")
        bin_dir.mkdir()
        for name, body in (("claude", STUB_CLAUDE), ("gh", STUB_GH), ("git", STUB_GIT)):
            path = bin_dir / name
            path.write_text(body)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        saved = os.environ.copy()

        def restore() -> None:
            os.environ.clear()
            os.environ.update(saved)

        self.addCleanup(restore)
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


class Verdicts(StubPath):
    def test_confirmed_wrong_and_plausible(self) -> None:
        for word, verdict in (("STUB-CONFIRM", "CONFIRMED"), ("STUB-WRONG", "WRONG"),
                              ("STUB-PLAUSIBLE", "PLAUSIBLE")):
            with self.subTest(verdict=verdict):
                result = triage.verify(finding(word), HEAD, timeout=20)
                self.assertEqual(result.verdict, verdict)
                self.assertEqual(result.cost_usd, 0.12)
                self.assertEqual(result.duration_s, 7.0)
                self.assertIn("lib.py:12", triage.evidence(result))

    def test_error_result_is_not_verified_with_the_reason(self) -> None:
        result = triage.verify(finding("STUB-ERROR"), HEAD, timeout=20)
        self.assertEqual(result.verdict, triage.NOT_VERIFIED)
        self.assertIn("error_max_budget_usd", result.reason)
        self.assertEqual(result.cost_usd, 0.75)

    def test_crash_without_json_is_not_verified(self) -> None:
        result = triage.verify(finding("STUB-CRASH"), HEAD, timeout=20)
        self.assertEqual(result.verdict, triage.NOT_VERIFIED)
        self.assertIn("exit 3", result.reason)
        self.assertIn("boom", result.reason)

    def test_timeout_kills_the_children_too(self) -> None:
        began = time.monotonic()
        result = triage.verify(finding("STUB-ORPHAN"), HEAD, timeout=1)
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(result.verdict, triage.NOT_VERIFIED)
        self.assertIn("timed out after 1 s", result.reason)

    def test_the_verifier_runs_in_the_tree(self) -> None:
        tree = Path(self.tmp.name, "tree")
        tree.mkdir()
        result = triage.verify(finding("STUB-CWD"), HEAD, timeout=20, tree=tree)
        self.assertEqual(Path(result.text.split("cwd ", 1)[1]).resolve(), tree.resolve())

    def test_timeout_kills_the_run(self) -> None:
        began = time.monotonic()
        result = triage.verify(finding("STUB-SLEEP"), HEAD, timeout=1)
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(result.verdict, triage.NOT_VERIFIED)
        self.assertIn("timed out after 1 s", result.reason)

    def test_the_prompt_names_the_branch_the_sha_and_the_answer_form(self) -> None:
        prompt = triage.prompt_for(finding("summary text"), HEAD)
        for part in (SHA, "The working tree is the PR's head: branch agent/claude/topic", "summary text", "when y",
                     "CONFIRMED, PLAUSIBLE or WRONG on the first line"):
            self.assertIn(part, prompt)
        self.assertNotIn("git show", prompt)
        argv = triage.claude_command(prompt)
        tools = argv[argv.index("--allowedTools") + 1:argv.index("--max-turns")]
        self.assertEqual(tools, ["Read", "Grep", "Glob"])  # no Bash: finding text must not reach a shell
        self.assertEqual(argv[argv.index("--agent") + 1], "finding-verifier")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "12")
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "0.75")

    def test_a_first_line_without_a_verdict_is_not_verified(self) -> None:
        run = triage.Run(code=0, out=json.dumps({"result": "I looked.\nCONFIRMED later"}), err="")
        self.assertEqual(triage.parse_verdict(finding("x"), run, 1.0, 5).reason, "no verdict on the first line")

    def test_the_verdict_must_open_the_first_line(self) -> None:
        def verdict(first: str) -> str:
            run = triage.Run(code=0, out=json.dumps({"result": first + "\nevidence"}), err="")
            return triage.parse_verdict(finding("x"), run, 1.0, 5).verdict

        for first, want in (("**CONFIRMED**", "CONFIRMED"), ("WRONG: the guard holds", "WRONG"),
                            ("## PLAUSIBLE", "PLAUSIBLE"), ("Not CONFIRMED yet", triage.NOT_VERIFIED),
                            ("The finding is WRONG", triage.NOT_VERIFIED), ("CONFIRMEDISH", triage.NOT_VERIFIED)):
            with self.subTest(first=first):
                self.assertEqual(verdict(first), want)


class Concurrency(unittest.TestCase):
    def test_at_most_jobs_run_at_once(self) -> None:
        lock, live, peak = threading.Lock(), [0], [0]

        def work(f: triage.Finding) -> triage.Result:
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.05)
            with lock:
                live[0] -= 1
            return triage.Result(f, "WRONG", text="WRONG\nno")

        cap = triage.SessionCap(10, count=lambda: 0, settle=0)
        with contextlib.redirect_stdout(io.StringIO()):
            results = triage.run_all([finding(f"f{i}") for i in range(9)], work, jobs=3, cap=cap)
        self.assertEqual(peak[0], 3)
        self.assertEqual([r.finding.summary for r in results], [f"f{i}" for i in range(9)])

    def test_waits_while_at_the_session_cap(self) -> None:
        counts, slept = iter([10, 11, 9]), list[float]()
        cap = triage.SessionCap(10, count=lambda: next(counts), sleep=slept.append, poll=15, settle=0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            triage.run_all([finding("only")], lambda f: triage.Result(f, "WRONG"), jobs=3, cap=cap)
        self.assertEqual(slept, [15, 15])
        self.assertIn("10 Claude processes running, cap 10; finding 1 (tools/x.py:3) waits", out.getvalue())

    def test_a_wait_past_the_deadline_is_not_verified(self) -> None:
        clock, slept = [0.0], list[float]()

        def sleep(s: float) -> None:
            slept.append(s)
            clock[0] += s

        cap = triage.SessionCap(10, count=lambda: 12, sleep=sleep, poll=15, settle=0, max_wait=60,
                                clock=lambda: clock[0])
        ran: list[triage.Finding] = []
        with contextlib.redirect_stdout(io.StringIO()):
            results = triage.run_all([finding("a"), finding("b")], lambda f: ran.append(f) or triage.Result(f, "WRONG"),
                                     jobs=1, cap=cap)
        self.assertEqual(ran, [])
        self.assertEqual([r.verdict for r in results], [triage.NOT_VERIFIED] * 2)
        self.assertEqual(results[0].reason, "waited 60 s at the session cap of 10 Claude processes")
        self.assertEqual(slept, [15] * 8)  # 4 polls each, then the deadline

    def test_the_count_leaves_out_this_run_and_its_ancestors(self) -> None:
        ps = "\n".join(("    1     0 /sbin/launchd", "  100     1 /usr/local/bin/claude", "  200   100 /bin/zsh",
                        "  300   200 make", "  400   300 python3", "  500   400 claude", "  600     1 claude",
                        "  700   600 node", "junk line"))
        self.assertEqual(triage.count_claude(ps, 400), 2)  # 500 (a verifier) and 600; 100 started this run
        self.assertEqual(triage.count_claude(ps, 999), 3)  # an unknown pid leaves all three in

    def test_a_worker_that_raises_is_not_verified(self) -> None:
        def work(f: triage.Finding) -> triage.Result:
            raise RuntimeError("bad")

        cap = triage.SessionCap(10, count=lambda: 0, settle=0)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            results = triage.run_all([finding("x")], work, jobs=1, cap=cap)
        self.assertEqual(results[0].verdict, triage.NOT_VERIFIED)


class Brief(unittest.TestCase):
    def test_sections_and_cost(self) -> None:
        results = [
            triage.Result(finding("real bug", "a.py", 5), "CONFIRMED", text="CONFIRMED\na.py:5 x is None.\nFix: guard.",
                          cost_usd=0.1),
            triage.Result(finding("maybe", "b.py", 6), "PLAUSIBLE", text="PLAUSIBLE\nb.py:6 depends on input.",
                          cost_usd=0.2),
            triage.Result(finding("not real", "c.py", 7), "WRONG", text="WRONG\nc.py:2 guards it.\nmore", cost_usd=0.3),
            triage.Result(finding("lost", "d.py", 8), triage.NOT_VERIFIED, reason="timed out after 300 s"),
        ]
        text = triage.brief(12, HEAD, results)
        confirmed = text.split("## Confirmed: fix these")[1].split("## Plausible")[0]
        self.assertIn("### a.py:5: real bug", confirmed)
        self.assertIn("Fix: guard.", confirmed)
        plausible = text.split("## Plausible: check against the code")[1].split("## Wrong")[0]
        self.assertIn("### b.py:6: maybe", plausible)
        self.assertIn("Check against the code.", plausible)
        self.assertIn("- c.py:7: not real (c.py:2 guards it.)", text)
        self.assertIn("## Not verified\n\n- d.py:8: lost (timed out after 300 s)", text)
        self.assertIn("1 confirmed, 1 plausible, 1 wrong, 1 not verified", text)
        self.assertIn("Total cost: $0.60.", text)
        self.assertIn(SHA, text)


class Tree(unittest.TestCase):
    def setUp(self) -> None:
        if not shutil.which("git"):
            self.skipTest("no git")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name, "repo")
        self.repo.mkdir()
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        for argv in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                                      "-m", "one"]):
            subprocess.run(["git", *argv], cwd=self.repo, check=True, env=env, capture_output=True)
        (self.repo / "a.txt").write_text("head\n")
        subprocess.run(["git", "add", "a.txt"], cwd=self.repo, check=True, env=env)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "two"],
                       cwd=self.repo, check=True, env=env)
        self.sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, check=True, capture_output=True,
                                  text=True).stdout.strip()
        (self.repo / "a.txt").write_text("working copy\n")

    def worktrees(self) -> str:
        return subprocess.run(["git", "worktree", "list"], cwd=self.repo, capture_output=True, text=True).stdout

    def test_the_tree_is_the_sha_and_is_removed_after(self) -> None:
        with triage.verifier_tree(self.sha, self.repo) as tree:
            self.assertEqual((tree / "a.txt").read_text(), "head\n")
            self.assertEqual(len(self.worktrees().strip().splitlines()), 2)
            self.assertIn("(detached HEAD)", self.worktrees())
        self.assertFalse(tree.parent.exists())
        self.assertEqual(len(self.worktrees().strip().splitlines()), 1)

    def test_the_tree_is_removed_when_the_run_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            with triage.verifier_tree(self.sha, self.repo) as tree:
                raise RuntimeError("verifier crash")
        self.assertFalse(tree.parent.exists())
        self.assertEqual(len(self.worktrees().strip().splitlines()), 1)

    def test_an_unknown_sha_is_a_triage_error(self) -> None:
        with self.assertRaises(triage.TriageError):
            with triage.verifier_tree("f" * 40, self.repo):
                pass

    def test_fetch_refuses_a_sha_that_is_not_here(self) -> None:
        bare = Path(self.tmp.name, "origin.git")
        subprocess.run(["git", "clone", "-q", "--bare", str(self.repo), str(bare)], check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=self.repo, check=True)
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=self.repo, capture_output=True,
                                text=True).stdout.strip()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            triage.fetch(triage.Head(branch, self.sha), self.repo)
        self.assertEqual(out.getvalue(), "")
        with self.assertRaises(triage.TriageError) as raised:
            triage.fetch(triage.Head(branch, "e" * 40), self.repo)
        self.assertIn("is not a commit here", str(raised.exception))


class Makefile(unittest.TestCase):
    def test_values_with_quotes_reach_triage_whole(self) -> None:
        if not shutil.which("make"):
            self.skipTest("no make")
        values = {"PR": "12", "FINDINGS": "/tmp/it's here.json", "OUT": "/tmp/o'ut $(shell echo EXPANDED)"}
        done = subprocess.run(["make", "-n", "-s", "triage", *(f"{k}={v}" for k, v in values.items())], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("EXPANDED", done.stderr)
        line = next(x for x in done.stdout.splitlines() if "triage.py" in x)
        argv = shlex.split(line)
        self.assertEqual(argv[argv.index("tools/agent/triage.py") + 1], "12")
        self.assertEqual(argv[argv.index("--findings") + 1], values["FINDINGS"])
        self.assertEqual(argv[argv.index("--out") + 1], values["OUT"])


class WholeRun(StubPath):
    def test_main_writes_one_json_per_finding_the_summary_and_the_brief(self) -> None:
        os.environ["HART_SESSION_CAP"] = "100000"
        log = Path(self.tmp.name, "git.log")
        os.environ["STUB_GIT_LOG"] = str(log)
        findings = Path(self.tmp.name, "findings.json")
        findings.write_text(json.dumps([
            {"file": "a.py", "line": 1, "summary": "STUB-CONFIRM one", "failure_scenario": "s", "severity": "high"},
            {"file": "b.py", "line": 2, "summary": "STUB-WRONG two"},
            {"file": "c.py", "line": 3, "summary": "STUB-ERROR three"},
        ]))
        out_dir = Path(self.tmp.name, "out")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = triage.main(["12", "--findings", str(findings), "--out", str(out_dir), "--timeout", "20"])
        self.assertEqual(code, 1)  # one not verified
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()),
                         ["finding-01.json", "finding-02.json", "finding-03.json", "fix-brief.md", "summary.json"])
        one = json.loads((out_dir / "finding-01.json").read_text())
        self.assertEqual((one["verdict"], one["finding"]["file"], one["cost_usd"]), ("CONFIRMED", "a.py", 0.12))
        summary = json.loads((out_dir / "summary.json").read_text())
        self.assertEqual(summary["sha"], SHA)
        self.assertEqual(summary["counts"], {"CONFIRMED": 1, "PLAUSIBLE": 0, "WRONG": 1, "NOT VERIFIED": 1})
        self.assertIn(str(out_dir / "fix-brief.md"), printed.getvalue())
        self.assertIn("1 confirmed, 0 plausible, 1 wrong, 1 not verified", printed.getvalue())
        tree = Path(log.read_text().strip())
        self.assertTrue(tree.name == "tree" and not tree.parent.exists())  # made, then removed

    def test_a_head_that_is_not_here_is_a_bad_call(self) -> None:
        os.environ["STUB_GIT_NO_SHA"] = "1"
        findings = Path(self.tmp.name, "findings.json")
        findings.write_text(json.dumps([{"file": "a.py", "summary": "STUB-CONFIRM"}]))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(triage.main(["12", "--findings", str(findings)]), 2)
        self.assertIn(f"the PR's head {SHA} is not a commit here", err.getvalue())

    def test_bad_findings_file_is_a_bad_call(self) -> None:
        findings = Path(self.tmp.name, "findings.json")
        findings.write_text(json.dumps({"file": "a.py"}))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(triage.main(["12", "--findings", str(findings)]), 2)
        self.assertIn("must be a JSON list", err.getvalue())


if __name__ == "__main__":
    unittest.main()
