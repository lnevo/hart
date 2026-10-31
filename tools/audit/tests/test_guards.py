"""The Claude Code hooks allow and stop the commands they promise to."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN_GUARD = ROOT / ".claude/hooks/main_guard.py"
SUBAGENT_GUARD = ROOT / ".claude/hooks/subagent_guard.py"


def run(hook: Path, command: str, cwd: str):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=cwd)
    payload = json.dumps({"tool_input": {"command": command}, "cwd": cwd})
    return subprocess.run([sys.executable, str(hook)], input=payload, capture_output=True, text=True, env=env)


class MainGuard(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = os.path.realpath(tmp.name)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)

    def branch(self, name: str) -> None:
        subprocess.run(["git", "-C", self.repo, "checkout", "-q", "-b", name], check=True)

    def code(self, command: str) -> int:
        return run(MAIN_GUARD, command, self.repo).returncode

    def test_push_to_main_is_blocked(self) -> None:
        self.assertEqual(self.code("git push origin main"), 2)
        self.assertEqual(self.code("git push origin HEAD:main"), 2)
        self.assertEqual(self.code("git push -u origin HEAD"), 2)
        self.assertEqual(self.code("git status && git push"), 2)

    def test_force_push_is_blocked_on_any_branch(self) -> None:
        self.branch("agent/claude/x")
        self.assertEqual(self.code("git push --force origin HEAD"), 2)
        self.assertEqual(self.code("git push --force-with-lease"), 2)
        self.assertEqual(self.code("git push -fu origin HEAD"), 2)
        self.assertEqual(self.code("git push origin +HEAD"), 2)

    def test_agent_branch_push_passes(self) -> None:
        self.branch("agent/claude/x")
        self.assertEqual(self.code("git push -u origin HEAD"), 0)
        self.assertEqual(self.code("git push origin agent/claude/x"), 0)

    def test_searching_for_a_push_passes(self) -> None:
        self.assertEqual(self.code("grep -rn 'git push origin main' wiki"), 0)

    def test_other_repo_keeps_its_own_rules(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            subprocess.run(["git", "init", "-q", "-b", "main", other], check=True)
            self.assertEqual(self.code(f"git -C {other} push origin main"), 0)
            self.assertEqual(self.code(f"cd {other} && git push origin main"), 0)

    def test_publish_and_merge_ask(self) -> None:
        for command in ("mosquitto_pub -h x -t track/cmd/1 -m THROWN", "gh pr merge 3 --merge"):
            done = run(MAIN_GUARD, command, self.repo)
            self.assertEqual(done.returncode, 0)
            decision = json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"]
            self.assertEqual(decision, "ask")

    def test_other_publish_passes_quietly(self) -> None:
        self.assertEqual(run(MAIN_GUARD, "mosquitto_pub -t lab/test -m 1", self.repo).stdout, "")


class SubagentGuard(unittest.TestCase):
    def test_deploys_are_blocked_through_make(self) -> None:
        self.assertEqual(run(SUBAGENT_GUARD, "make deploy-site", str(ROOT)).returncode, 2)
        self.assertEqual(run(SUBAGENT_GUARD, "make check", str(ROOT)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
