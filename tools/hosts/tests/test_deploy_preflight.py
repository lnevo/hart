"""A deploy asks every host named on the command line for an ssh answer before it changes anything.

Windows is kept matching the Pi and the Pi step runs first, so an unreachable Windows must stop
`--pi --win` before the Pi step. ssh and scp are stand-ins that log each call: a host listed in
down.txt refuses, the no-op and the Pi's read-only checks answer, and anything else (the first
real host step) fails with 99. Nothing reaches a host. HOME and TMPDIR are temporary folders, a
step that would rewrite tables.xml runs as a dry run and is logged (keep_repo_tables), and every test checks that the
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
DEPLOY_STEPS = ROOT / "tools/hosts/deploy"
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
# mksock: the preflight no-op (Pi "true", Windows "exit 0") opens a master, as real ssh does with
# ControlMaster=auto.
if [[ -f "@TMP@/mksock" && ( "$cmd" == true || "$cmd" == "exit 0" ) ]]; then
  for a in "$@"; do
    [[ "$a" == ControlPath=* ]] && python3 -c 'import socket, sys; socket.socket(socket.AF_UNIX).bind(sys.argv[1])' "${a#ControlPath=}"
  done
fi
# The gate's Windows probe (a temp folder made and removed, tar found) answers unless win_probe_fails or win_no_tar.
case "$cmd" in
  *hart-probe-*)
    [[ ! -f "@TMP@/win_probe_fails" ]] || { echo "ssh: no temp folder" >&2; exit 1; }
    [[ ! -f "@TMP@/win_no_tar" ]] || { echo "tar: not found" >&2; exit 1; }
    exit 0 ;;
esac
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


def status_path(line: str) -> str:
    """The path a porcelain status line names (the new name for a rename)."""
    path = line[3:].split(" -> ")[-1]
    return path[1:-1] if path.startswith('"') and path.endswith('"') else path


def checkout_state(status: str | None = None, root: Path = ROOT) -> tuple[str, list[str]]:
    """The tables.xml hash, and each status line a deploy could have changed with a hash of
    that file's contents, so a second edit to a file that was already modified is seen too."""
    if status is None:
        # -uall lists each untracked file, so a new file inside an untracked folder shows too.
        status = git("status", "--porcelain", "-uall", raw=True).decode()
    lines = []
    for ln in status.splitlines():
        if not deploy_could_write(ln):
            continue
        path = status_path(ln)
        digest = ""
        # Hash contents only where the deploy reads or writes, so an edit elsewhere (www/) during
        # the run cannot fail the guard; a file another job removes mid-read keeps its bare line.
        if "/" not in path or path.startswith(DEPLOY_TREES):
            try:
                digest = hashlib.sha256((root / path).read_bytes()).hexdigest()
            except OSError:
                pass
        lines.append(f"{ln} {digest}" if digest else ln)
    return (hashlib.sha256(TABLES.read_bytes()).hexdigest(), lines)


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

    def test_a_second_edit_to_an_already_modified_file_is_seen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            panel = Path(tmp) / "cats/panels/HART_CTC.xml"
            panel.parent.mkdir(parents=True)
            panel.write_text("owner's uncommitted edit\n", encoding="utf-8")
            line = " M cats/panels/HART_CTC.xml"
            before = checkout_state(line, root=Path(tmp))
            self.assertEqual(before, checkout_state(line, root=Path(tmp)))
            panel.write_text("owner's uncommitted edit\nand the deploy's\n", encoding="utf-8")
            self.assertNotEqual(before, checkout_state(line, root=Path(tmp)))

    def test_an_edit_outside_the_deploy_trees_is_not_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "www/index.html"
            page.parent.mkdir(parents=True)
            page.write_text("one\n", encoding="utf-8")
            line = " M www/index.html"
            before = checkout_state(line, root=Path(tmp))
            page.write_text("two\n", encoding="utf-8")
            self.assertEqual(before, checkout_state(line, root=Path(tmp)))

    def test_a_quoted_or_renamed_path_is_read(self) -> None:
        self.assertEqual("tools/hosts/a b.sh", status_path('?? "tools/hosts/a b.sh"'))
        self.assertEqual("cats/new.xml", status_path("R  cats/old.xml -> cats/new.xml"))


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
        # the unpulled check, with the generated tables.xml's hash as the reference for a Pi that has none
        generated = hashlib.sha256(TABLES.read_bytes()).hexdigest()
        # and the hash of each Store a merged split took in (store_splits.csv), so the Pi's file of one is not unpulled
        splits = ROOT / "jmri/layouts/hart/data/store_splits.csv"
        shas = [ln.split(",", 1)[0] for ln in splits.read_text().splitlines()[1:]] if splits.is_file() else []
        # and the hash of the Operations files this checkout ships (ops:), which a merged auto-pulled session equals
        ops = hashlib.sha256(b"".join((ROOT / "jmri/layouts/hart/operations" / n).read_bytes() for n in (
            "Operations.xml", "OperationsCarRoster.xml", "OperationsEngineRoster.xml", "OperationsLocationRoster.xml",
            "OperationsRouteRoster.xml", "OperationsTrainRoster.xml"))).hexdigest()
        # and the hash of the DecoderPro roster this checkout ships (roster:, tools/hosts/pi/roster_sha.sh)
        roster = subprocess.run(["bash", str(ROOT / "tools/hosts/pi/roster_sha.sh"), str(ROOT / "jmri/layouts/hart/roster")],
                                capture_output=True, text=True, check=True).stdout.strip()
        want = (f"{PI} bash -s -- '/srv/fake-pi/JMRI_UserFiles' '{generated}' ops:{ops} roster:{roster}"
                + "".join(f" {h}" for h in shas))
        self.assertTrue(calls[2].endswith(want), calls)
        # Windows' probe is the last gate call; then the first real host step, which the stand-in fails.
        self.assertIn("hart-probe-", calls[3])
        self.assertIn("mktemp -d /tmp/hart-deploy.XXXXXX", calls[4])
        self.assertEqual(99, done.returncode, done.stderr[-2000:])
        # No gate rewrites tables.xml any more (R9c: the generator applies the Digicon rule), so the hosts get the
        # committed bytes.
        self.assertFalse((self.tmp / "gates.log").exists(), "a deploy step ran disable_digicon_sml_in_tables.py")
        # the freshness check ran before the first host step (a stand-in for build_tables.py --check)
        self.assertIn("build_tables.py --check", (self.tmp / "tables_check.log").read_text())

    def test_stale_tables_stop_the_deploy_before_any_host_step(self) -> None:
        """tables.xml must be what build_tables.py writes (R9c): a stale file stops the deploy after the read-only
        host checks and before anything is sent (the check itself is check.sh's tables job; a stand-in here)."""
        (self.tmp / "tables_stale").touch()
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertIn("STOP: tables.xml is not what tools/schematic/build_tables.py writes", done.stderr)
        self.assertIn("--check", (self.tmp / "tables_check.log").read_text())
        self.assertNotIn("Deploy → Pi", done.stdout)
        self.assertFalse(any("mktemp -d /tmp/hart-deploy" in c for c in self.calls()), self.calls())

    def test_a_missing_plugin_gets_its_own_stop(self) -> None:
        (self.tmp / "tables_no_plugin").touch()
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertIn("STOP: the tables check needs the schematic-maps plugin at its pin: run git submodule update",
                      done.stderr)
        self.assertNotIn("is not what tools/schematic/build_tables.py writes", done.stderr)
        self.assertNotIn("Deploy → Pi", done.stdout)

    def test_a_source_error_gets_its_own_stop(self) -> None:
        (self.tmp / "tables_source_error").touch()
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertIn("cannot make tables.xml from its sources: fix the source error above, or rerun discovery",
                      done.stderr)
        self.assertNotIn("is not what tools/schematic/build_tables.py writes", done.stderr)

    def test_a_redeploy_skips_the_regeneration_but_checks_digicon(self) -> None:
        """A redeploy (HART_REDEPLOY_FROM) would redraw with another plugin than the commit's: no regeneration, a
        line that says so, and the Digicon check still stops an enabled destination."""
        (self.tmp / "tables_stale").touch()
        self.env["HART_REDEPLOY_FROM"] = "0" * 40
        done = self.deploy("--pi", "--win")
        self.assertIn("Redeploy of an older commit: not regenerating tables.xml", done.stdout)
        self.assertNotIn("is not what tools/schematic/build_tables.py writes", done.stderr)
        self.assertFalse((self.tmp / "tables_check.log").exists(), "the regeneration ran on a redeploy")
        self.assertIn("Deploy → Pi", done.stdout)
        (self.tmp / "digicon_enabled").touch()
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertIn("STOP: a Digicon mast's Signal Mast Logic is stored enabled", done.stderr)

    def test_an_enabled_digicon_destination_stops_the_deploy(self) -> None:
        (self.tmp / "digicon_enabled").touch()
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertIn("STOP: a Digicon mast's Signal Mast Logic is stored enabled", done.stderr)
        self.assertNotIn("Deploy → Pi", done.stdout)
        self.assertFalse(any("mktemp -d /tmp/hart-deploy" in c for c in self.calls()), self.calls())

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
    """Each host's calls share one ssh connection, on its own socket ("pi", "win") in a folder made for the
    run. The folder is gone after every run, and a master that was opened is told to exit."""

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

    def sockets(self) -> dict[str, Path]:
        """The socket each host used, by name ("pi", "win"); every one sits in the same run folder."""
        found = {Path(p).name: Path(p) for p in self.control_paths()}
        self.assertEqual(len(found), len(self.control_paths()), self.calls())
        self.assertLessEqual(len({p.parent for p in found.values()}), 1, found)
        return found

    def test_each_host_shares_its_own_socket(self) -> None:
        done = self.deploy("--pi", "--win")
        self.assertEqual(99, done.returncode, done.stderr[-2000:])
        self.assertIn("Pi deploy done.", done.stdout)
        pi = [c for c in self.calls() if PI in c]
        win = [c for c in self.calls() if WIN in c]
        # the no-op, the unpulled check, the drop folder, the rsync, the apply and the restart check
        self.assertEqual(6, len(pi), pi)
        # the no-op, the gate's probe and the drop folder (which the stand-in fails)
        self.assertEqual(3, len(win), win)
        sockets = self.sockets()
        self.assertEqual({"pi", "win"}, set(sockets), self.calls())
        self.assertTrue(all(f"ControlPath={sockets['pi']}" in c for c in pi), pi)
        self.assertTrue(any(c.startswith("rsync ") and f"ControlPath={sockets['pi']}" in c for c in pi), pi)
        self.assertTrue(all(f"ControlPath={sockets['win']}" in c and "ControlMaster=auto" in c for c in win), win)
        self.assertFalse(sockets["pi"].parent.exists(), "the socket folder was left behind")
        # no master was opened, so none is told to exit
        self.assertFalse(any("-O exit" in c for c in self.calls()), self.calls())

    def test_an_opened_master_is_closed_and_its_folder_removed(self) -> None:
        (self.tmp / "mksock").touch()
        done = self.deploy("--pi", "--win")
        self.assertIn("Pi deploy done.", done.stdout)
        exits = [c for c in self.calls() if "-O exit" in c]
        self.assertEqual(2, len(exits), self.calls())
        sockets = self.sockets()
        self.assertTrue(exits[0].endswith(f"-O exit {PI}") and f"ControlPath={sockets['pi']}" in exits[0], exits)
        self.assertTrue(exits[1].endswith(f"-p 1 -O exit nobody@{WIN}")
                        and f"ControlPath={sockets['win']}" in exits[1], exits)
        self.assertFalse(sockets["pi"].parent.exists())

    def test_a_stopped_run_removes_the_folder_too(self) -> None:
        self.down(WIN)
        done = self.deploy("--pi", "--win")
        self.assertIn(WIN_DOWN, done.stderr)
        sockets = self.sockets()
        self.assertEqual({"pi", "win"}, set(sockets), self.calls())
        self.assertFalse(sockets["pi"].parent.exists())

    def test_hart_ssh_mux_0_turns_reuse_off(self) -> None:
        self.env["HART_SSH_MUX"] = "0"
        self.env["HART_WIN_SSH_MUX"] = "1"
        done = self.deploy("--pi", "--win")
        self.assertIn("Pi deploy done.", done.stdout)
        self.assertEqual(set(), self.control_paths())

    def test_hart_win_ssh_mux_0_turns_reuse_off_for_windows_only(self) -> None:
        self.env["HART_WIN_SSH_MUX"] = "0"
        (self.tmp / "mksock").touch()
        done = self.deploy("--pi", "--win")
        self.assertIn("Pi deploy done.", done.stdout)
        self.assertEqual({"pi"}, set(self.sockets()), self.calls())
        win = [c for c in self.calls() if WIN in c]
        self.assertTrue(win and not any("Control" in c for c in win), win)
        # Windows alone: no socket folder at all.
        (self.tmp / "network.log").unlink()
        done = self.deploy("--win")
        self.assertIn("Deploy → Windows", done.stdout)
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
        # Every Windows call, the scp too, went over the Windows socket.
        win = [c for c in self.calls() if WIN in c]
        sock = self.sockets()["win"]
        self.assertTrue(any(c.startswith("scp ") for c in win), win)
        self.assertTrue(all(f"ControlPath={sock}" in c for c in win), win)
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
        sockets = self.sockets()
        self.assertEqual({"pi", "win"}, set(sockets), self.calls())
        self.assertTrue(str(sockets["pi"]).startswith("/tmp/hart-ssh."), self.calls())

    def test_windows_alone_failing_does_not_mention_the_pi(self) -> None:
        done = self.deploy("--win")
        self.assertEqual(99, done.returncode, done.stderr[-2000:])
        self.assertNotIn("The Pi has this deploy", done.stderr)
        sockets = self.sockets()
        self.assertEqual({"win"}, set(sockets), self.calls())
        self.assertFalse(sockets["win"].parent.exists())


if __name__ == "__main__":
    unittest.main()
