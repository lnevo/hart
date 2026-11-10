"""The Claude Code hooks, and the Cursor hook that reuses them, allow and stop the commands they promise to.

The guards only read command text; they never run it. These tests keep it that way:
the publish cases are checked in this process with the command as plain data, and
every hook started as a process gets a PATH holding only git, so no MQTT client
could be found even if something tried to run one.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN_GUARD = ROOT / ".claude/hooks/main_guard.py"
SUBAGENT_GUARD = ROOT / ".claude/hooks/subagent_guard.py"
CURSOR_GUARD = ROOT / ".cursor/hooks/main_guard.py"

# Command text for the publish rule. Never executed: a reserved .invalid host and a TEST topic.
PUBLISH_CMD = " ".join(["mosquitto_pub", "-h", "example.invalid", "-t", "track/cmd/TEST", "-m", "NONE"])
OTHER_PUBLISH_CMD = " ".join(["mosquitto_pub", "-h", "example.invalid", "-t", "lab/test", "-m", "NONE"])

_BIN = tempfile.TemporaryDirectory()
os.symlink(shutil.which("git"), os.path.join(_BIN.name, "git"))
GIT_ONLY_PATH = _BIN.name


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(hook: Path, command: str, cwd: str):
    """Start a hook as Claude Code does, with no MQTT client reachable on PATH."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=cwd, PATH=GIT_ONLY_PATH)
    payload = json.dumps({"tool_input": {"command": command}, "cwd": cwd})
    return subprocess.run([sys.executable, str(hook)], input=payload, capture_output=True, text=True, env=env)


def in_process(command: str, cwd: str) -> tuple[int, str]:
    """Run the main guard in this process on `command` as data; returns (exit code, stdout)."""
    guard = load(MAIN_GUARD, "hart_main_guard_test")
    out = io.StringIO()
    saved = sys.stdin
    sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": command}, "cwd": cwd}))
    try:
        with mock_env(CLAUDE_PROJECT_DIR=cwd), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = guard.main()
    finally:
        sys.stdin = saved
    return code, out.getvalue()


@contextlib.contextmanager
def mock_env(**values):
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def git_repo(test: unittest.TestCase) -> str:
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    repo = os.path.realpath(tmp.name)
    subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
    return repo


class MainGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = git_repo(self)

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

    def test_commit_on_main_is_blocked(self) -> None:
        self.assertEqual(self.code("git commit -m x"), 2)
        self.assertEqual(self.code("git add -A && git commit -q -m x"), 2)

    def test_commit_on_agent_branch_passes(self) -> None:
        self.branch("agent/claude/x")
        self.assertEqual(self.code("git commit -m x"), 0)

    def test_branching_first_in_one_command_passes(self) -> None:
        self.assertEqual(self.code("git checkout -b agent/claude/x && git commit -m x"), 0)
        self.assertEqual(self.code("git checkout -q -b agent/claude/x && git push -u origin HEAD"), 0)
        self.assertEqual(self.code("git switch -c agent/claude/x && git push -u origin HEAD"), 0)

    def test_admin_merge_is_blocked(self) -> None:
        self.assertEqual(self.code("gh pr merge 3 --merge --admin"), 2)

    def test_searching_for_a_push_passes(self) -> None:
        self.assertEqual(self.code("grep -rn 'git push origin main' wiki"), 0)

    def test_other_repo_keeps_its_own_rules(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            subprocess.run(["git", "init", "-q", "-b", "main", other], check=True)
            self.assertEqual(self.code(f"git -C {other} push origin main"), 0)
            self.assertEqual(self.code(f"cd {other} && git push origin main"), 0)
            self.assertEqual(self.code(f"git -C {other} commit -m x"), 0)

    def test_publish_asks(self) -> None:
        code, out = in_process(PUBLISH_CMD, self.repo)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_plain_merge_passes_quietly(self) -> None:
        done = run(MAIN_GUARD, "gh pr merge 3 --merge", self.repo)
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_other_publish_passes_quietly(self) -> None:
        self.assertEqual(in_process(OTHER_PUBLISH_CMD, self.repo), (0, ""))


class CursorGuard(unittest.TestCase):
    """Cursor sends {command, cwd, workspace_roots} and reads {permission, ...} back."""

    def setUp(self) -> None:
        self.repo = git_repo(self)
        self.hook = load(CURSOR_GUARD, "hart_cursor_guard_test")

    def permission(self, command: str) -> str:
        data = {"command": command, "cwd": self.repo, "workspace_roots": [self.repo],
                "hook_event_name": "beforeShellExecution"}
        with mock_env(CURSOR_PROJECT_DIR=self.repo):
            return self.hook.decide(data)["permission"]

    def test_hooks_json_runs_the_guard(self) -> None:
        hooks = json.loads((ROOT / ".cursor/hooks.json").read_text())
        commands = [h["command"] for h in hooks["hooks"]["beforeShellExecution"]]
        self.assertIn("python3 .cursor/hooks/main_guard.py", commands)

    def test_main_rules_deny(self) -> None:
        self.assertEqual(self.permission("git commit -m x"), "deny")
        self.assertEqual(self.permission("git push origin main"), "deny")
        self.assertEqual(self.permission("gh pr merge 3 --admin"), "deny")

    def test_publish_asks(self) -> None:
        self.assertEqual(self.permission(PUBLISH_CMD), "ask")

    def test_ordinary_commands_allow(self) -> None:
        self.assertEqual(self.permission("git status"), "allow")
        self.assertEqual(self.permission("git checkout -b agent/cursor/x && git commit -m x"), "allow")

    def test_reply_is_cursor_json(self) -> None:
        """The hook as Cursor starts it: JSON in, one JSON reply out, exit 0."""
        payload = json.dumps({"command": "git commit -m x", "cwd": self.repo, "workspace_roots": [self.repo]})
        done = subprocess.run([sys.executable, str(CURSOR_GUARD)], input=payload, capture_output=True, text=True,
                              env=dict(os.environ, CURSOR_PROJECT_DIR=self.repo, PATH=GIT_ONLY_PATH))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["permission"], "deny")


class SubagentGuard(unittest.TestCase):
    def test_deploys_are_blocked_through_make(self) -> None:
        self.assertEqual(run(SUBAGENT_GUARD, "make deploy-site", str(ROOT)).returncode, 2)
        self.assertEqual(run(SUBAGENT_GUARD, "make check", str(ROOT)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
