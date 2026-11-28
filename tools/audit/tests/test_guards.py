"""The Claude Code hooks, and the Cursor hook that reuses them, allow and stop the commands they promise to.

The guards only read command text; they never run it. These tests keep it that way:
the publish cases are checked in this process with the command as plain data, and
every hook started as a process gets a PATH holding only git, so no MQTT client
could be found even if something tried to run one.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guards_case import GIT_ONLY_PATH, ROOT, load, mock_env, run  # noqa: E402

MAIN_GUARD = ROOT / ".claude/hooks/main_guard.py"
SUBAGENT_GUARD = ROOT / ".claude/hooks/subagent_guard.py"
CURSOR_GUARD = ROOT / ".cursor/hooks/main_guard.py"


# Command text for the publish rule. Never executed: a reserved .invalid host and a TEST topic.
PUBLISH_CMD = " ".join(["mosquitto_pub", "-h", "example.invalid", "-t", "track/cmd/TEST", "-m", "NONE"])
OTHER_PUBLISH_CMD = " ".join(["mosquitto_pub", "-h", "example.invalid", "-t", "lab/test", "-m", "NONE"])


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
    def test_make_ready_is_the_one_way_to_ship(self) -> None:
        for command in ('make ready FILES="a.py b.md" MSG="fix(x): git commit wording"',
                        "make ready FILES=a.py MSG=m TITLE=t BODY_FILE=/tmp/body.md",
                        "make ready MSG='fix: deploy-layout docs' 2>&1",
                        "python3 tools/agent/ready.py --files a.py --msg 'fix: git push text'",
                        "python3 ./tools/agent/ready.py --help"):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 0)
        for command in ("git commit -m x", "git add a.py", "git push -u origin HEAD", "gh pr create --fill",
                        "gh pr merge 5", "gh pr merge 5 --merge --auto", "make deploy-layout",
                        "make ready && git push origin main", "make ready; gh pr merge 5",
                        "make ready deploy-layout", "make ready redeploy", "make -C /tmp ready",
                        "make ready CMD=x", "make ready MAKEFLAGS=-n", "HART_READY_ATTRIBUTION=/tmp/x make ready",
                        "env FOO=1 make ready", "make ready ready", "python3 tools/agent/ready.py --force",
                        "git push --force origin HEAD", "git push origin HEAD:main",
                        "./tools/hosts/sync_hart_package.sh --pi --win"):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 2)

    def test_make_ready_values_that_make_would_expand_are_blocked(self) -> None:
        for command in ("make ready FILES=x MSG='$(shell git push --force origin HEAD:main)'",
                        'make ready FILES=x MSG="$(shell ssh pi true)"', "make ready FILES=x TITLE='${HOME}'",
                        "make ready FILES=x MSG='a' BODY='`id`'"):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 2)
        for command in ("make ready FILES=x MSG='fix: costs $5' BRANCH=agent/claude/topic",):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 0)

    def test_the_makefile_does_not_expand_ready_values(self) -> None:
        out = subprocess.run(["make", "-n", "ready", "FILES=x", "MSG=$(shell echo EXPANDED >&2)"], cwd=ROOT,
                             capture_output=True, text=True, timeout=60)
        self.assertNotIn("EXPANDED", out.stderr)
        self.assertIn("--msg '$(shell echo EXPANDED >&2)'", out.stdout)

    def test_deploys_are_blocked_through_make(self) -> None:
        self.assertEqual(run(SUBAGENT_GUARD, "make deploy-site", str(ROOT)).returncode, 2)
        self.assertEqual(run(SUBAGENT_GUARD, "make check", str(ROOT)).returncode, 0)

    def test_make_land_is_blocked(self) -> None:  # it merges a PR
        for command in ("make land PR=12", "make land PR=12 SQUASH=1", "make -s land PR=12"):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 2)
        self.assertEqual(run(SUBAGENT_GUARD, "grep -n land Makefile", str(ROOT)).returncode, 0)

    def test_land_py_run_directly_is_blocked(self) -> None:  # make land's script, called without make
        for command in ("python3 tools/agent/land.py 12", "tools/agent/land.py 12", "./tools/agent/land.py --pr 12",
                        "env python3 tools/agent/land.py 12", "cd tools/agent && python3 land.py 12"):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 2)
        for command in ("grep -n merge tools/agent/land.py", "python3 -m unittest tools/audit/tests/test_land.py"):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 0)

    def test_pulls_from_the_pi_are_blocked(self) -> None:
        for command in ("make ops-pull", "make roster-pull", "tools/ops/pull_ops.sh", "./tools/ops/pull_roster.sh",
                        "bash tools/ops/pull_roster.sh", "timeout 60 tools/ops/pull_roster.sh"):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 2)
        for command in ("grep -n roster-pull Makefile", "sed -n 1,20p tools/ops/pull_roster.sh"):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 0)

    def test_ssh_that_only_reads_is_allowed(self) -> None:
        for command in (
            "ssh pi tail -n 50 ~/JMRI_UserFiles/messages.log",
            "ssh -p 2222 user@example.invalid cat C:/x/deploy_stamp.txt",
            'ssh pi "pgrep -fl PanelPro; sha256sum ~/JMRI_UserFiles/tables.xml"',
            "ssh -o ConnectTimeout=5 pi systemctl status mosquitto | head",
            "ssh pi git -C ~/sts log -1 --oneline",
            "ssh pi git -C ~/sts log -p -1",
            "grep -rn sshd docs",
            "ssh pi cat ~/hart/pi_quit_panelpro.sh",
            "ssh -p 2222 -o ConnectTimeout=5 win type C:/JMRI_UserFiles/cats/deploy_stamp.txt",
            "timeout 10 ssh pi uptime",
            "make check && git log -1",
            "git log --oneline -3 # recent",
            "ssh pi cat x 2>&1 | head",
            "ssh pi tail -n 5 x 2>/dev/null",
            "tools/hosts/deploy_status.sh --pi --win",
            "python3 -m unittest tools.audit.tests.test_guards",
            "timeout 30 grep -rn deploy docs",
            "timeout 30 grep -rn 'git push' .",
            "time grep -r sync_hart_package.sh .",
            "env FOO=1 grep -rn ssh .",
            "if grep -q 'make deploy' f; then echo y; fi",
            "timeout 60 grep -e if -e then -e else -e elif -e do -e while -e until src",
            'make deploy-status HOSTS="--pi --win"',
            "gh pr view 5",
            "gh api repos/o/r/pulls",
            "git branch --list",
            "uv run pytest -q",
            "ssh pi journalctl -u mosquitto -n 50",
        ):
            with self.subTest(command=command):
                done = run(SUBAGENT_GUARD, command, str(ROOT))
                self.assertEqual(done.returncode, 0, done.stderr)

    def test_ssh_that_writes_or_opens_a_shell_is_blocked(self) -> None:
        for command in (
            "ssh pi",
            "ssh pi rm -f /tmp/x",
            "ssh pi 'cat a > /tmp/jmri_cmd.py'",
            "ssh pi 'ls; touch x'",
            "ssh pi find /tmp -delete",
            "ssh pi sed -i s/a/b/ f",
            "ssh pi systemctl restart mosquitto",
            "ssh -L 8080:localhost:80 pi cat x",
            "ssh pi 'echo $(reboot)'",
            "ssh pi 'cat x | tee y'",
            "bash -c 'ssh pi rm x'",
            "ls && ssh pi reboot",
            "ssh pi 'unbalanced",
            "scp a pi:b",
            # found in review: comments, ssh options, writing programs and shell wrappers
            "echo a#; git push origin main",
            "ssh pi 'cat x#; rm -rf y'",
            "ssh -o ProxyCommand='rm x' pi cat y",
            "ssh -o LocalForward=8080:localhost:80 pi cat x",
            "ssh -F cfg pi cat x",
            "ssh pi sed -n 'w /tmp/jmri_cmd.py' f",
            "ssh pi sed s/x/y/e f",
            "ssh pi git -C ~/sts/sts-docker branch -D active",
            "ssh pi git log --output=/tmp/jmri_cmd.py",
            "ssh pi uniq a /tmp/jmri_cmd.py",
            "ssh pi sort -uo /tmp/x a",
            "ssh -p 2222 win 'echo (Remove-Item C:/x)'",
            "ssh -p 2222 win 'echo $env:PATH'",
            "bash -lc 'git push'",
            "FOO='a b' git push",
            "python3 'tools/my dir/serial_to_mqtt.py'",
            # second review: env, wrappers, option values, cmd quoting, crashes, paths
            'ssh pi "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=reboot git status"',
            "ssh pi \"GIT_PAGER='rm x' git -p log\"",
            "timeout 10 ssh pi rm -rf x",
            "sudo ssh pi reboot",
            "{ ssh pi rm x; }",
            "(ssh pi rm x)",
            "env A=1 ssh pi rm x",
            "ssh pi git --namespace log push",
            "ssh pi systemctl -p status restart mosquitto",
            "ssh pi git -C x -C log reset",
            "ssh win \"type 'a & del y'\"",
            "ssh -o '' pi cat x",
            "ssh pi /tmp/x/cat y",
            "git -C 'a b' commit",
            "timeout 5 git push",
            "sudo make deploy-layout",
            "./tools/hosts/sync_hart_package.sh --pi --win",
            "./tools/hosts/deploy/ship_pi.sh /tmp/stage/pi",
            "bash tools/hosts/deploy/ship_win.sh /tmp/stage/win",
            "run_serial_mqtt.cmd verbose",
            # third review: wrapper option values, conditions, interpreters, host scripts, follow
            "sudo -u pi git push",
            "timeout -s KILL 10 git push",
            "env -u X git push",
            "sudo -u pi ssh pi rm x",
            "if git push; then :; fi",
            "while ssh pi rm x; do :; done",
            "watch -n 2 'git push'",
            "xargs -I {} git push",
            "make redeploy COMMIT=abc HOSTS=--pi",
            "./tools/hosts/redeploy_commit.sh abc --pi",
            "tools/hosts/pi_quit_panelpro.sh --for-deploy",
            "tools/hosts/pi_sts_update.sh",
            "make ops-pull",
            "make sts-pull",
            "bash -x tools/hosts/sync_hart_package.sh --pi",
            "python3 -u serial_to_mqtt.py",
            "python3.11 serial_to_mqtt.py",
            "uv run tools/x/serial_to_mqtt.py",
            "dash -c 'git push'",
            'python3 -c "import os; os.system(\'ssh pi reboot\')"',
            "ssh pi tail -f /var/log/syslog",
            "ssh pi docker logs --follow web",
            "ssh pi git status",
            # fourth review: substitution, grouping, launchers, inline code, gh, find -exec, follow flags
            "(git push)",
            "echo $(git push)",
            "a=$(git push origin HEAD)",
            "echo `git push`",
            "uv run git push",
            "uv run make deploy-layout",
            'python3 -c "import os; os.popen(\'git push\')"',
            "perl -ne 'system(\"git push\")' x",
            "gh pr merge 5 --merge",
            "gh api -X DELETE repos/o/r/git/refs/heads/x",
            "git pull",
            "git branch -D main",
            "git worktree remove x",
            "find . -maxdepth 0 -exec git push \\;",
            "ssh pi journalctl -xef",
            "ssh pi tail -n5 -qf x",
            "ssh pi docker logs --tail 5 -tf web",
            'ssh pi "head x >/dev/null_evil"',
        ):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 2)


class OperatingFlag(unittest.TestCase):
    """While the operating flag is set, what reaches the Pi and Windows waits; the Mac's own work does not."""

    HOSTS = {"HART_PI_SSH": "pi", "HART_PI_WEB_HOST": "RPi-JMRI.local", "HART_MQTT_BROKER": "10.0.0.150",
             "HART_WIN_SSH": "lnevo@minipc-e5h6x.local"}
    FAKE_HOSTS = {"HART_PI_SSH": "fakepi.test", "HART_PI_WEB_HOST": "fakeweb.test", "HART_MQTT_BROKER": "192.0.2.1",
                  "HART_WIN_SSH": "user@fakewin.test"}

    def op_code(self, command: str, flag: str | None, hosts: dict[str, str] | None = None) -> int:
        """The guard's exit code with the operating flag file holding `flag` (None: no file) and the layout
        hosts named by `hosts` (HOSTS when None)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "operating")
            if flag is not None:
                Path(path).write_text(flag, encoding="utf-8")
            guard = load(MAIN_GUARD, "hart_main_guard_operating_test")
            guard.OPERATING_FLAG = path
            guard.main_checkout = lambda target: False
            guard.on_main = lambda target, branched: False
            saved = sys.stdin
            sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": command}, "cwd": str(ROOT)}))
            try:
                with mock_env(CLAUDE_PROJECT_DIR=str(ROOT), HART_GUARD_OPERATING="", **(hosts or self.HOSTS)), \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    return guard.main()
            finally:
                sys.stdin = saved

    def test_only_what_reaches_the_layout_hosts_waits(self) -> None:
        owner = "by=owner\nsince=2026-11-18T15:00:00-0500\nreason=ops session\n"
        blocked = ("./tools/hosts/sync_hart_package.sh --pi --win", "./tools/hosts/sync_hart_package.sh --all",
                   "./tools/hosts/sync_hart_package.sh --win", "make deploy-layout", "make -s deploy-all",
                   'make redeploy COMMIT=abc HOSTS="--win"', 'export HOSTS="--win"; make redeploy COMMIT=abc',
                   'make redeploy COMMIT=abc HOSTS="--pi --win"', "./tools/hosts/redeploy_commit.sh abc --pi",
                   'HOSTS="--pi --win" make redeploy COMMIT=abc', 'export HOSTS="--pi"; make redeploy COMMIT=abc',
                   "HOSTS=--all && make redeploy COMMIT=abc",
                   "tools/hosts/pi_quit_panelpro.sh --for-deploy", "tools/hosts/pi_start_panelpro.sh",
                   "tools/hosts/pi_sts_update.sh", "ssh pi 'pkill -f PanelPro'", "ssh pi pkill java",
                   "ssh -o BatchMode=yes pi 'sudo reboot'",
                   "ssh -p 2222 lnevo@minipc-e5h6x.local taskkill /IM python.exe",
                   "bash -c 'tools/hosts/pi_quit_panelpro.sh --for-deploy'", "zsh -c \"ssh pi pkill -f PanelPro\"",
                   "env HART_PI_RESTART=0 timeout 60 tools/hosts/pi_quit_panelpro.sh",
                   "jmri/layouts/hart/scripts/speedmatch/drop_job.sh /tmp/job.py",
                   "python3 jmri/layouts/hart/scripts/speedmatch/speedmatch.py drop /tmp/job.py",
                   "python3 -u jmri/layouts/hart/scripts/speedmatch/speedmatch.py pom p.json --send",
                   "python3 jmri/layouts/hart/scripts/speedmatch/speedmatch.py pom p.json --se",
                   "python3 jmri/layouts/hart/scripts/speedmatch/speedmatch.py pom p.json --s --apply",
                   "python3 -W ignore jmri/layouts/hart/scripts/speedmatch/speedmatch.py pom p.json --send",
                   "python3 -X dev -W ignore -u jmri/layouts/hart/scripts/speedmatch/speedmatch.py drop /tmp/j.py",
                   "python3 -Wignore jmri/layouts/hart/scripts/speedmatch/speedmatch.py drop /tmp/j.py",
                   "cd jmri/layouts/hart/scripts/speedmatch && python3 -m speedmatch pom p.json --send",
                   'make speedmatch ARGS="pom p.json --apply --consists-broken --send"',
                   "make speedmatch ARGS='drop /tmp/job.py'")
        for cmd in blocked:
            self.assertEqual(self.op_code(cmd, owner), 2, cmd)
            self.assertEqual(self.op_code(cmd, None), 0, cmd)          # no flag: allowed
        # the Mac's own work stays open; Windows stays guarded, as it runs the LCOS bridge
        for cmd in ("make tables-pull", "./tools/hosts/sync_hart_package.sh", "make panelpro-test",
                    "osascript -e 'tell application \"PanelPro\" to quit'", "open -a /Applications/JMRI/PanelPro.app",
                    "jmri/layouts/hart/scripts/run_sml_discover.sh", "make deploy-site", "./tools/check.sh",
                    'make redeploy COMMIT=abc HOSTS="--mac"', "./tools/hosts/sync_hart_package.sh --stage-only /tmp/x",
                    "ssh pi uptime", "ssh other-host pkill java", "ssh -p 2222 lnevo@minipc-e5h6x.local hostname",
                    "cat tools/hosts/pi_quit_panelpro.sh",
                    "tools/hosts/operating.sh off --owner", "tools/hosts/operating.sh status",
                    "jmri/layouts/hart/scripts/speedmatch/drop_job.sh --fetch /tmp/x.log",
                    "jmri/layouts/hart/scripts/speedmatch/drop_job.sh --kill",
                    "python3 jmri/layouts/hart/scripts/speedmatch/speedmatch.py pom p.json --out /tmp/d.py",
                    "python3 jmri/layouts/hart/scripts/speedmatch/speedmatch.py drop --kill",
                    "python3 -W ignore jmri/layouts/hart/scripts/speedmatch/speedmatch.py pom p.json --out /tmp/d.py",
                    "python3 -c 'print(1)'",
                    'make speedmatch ARGS="job steps --loco x --out /tmp/j.py"', "make speedmatch"):
            self.assertEqual(self.op_code(cmd, owner), 0, cmd)
        # a speed-matching run's own flag lets the run's next job through, never a host deploy
        speed = "by=speedmatch\nsince=2026-11-18T15:00:00-0500\nreason=job\n"
        self.assertEqual(self.op_code("jmri/layouts/hart/scripts/speedmatch/drop_job.sh /tmp/job.py", speed), 0)
        self.assertEqual(self.op_code("make deploy-layout", speed), 2)

    def test_ssh_behind_substitutions_pipes_and_wrappers_waits(self) -> None:
        owner = "by=owner\nsince=2026-11-18T15:00:00-0500\nreason=ops session\n"
        blocked = ("ssh fakepi.test reboot", "echo $(ssh fakepi.test reboot)", "echo `ssh fakepi.test reboot`",
                   "echo $(echo $(ssh fakepi.test reboot))", "echo `echo \\`ssh fakepi.test reboot\\``",
                   'echo "$(ssh fakepi.test reboot)"', "a=$(ssh fakepi.test reboot)",
                   "echo fakepi.test | xargs -I{} ssh {} reboot",
                   "echo fakepi.test | xargs -n1 -P2 -I {} ssh {} reboot", "echo reboot | xargs ssh fakepi.test",
                   "bash -c 'ssh fakepi.test reboot'", 'sh -c "ssh fakepi.test reboot"',
                   "zsh -lc 'ssh fakepi.test reboot'", "env A=1 ssh fakepi.test reboot",
                   "nohup ssh fakepi.test reboot", "time ssh fakepi.test reboot",
                   "timeout -s KILL 10 ssh fakepi.test reboot", "sudo -u x ssh fakepi.test reboot",
                   "nice -n 5 ssh fakepi.test reboot", "exec ssh fakepi.test reboot",
                   "command ssh fakepi.test reboot", "watch -n 2 'ssh fakepi.test reboot'",
                   "if ssh fakepi.test reboot; then :; fi", "while true; do ssh fakepi.test reboot; done",
                   "until ssh fakepi.test reboot; do :; done", "for h in fakepi.test; do ssh $h reboot; done",
                   "ls; ssh fakepi.test reboot", "true && ssh fakepi.test reboot", "false || ssh fakepi.test reboot",
                   "ls | ssh fakepi.test reboot", "(ssh fakepi.test reboot)", "{ ssh fakepi.test reboot; }",
                   "find . -exec ssh {} reboot \\;", "ssh user@fakewin.test taskkill /IM java.exe",
                   "ssh $HART_PI_SSH reboot", "H=fakepi.test; ssh $H reboot",
                   "cat <<EOF | ssh fakepi.test\nreboot\nEOF", "ssh fakepi.test bash -s <<EOF\nreboot\nEOF",
                   "bash <<EOF\nssh fakepi.test reboot\nEOF", "2>/dev/null ssh fakepi.test reboot",
                   "2>&1 ssh fakepi.test reboot", "setsid ssh fakepi.test reboot",
                   "flock /tmp/l ssh fakepi.test reboot", "$(echo ssh) fakepi.test reboot",
                   # lines the parser cannot split block when they name a layout host
                   "echo $(ssh fakepi.test reboot", "ssh fakepi.test 'reboot", "echo `ssh fakepi.test reboot")
        for cmd in blocked:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.op_code(cmd, owner, self.FAKE_HOSTS), 2)
                self.assertEqual(self.op_code(cmd, None, self.FAKE_HOSTS), 0)
        for cmd in ("echo ssh", "echo ssh fakepi.test reboot", "grep fakepi.test file",
                    "grep -rn 'ssh fakepi.test reboot' .", "ssh other.test reboot", "echo $(ssh other.test reboot)",
                    "bash -c 'ssh other.test reboot'", "ssh fakepi.test uptime", "echo $(ssh fakepi.test uptime)",
                    "ssh fakepi.test cat ~/x.sh", "echo 'unbalanced",
                    "$(git rev-parse --show-toplevel)/tools/check.sh", "2>/dev/null ssh other.test reboot",
                    "git commit -m \"$(cat <<'EOF'\nit's done on fakepi.test\nEOF\n)\""):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.op_code(cmd, owner, self.FAKE_HOSTS), 0)

    def test_the_env_files_are_read_once_per_call(self) -> None:
        guard = load(MAIN_GUARD, "hart_main_guard_env_once")
        reads = []
        real = guard.layout_env
        guard.layout_env = lambda: reads.append(1) or real()
        guard.main_checkout = lambda target: False
        guard.on_main = lambda target, branched: False
        command = "ls; echo $(date); bash -c 'ls; pwd' && ssh other.test uptime"
        saved = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": command}, "cwd": str(ROOT)}))
        try:
            with mock_env(CLAUDE_PROJECT_DIR=str(ROOT), HART_GUARD_OPERATING="1", **self.FAKE_HOSTS), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(guard.main(), 0)
        finally:
            sys.stdin = saved
        self.assertEqual(len(reads), 1)

    def test_the_flag_can_be_forced(self) -> None:
        guard = load(MAIN_GUARD, "hart_main_guard_operating_force")
        guard.OPERATING_FLAG = "/nonexistent/flag"
        with mock_env(HART_GUARD_OPERATING="1"):
            self.assertIsNotNone(guard.operating())
        with mock_env(HART_GUARD_OPERATING="0"):
            self.assertIsNone(guard.operating())
        with mock_env(HART_GUARD_OPERATING=""):
            self.assertIsNone(guard.operating())


if __name__ == "__main__":
    unittest.main()
