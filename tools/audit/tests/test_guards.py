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


class JmriOpenAndPrivateName(unittest.TestCase):
    """Table writers stop while PanelPro or CATS is open; the private name stays out of publishing text.

    Checked in this process with the command as data. The running-JMRI check is replaced, so
    the result never depends on what is open, and the name check is replaced by a stand-in
    for a marker word, so no test file holds the real name.
    """
    MARK = "zz-private-marker"

    def guard(self, running: bool):
        guard = load(MAIN_GUARD, "hart_main_guard_names_test")
        guard.jmri_running = lambda: running
        guard.contains_private_name = lambda text: self.MARK in text
        guard.main_checkout = lambda target: False  # CI's clone is a main checkout; tested in test_worktrees
        guard.on_main = lambda target, branched: False  # the checkout's branch must not matter; MainGuard tests the rule
        return guard

    def code(self, command: str, running: bool = True) -> int:
        guard = self.guard(running)
        saved = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": command}, "cwd": str(ROOT)}))
        try:
            with mock_env(CLAUDE_PROJECT_DIR=str(ROOT)), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                return guard.main()
        finally:
            sys.stdin = saved

    def test_writers_blocked_while_open(self) -> None:
        for cmd in ("make tables-pull", "make deploy-all", "make -s deploy-layout", "make ops-pull",
                    "./tools/ops/pull_tables.sh", "./cats/scripts/sync_hart_package.sh --pi",
                    "cd x && ./cats/scripts/sync_hart_package.sh --all",
                    "./tools/hosts/sync_hart_package.sh --pi",
                    "python3 jmri/layouts/hart/scripts/apply_nx_layer.py",
                    "JMRI_LAYOUT=hart python3 jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py",
                    "python3 jmri/layouts/hart/scripts/apply_public_names.py --apply"):
            self.assertEqual(self.code(cmd), 2, cmd)

    def test_writers_pass_when_closed(self) -> None:
        for cmd in ("make tables-pull", "./cats/scripts/sync_hart_package.sh --pi"):
            self.assertEqual(self.code(cmd, running=False), 0, cmd)

    def test_read_only_work_passes_while_open(self) -> None:
        for cmd in ("make panelpro-test", "make deploy-site", "make check", "./tools/check.sh",
                    "python3 jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py --check",
                    "python3 jmri/layouts/hart/scripts/apply_le_sml_facing.py --dry-run",
                    "python3 jmri/layouts/hart/scripts/apply_public_names.py",
                    "./cats/scripts/sync_hart_package.sh --help", "./tools/hosts/sync_hart_package.sh --dry-run --pi",
                    "./cats/scripts/sync_hart_package.sh --stage-only /tmp/x",
                    "./tools/hosts/sync_hart_package.sh --pi --stage-only=/tmp/x",
                    "./cats/scripts/sync_hart_package.sh --dry-run --pi", "cat tools/ops/pull_tables.sh"):
            self.assertEqual(self.code(cmd), 0, cmd)

    def test_process_check_can_be_forced(self) -> None:
        guard = load(MAIN_GUARD, "hart_main_guard_force_test")
        with mock_env(HART_GUARD_JMRI_RUNNING="1"):
            self.assertTrue(guard.jmri_running())
        with mock_env(HART_GUARD_JMRI_RUNNING="0"):
            self.assertFalse(guard.jmri_running())

    def test_private_name_blocked_in_publishing_text(self) -> None:
        m = self.MARK
        for cmd in (f'git commit -m "fix {m} text"', f"git -C . commit --message='{m}'",
                    f'gh pr create --title "{m}" --body ok', f'gh pr edit 3 --body "see {m}"',
                    f'gh issue create --title t --body "{m}"',
                    f'git commit -m "$(cat <<EOF\nfirst line\nmore {m}\nEOF\n)"'):
            self.assertEqual(self.code(cmd, running=False), 2, cmd)

    def test_clean_publishing_text_passes(self) -> None:
        for cmd in ('gh pr create --title t --body "clean"', f"echo {self.MARK}", "gh pr view 3"):
            self.assertEqual(self.code(cmd, running=False), 0, cmd)

    def test_private_name_in_body_file_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad, good = Path(tmp, "bad.md"), Path(tmp, "good.md")
            bad.write_text(f"body {self.MARK}\n")
            good.write_text("body\n")
            self.assertEqual(self.code(f"gh pr create --title t --body-file {bad}", running=False), 2)
            self.assertEqual(self.code(f"git commit -F {bad}", running=False), 2)
            self.assertEqual(self.code(f"gh pr create --title t --body-file {good}", running=False), 0)

    def test_wrapped_and_unlisted_writers_blocked_while_open(self) -> None:
        nx = "jmri/layouts/hart/scripts/apply_nx_layer.py"
        for cmd in (f"env JMRI_LAYOUT=hart python3 {nx}", f"python3 -u {nx}", f"uv run python {nx}",
                    "zsh tools/ops/pull_tables.sh", "bash -c ./tools/ops/pull_tables.sh",
                    "(./tools/ops/pull_tables.sh)", "cd jmri && python3 scripts/apply_blocks_to_panel.py",
                    # no list entry: found by reading the script
                    "python3 jmri/scripts/polish_hart_cp_labels.py",
                    "python3 jmri/layouts/hart/scripts/build_hart_signal_heads.py",
                    # flags these scripts do not define do not make them safe
                    "python3 jmri/layouts/hart/scripts/annotate_mqtt_sensors_and_dispatcher.py --check",
                    "python3 jmri/layouts/hart/scripts/refresh_bean_comments.py --dry-run"):
            self.assertEqual(self.code(cmd), 2, cmd)

    def test_hartlib_writers_blocked_readers_pass_while_open(self) -> None:
        # A script on hartlib may name neither tables.xml nor a write call.
        writers = {
            "w1.py": "from hartlib import tables\ndoc = tables.load()\ndoc.save()\n",
            "w2.py": "from hartlib.tables import load\ndoc = load()\ndoc.save()\n",
            "w3.py": "from hartlib import (\n    paths,\n    tables,\n)\ntables.load().save()\n",
            "w4.py": "import hartlib.tables as t\nt.load().save()\n",
        }
        readers = {
            "r1.py": "from hartlib import paths, tables\nroot = tables.read(paths.TABLES_XML)\n",
            "r2.py": "from hartlib import paths\nimport openpyxl\nwb = openpyxl.Workbook()\nwb.save(paths.REPO_ROOT / 'x.xlsx')\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in {**writers, **readers}.items():
                Path(tmp, name).write_text(text)
            for name in writers:
                self.assertEqual(self.code(f"python3 {Path(tmp, name)}"), 2, name)
                self.assertEqual(self.code(f"python3 {Path(tmp, name)}", running=False), 0, name)
            for name in readers:
                self.assertEqual(self.code(f"python3 {Path(tmp, name)}"), 0, name)

    def test_openpyxl_save_beside_a_tables_mention_passes_while_open(self) -> None:
        # Reads tables.xml, saves a workbook: not a table writer (as before hartlib).
        self.assertEqual(self.code("python3 docs/wiring/lcos/build_lcos_signal_manager_plan.py"), 0)

    def test_readers_and_launchers_pass_while_open(self) -> None:
        for cmd in ("python3 jmri/scripts/check_hart_phase02.py", "git grep pull_tables.sh",
                    "python3 jmri/layouts/hart/scripts/export_track_lengths.py",
                    "./cats/scripts/launch_cats.sh", "python3 -m unittest discover -s tools/audit/tests",
                    "python3 www/scripts/prepare_github_pages.py /tmp/dist",
                    "python3 www/scripts/check_portal_build.py"):
            self.assertEqual(self.code(cmd), 0, cmd)

    def test_process_pattern_covers_jmri5_decoderpro(self) -> None:
        guard = load(MAIN_GUARD, "hart_main_guard_process_test")
        for line in ("java -cp x apps.gui3.dp3.DecoderPro3", "java -cp x apps.PanelPro.PanelPro",
                     "java -jar cats.jar cats.apps.Crandic"):
            self.assertRegex(line, guard.PROCESS)

    def test_more_publishing_text_checked(self) -> None:
        m = self.MARK
        for cmd in (f'gh pr comment 3 --body "{m}"', f'gh issue comment 3 --body "{m}"',
                    f'gh issue edit 3 --body "{m}"', f'gh pr review 3 --comment --body "{m}"',
                    f'gh release create v1 --notes "{m}"', f'git tag -a v1 -m "{m}"'):
            self.assertEqual(self.code(cmd, running=False), 2, cmd)

    def test_attached_body_file_forms_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "bad.md")
            bad.write_text(f"body {self.MARK}\n")
            for cmd in (f"gh pr create --title t --body-file={bad}", f"git commit -F{bad}",
                        f"git commit --file={bad}"):
                self.assertEqual(self.code(cmd, running=False), 2, cmd)

    def test_name_in_an_earlier_part_does_not_block_a_clean_commit(self) -> None:
        cmd = f"git grep -n {self.MARK} ; git commit -m 'remove the leaked name'"
        self.assertEqual(self.code(cmd, running=False), 0)

    def test_publishing_blocked_when_name_check_cannot_load(self) -> None:
        guard = load(MAIN_GUARD, "hart_main_guard_missing_check_test")
        guard.jmri_running = lambda: False
        guard.NAME_CHECK = str(ROOT / "no" / "such" / "private_name.py")
        saved = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": "gh pr create --title t --body ok"},
                                            "cwd": str(ROOT)}))
        try:
            with mock_env(CLAUDE_PROJECT_DIR=str(ROOT)), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(guard.main(), 2)
        finally:
            sys.stdin = saved

    def test_after_edit_checks_match_check_sh(self) -> None:
        after = load(ROOT / ".claude/hooks/check_after_edit.py", "hart_check_after_edit_test")
        check_sh = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
        for name, argv in after.CHECKS:
            self.assertIn(f"run {name} " + " ".join(argv), check_sh, name)

    def test_real_name_check_loads_and_passes_clean_text(self) -> None:
        guard = load(MAIN_GUARD, "hart_main_guard_real_name_test")
        self.assertFalse(guard.contains_private_name("a clean commit message about masts"))


if __name__ == "__main__":
    unittest.main()
