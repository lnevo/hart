"""tools/agent/triage.py: verdicts from a stub `claude` on PATH (confirmed, wrong, error, timeout), the jobs limit,
the session-cap wait, the brief and the whole run. No real verifier starts."""
from __future__ import annotations

import contextlib
import io
import json
import os
import stat
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
prompt = sys.argv[sys.argv.index("-p") + 1]
if "STUB-SLEEP" in prompt:
    time.sleep(30)
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
[ "$1" = rev-parse ] && echo {SHA}
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
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
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

    def test_timeout_kills_the_run(self) -> None:
        began = time.monotonic()
        result = triage.verify(finding("STUB-SLEEP"), HEAD, timeout=1)
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(result.verdict, triage.NOT_VERIFIED)
        self.assertIn("timed out after 1 s", result.reason)

    def test_the_prompt_names_the_branch_the_sha_and_the_answer_form(self) -> None:
        prompt = triage.prompt_for(finding("summary text"), HEAD)
        for part in (SHA, "git show origin/agent/claude/topic:<path>", "summary text", "when y",
                     "CONFIRMED, PLAUSIBLE or WRONG on the first line"):
            self.assertIn(part, prompt)
        argv = triage.claude_command(prompt)
        self.assertEqual(argv[argv.index("--agent") + 1], "finding-verifier")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "12")
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "0.75")

    def test_a_first_line_without_a_verdict_is_not_verified(self) -> None:
        run = triage.Run(code=0, out=json.dumps({"result": "I looked.\nCONFIRMED later"}), err="")
        self.assertEqual(triage.parse_verdict(finding("x"), run, 1.0, 5).reason, "no verdict on the first line")


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
        counts, slept = iter([10, 11, 9]), []
        cap = triage.SessionCap(10, count=lambda: next(counts), sleep=slept.append, poll=15, settle=0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            triage.run_all([finding("only")], lambda f: triage.Result(f, "WRONG"), jobs=3, cap=cap)
        self.assertEqual(slept, [15, 15])
        self.assertIn("10 Claude processes running, cap 10; finding 1 (tools/x.py:3) waits", out.getvalue())

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


class WholeRun(StubPath):
    def test_main_writes_one_json_per_finding_the_summary_and_the_brief(self) -> None:
        os.environ["HART_SESSION_CAP"] = "100000"
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

    def test_bad_findings_file_is_a_bad_call(self) -> None:
        findings = Path(self.tmp.name, "findings.json")
        findings.write_text(json.dumps({"file": "a.py"}))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(triage.main(["12", "--findings", str(findings)]), 2)
        self.assertIn("must be a JSON list", err.getvalue())


if __name__ == "__main__":
    unittest.main()
