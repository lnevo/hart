"""A deploy asks every host named on the command line for an ssh answer before it changes anything.

Windows is kept matching the Pi and the Pi step runs first, so an unreachable Windows must stop
`--pi --win` before the Pi step. ssh and scp are stand-ins that log each call: a host listed in
down.txt refuses, the no-op and the Pi's read-only checks answer, and anything else (the first
real host step) fails with 99. Nothing reaches a host. HOME and TMPDIR are temporary folders, the
gate that rewrites tables.xml runs as a dry run (keep_repo_tables), and every test checks that the
checkout is as it was where a deploy could change it (checkout_state).
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_stage import git, keep_repo_tables, stage_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SYNC = ROOT / "tools/hosts/sync_hart_package.sh"
REDEPLOY = ROOT / "tools/hosts/redeploy_commit.sh"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
PI = "pi.example.invalid"
WIN = "win.example.invalid"
PI_DOWN = f"STOP: cannot reach the Pi ({PI}) over ssh."
WIN_DOWN = f"STOP: cannot reach Windows (nobody@{WIN} port 1) over ssh."
ANY_DOWN = "STOP: cannot reach"
NO_FILE = "No file was sent to or installed on any host, and the Mac install did not run."
UNPULLED_HINT = "could not check the Pi for unpulled changes"
RESTARTING = "Starting PanelPro on the Pi again (it was quit for this deploy)"
FAKE_SSH = r"""#!/bin/bash
echo "ssh $*" >>"@TMP@/network.log"
while read -r host; do
  [[ -n "$host" && " $* " == *"$host "* ]] && { echo "ssh: connect to host $host: refused" >&2; exit 255; }
done <"@TMP@/down.txt"
cmd="${@: -1}"
# mksock: the preflight no-op opens a master, as real ssh does with ControlMaster=auto.
if [[ -f "@TMP@/mksock" && "$cmd" == true ]]; then
  for a in "$@"; do
    [[ "$a" == ControlPath=* ]] && python3 -c 'import socket, sys; socket.socket(socket.AF_UNIX).bind(sys.argv[1])' "${a#ControlPath=}"
  done
fi
# pi_ok: the Pi's file steps answer, so a run gets as far as the Windows step.
if [[ -f "@TMP@/pi_ok" ]]; then
  case "$cmd" in
    "mktemp -d /tmp/hart-deploy.XXXXXX") echo /tmp/hart-deploy.fake; exit 0 ;;
    *apply_hart_package_local.sh) exit 0 ;;
  esac
fi
# win_ok: Windows gives a drop folder and the apply exits with win_apply_rc; the folder cleanup fails.
if [[ -f "@TMP@/win_ok" ]]; then
  case "$cmd" in
    *"New-Item -ItemType Directory"*) echo 'C:\Temp\hart-deploy-fake'; exit 0 ;;
    *"tar -xzf _pkg.tgz"*) exit 0 ;;
    *apply_hart_package_local.ps1*) exit "$(cat "@TMP@/win_apply_rc")" ;;
  esac
fi
case "$cmd" in
  true|"exit 0") exit 0 ;;                       # the preflight no-op
  "bash -s -- '"*) cat >/dev/null; exit 0 ;;     # unpulled_changes.sh: nothing unpulled
  "bash -s") cat >/dev/null; cat "@TMP@/restart.txt"; exit 0 ;;  # panelpro_restart_due.sh
esac
exit 99
"""
# rsync to a host only logs; a local copy (the staging) runs the real rsync.
FAKE_RSYNC = r"""#!/bin/bash
if [[ "${@: -1}" == *.example.invalid:* ]]; then
  echo "rsync $*" >>"@TMP@/network.log"
  exit 0
fi
exec "@RSYNC@" "$@"
"""

# Where a deploy could leave a new untracked file: the trees it reads from or writes beside, and the
# top level (it runs with the checkout as its working folder). check.sh runs other test jobs at the
# same time, and a temporary file one of them makes elsewhere (www/, tools/hartlib/) is not the deploy's.
DEPLOY_TREES = ("jmri/", "cats/", "tools/hosts/", "tools/env/", "tools/mqtt-mimic/", "docs/jmri/")


def deploy_could_write(line: str) -> bool:
    """A `git status --porcelain` line the deploy could have caused: any tracked change, and an untracked
    path at the top level or under DEPLOY_TREES."""
    if not line.startswith("?? "):
        return True
    path = line[3:].strip('"')
    return "/" not in path.rstrip("/") or path.startswith(DEPLOY_TREES)


def checkout_state(status: str | None = None) -> tuple[str, list[str]]:
    """The tables.xml hash and the status lines a deploy could have changed."""
    if status is None:
        status = git("status", "--porcelain", raw=True).decode()
    return (hashlib.sha256(TABLES.read_bytes()).hexdigest(),
            [ln for ln in status.splitlines() if deploy_could_write(ln)])


class DeployHarness(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = stage_env(self.tmp)
        keep_repo_tables(self.tmp)
        self.scratch = self.tmp / "scratch"
        self.scratch.mkdir()
        self.env.update(HOME=str(self.tmp / "home"), TMPDIR=str(self.scratch))
        (self.tmp / "bin/ssh").write_text(FAKE_SSH.replace("@TMP@", str(self.tmp)), encoding="utf-8")
        (self.tmp / "restart.txt").write_text("no\n", encoding="utf-8")
        self.down()
        # No test may change the checkout: the tables bytes and git's view of it stay as they were.
        before = checkout_state()
        self.addCleanup(lambda: self.assertEqual(before, checkout_state(), "the deploy changed the checkout"))

    def down(self, *hosts: str) -> None:
        (self.tmp / "down.txt").write_text("".join(f"{h}\n" for h in hosts), encoding="utf-8")

    def calls(self) -> list[str]:
        log = self.tmp / "network.log"
        return log.read_text().splitlines() if log.exists() else []

    def pi_calls(self) -> list[str]:
        return [c.split(f"{PI} ", 1)[1] for c in self.calls() if f"{PI} " in c]

    def deploy(self, *flags: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SYNC), *flags], cwd=ROOT, env=self.env,
                              capture_output=True, text=True, timeout=600)


class CheckoutGuardTest(unittest.TestCase):
    """The guard ignores another job's temporary file and still sees what a deploy could change."""

    def test_other_jobs_temporary_files_are_ignored(self) -> None:
        clean = checkout_state("")
        for stray in ("?? www/data/tmpab12cd/", "?? tools/hartlib/tests/probe.py"):
            self.assertEqual(clean, checkout_state(stray), stray)

    def test_a_deploy_change_is_seen(self) -> None:
        clean = checkout_state("")
        for dirt in (" M jmri/layouts/hart/output/tables.xml", "M  cats/panels/HART_CTC.xml",
                     " M www/index.html", "?? jmri/layouts/hart/output/stage/", "?? cats/deploy_stamp.txt",
                     "?? stage/", "?? deploy_stamp.txt", '?? "tools/hosts/a b.sh"'):
            self.assertNotEqual(clean, checkout_state(dirt), dirt)


class PreflightTest(DeployHarness):
    def test_windows_down_stops_pi_and_win_before_any_pi_step(self) -> None:
        self.down(WIN)
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(WIN_DOWN, done.stderr)
        self.assertIn(NO_FILE, done.stderr)
        self.assertNotIn(PI_DOWN, done.stderr)
        self.assertNotIn("Deploy → Pi", done.stdout)
        # The Pi saw only the no-op and the restart check: no unpulled check, no file step.
        self.assertEqual(["true", "bash -s"], self.pi_calls(), self.calls())
        self.assertNotIn(RESTARTING, done.stdout)
        self.assertFalse((self.tmp / "home").exists(), "the Mac install ran")
        self.assertFalse((self.tmp / "gates.log").exists(), "the tables.xml gate ran")

    def test_stop_says_that_panelpro_quit_for_the_deploy_is_started_again(self) -> None:
        self.down(WIN)
        (self.tmp / "restart.txt").write_text("yes\n", encoding="utf-8")
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(NO_FILE, done.stderr)
        self.assertIn("The Pi answered: PanelPro there is started again if it was quit for this deploy",
                      done.stderr)
        self.assertIn(RESTARTING, done.stdout)
        # The no-op, the restart check, then pi_start_panelpro.sh's own ssh (which the stand-in fails).
        self.assertEqual(3, len(self.pi_calls()), self.calls())
        self.assertIn("PanelPro did not start on the Pi; run tools/hosts/pi_start_panelpro.sh", done.stderr)

    def test_pi_down_names_the_pi_not_the_unpulled_check(self) -> None:
        self.down(PI)
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(PI_DOWN, done.stderr)
        self.assertNotIn(WIN_DOWN, done.stderr)
        self.assertNotIn(UNPULLED_HINT, done.stderr)
        self.assertNotIn("HART_DISCARD_PI_CHANGES", done.stderr)
        self.assertNotIn("The Pi answered", done.stderr)
        # One no-op each, and no restart check on a Pi that does not answer.
        self.assertEqual(2, len(self.calls()), self.calls())

    def test_both_down_names_both_and_skips_the_restart_check(self) -> None:
        self.down(PI, WIN)
        done = self.deploy("--all")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(PI_DOWN, done.stderr)
        self.assertIn(WIN_DOWN, done.stderr)
        self.assertEqual(2, len(self.calls()), self.calls())

    def test_single_host_checks_only_that_host(self) -> None:
        self.down(PI, WIN)
        pi = self.deploy("--pi")
        self.assertEqual(1, pi.returncode, pi.stderr)
        self.assertIn(PI_DOWN, pi.stderr)
        self.assertNotIn(WIN_DOWN, pi.stderr)
        self.assertEqual(1, len(self.calls()), self.calls())
        self.assertFalse(any(WIN in c for c in self.calls()), self.calls())
        (self.tmp / "network.log").unlink()
        win = self.deploy("--win")
        self.assertEqual(1, win.returncode, win.stderr)
        self.assertIn(WIN_DOWN, win.stderr)
        self.assertNotIn(PI_DOWN, win.stderr)
        self.assertEqual(1, len(self.calls()), self.calls())
        self.assertFalse(any(PI in c for c in self.calls()), self.calls())

    def test_both_reachable_goes_on_to_the_pi_step(self) -> None:
        done = self.deploy("--pi", "--win")
        self.assertNotIn(ANY_DOWN, done.stderr)
        self.assertIn("Deploy → Pi", done.stdout)
        calls = self.calls()
        self.assertTrue(calls[0].endswith(f"{PI} true"), calls)
        self.assertTrue(calls[1].endswith(f"{WIN} exit 0"), calls)
        self.assertTrue(calls[2].endswith(f"{PI} bash -s -- '/srv/fake-pi/JMRI_UserFiles'"), calls)
        # The first real host step, which the stand-in fails.
        self.assertIn("mktemp -d /tmp/hart-deploy.XXXXXX", calls[3])
        self.assertEqual(99, done.returncode, done.stderr[-2000:])
        # The gate that rewrites tables.xml was reached, and ran as a dry run.
        self.assertEqual(1, len((self.tmp / "gates.log").read_text().splitlines()))

    def test_one_host_goes_on_while_the_other_is_down(self) -> None:
        self.down(PI)
        done = self.deploy("--win")
        self.assertNotIn(ANY_DOWN, done.stderr)
        self.assertIn("Deploy → Windows", done.stdout)
        self.assertFalse(any(PI in c for c in self.calls()), self.calls())

    def test_windows_tarball_is_removed_on_every_way_out(self) -> None:
        # A real run that fails at the first Windows step, twice, then a dry run: the old template
        # (hart-pkg.XXXXXX.tgz) left its literal name behind and the second run failed at mktemp.
        for flags in (("--win",), ("--win",), ("--win", "--dry-run")):
            done = self.deploy(*flags)
            self.assertIn("Deploy → Windows", done.stdout)
            self.assertNotIn("mktemp:", done.stderr)
            self.assertEqual([], sorted(p.name for p in self.scratch.iterdir()), flags)
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertIn("dry-run: would scp", done.stdout)
        # The real runs got as far as asking Windows for a drop folder, after the tarball was made.
        self.assertEqual(2, sum("hart-deploy-" in c for c in self.calls()), self.calls())
        src = SYNC.read_text(encoding="utf-8")
        self.assertIn('mktemp "${TMPDIR:-/tmp}/hart-pkg.XXXXXX")', src)

    def test_dry_run_and_stage_only_skip_the_check(self) -> None:
        self.down(PI, WIN)
        done = self.deploy("--pi", "--win", "--stage-only", str(self.tmp / "stage"))
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertEqual([], self.calls())
        done = self.deploy("--win", "--dry-run")
        self.assertNotIn(ANY_DOWN, done.stderr)
        self.assertEqual([], self.calls())

    def test_check_only_asks_the_hosts_named_and_stops_there(self) -> None:
        done = self.deploy("--check-only", "--win")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Host check: every host named answered over ssh.", done.stdout)
        self.assertNotIn("Pi check", done.stdout)
        self.assertEqual(1, len(self.calls()), self.calls())
        self.assertTrue(self.calls()[0].endswith(f"{WIN} exit 0"), self.calls())
        self.down(WIN)
        done = self.deploy("--check-only", "--all")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(WIN_DOWN, done.stderr)

    def test_redeploy_checks_the_hosts_before_the_older_commits_deploy(self) -> None:
        self.down(WIN)
        for hosts in (("--pi", "--win"), ("--win",)):
            done = subprocess.run(["bash", str(REDEPLOY), "HEAD", "--allow-unmerged", *hosts], cwd=ROOT,
                                  env=self.env, capture_output=True, text=True, timeout=600)
            self.assertEqual(1, done.returncode, done.stderr)
            self.assertIn(WIN_DOWN, done.stderr)
            self.assertNotIn("temporary worktree", done.stdout)
        self.assertFalse(any("mktemp" in c or "powershell" in c for c in self.calls()), self.calls())


class SshReuseTest(DeployHarness):
    """The Pi calls share one ssh connection through a socket folder made for the run; Windows keeps one
    connection per call. The folder is gone after every run, and a master that was opened is told to exit."""

    def setUp(self) -> None:
        super().setUp()
        rsync = shutil.which("rsync")
        assert rsync, "rsync is needed for the staging"
        tool = self.tmp / "bin/rsync"
        tool.write_text(FAKE_RSYNC.replace("@TMP@", str(self.tmp)).replace("@RSYNC@", rsync), encoding="utf-8")
        tool.chmod(0o755)
        (self.tmp / "pi_ok").touch()

    def control_paths(self) -> set[str]:
        return {a.split("=", 1)[1] for c in self.calls() for a in c.split() if a.startswith("ControlPath=")}

    def test_pi_calls_share_one_socket_and_windows_calls_do_not(self) -> None:
        done = self.deploy("--pi", "--win")
        self.assertEqual(99, done.returncode, done.stderr[-2000:])
        self.assertIn("Pi deploy done.", done.stdout)
        pi = [c for c in self.calls() if PI in c]
        win = [c for c in self.calls() if WIN in c]
        # the no-op, the unpulled check, the drop folder, the rsync, the apply and the restart check
        self.assertEqual(6, len(pi), pi)
        paths = self.control_paths()
        self.assertEqual(1, len(paths), self.calls())
        path = Path(paths.pop())
        self.assertEqual("pi", path.name)
        self.assertTrue(all(f"ControlPath={path}" in c for c in pi), pi)
        self.assertTrue(any(c.startswith("rsync ") and f"ControlPath={path}" in c for c in pi), pi)
        self.assertTrue(win and not any("ControlPath" in c for c in win), win)
        self.assertFalse(path.parent.exists(), "the socket folder was left behind")
        # no master was opened, so none is told to exit
        self.assertFalse(any("-O exit" in c for c in self.calls()), self.calls())

    def test_an_opened_master_is_closed_and_its_folder_removed(self) -> None:
        (self.tmp / "mksock").touch()
        done = self.deploy("--pi", "--win")
        self.assertIn("Pi deploy done.", done.stdout)
        exits = [c for c in self.calls() if "-O exit" in c]
        self.assertEqual(1, len(exits), self.calls())
        self.assertTrue(exits[0].endswith(f"-O exit {PI}"), exits)
        self.assertFalse(Path(self.control_paths().pop()).parent.exists())

    def test_a_stopped_run_removes_the_folder_too(self) -> None:
        self.down(WIN)
        done = self.deploy("--pi", "--win")
        self.assertIn(WIN_DOWN, done.stderr)
        paths = self.control_paths()
        self.assertEqual(1, len(paths), self.calls())
        self.assertFalse(Path(paths.pop()).parent.exists())

    def test_hart_ssh_mux_0_turns_reuse_off(self) -> None:
        self.env["HART_SSH_MUX"] = "0"
        done = self.deploy("--pi", "--win")
        self.assertIn("Pi deploy done.", done.stdout)
        self.assertEqual(set(), self.control_paths())

    def test_windows_failing_after_the_pi_was_deployed_says_so(self) -> None:
        done = self.deploy("--pi", "--win")
        self.assertEqual(99, done.returncode, done.stderr[-2000:])
        self.assertIn("Pi deploy done.", done.stdout)
        self.assertNotIn("Windows deploy done.", done.stdout)
        commit = git("rev-parse", "HEAD")
        self.assertIn(f"The Pi has this deploy (commit {commit[:12]}) but Windows does not.", done.stderr)
        self.assertIn(f"make redeploy COMMIT={commit} HOSTS=--win", done.stderr)
        self.assertNotIn("partly installed", done.stderr)
        self.assertEqual([], sorted(p.name for p in self.scratch.iterdir()), "staging or tarball left behind")

    def win_reaches_apply(self, rc: int) -> None:
        (self.tmp / "win_ok").touch()
        (self.tmp / "win_apply_rc").write_text(f"{rc}\n", encoding="utf-8")
        scp = self.tmp / "bin/scp"
        scp.write_text(f'#!/bin/sh\necho "scp $*" >>"{self.tmp}/network.log"\nexit 0\n', encoding="utf-8")
        scp.chmod(0o755)

    def test_windows_apply_failing_says_it_may_be_partly_installed(self) -> None:
        self.win_reaches_apply(7)
        done = self.deploy("--pi", "--win")
        self.assertEqual(7, done.returncode, done.stderr[-2000:])
        self.assertIn("Windows may be partly installed", done.stderr)
        self.assertIn("make redeploy COMMIT=", done.stderr)

    def test_windows_cleanup_failing_after_a_good_apply_says_nothing(self) -> None:
        # The apply succeeded; only the drop-folder removal fails (the stand-in refuses it).
        self.win_reaches_apply(0)
        done = self.deploy("--pi", "--win")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertTrue(any("Remove-Item" in c for c in self.calls()), self.calls())
        self.assertIn("WARNING: could not remove C:\\Temp\\hart-deploy-fake on Windows", done.stderr)
        self.assertIn("Windows deploy done.", done.stdout)
        self.assertNotIn("The Pi has this deploy", done.stderr)

    def test_a_tmpdir_with_whitespace_puts_the_socket_folder_in_tmp(self) -> None:
        spaced = self.tmp / "a b"
        spaced.mkdir()
        self.env["TMPDIR"] = str(spaced)
        done = self.deploy("--pi", "--win")
        self.assertIn("Pi deploy done.", done.stdout)
        paths = self.control_paths()
        self.assertEqual(1, len(paths), self.calls())
        self.assertTrue(paths.pop().startswith("/tmp/hart-ssh."), self.calls())

    def test_windows_alone_failing_does_not_mention_the_pi(self) -> None:
        done = self.deploy("--win")
        self.assertEqual(99, done.returncode, done.stderr[-2000:])
        self.assertNotIn("The Pi has this deploy", done.stderr)
        self.assertEqual(set(), self.control_paths())


if __name__ == "__main__":
    unittest.main()
