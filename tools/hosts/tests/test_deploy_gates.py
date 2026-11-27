"""The order of gates and ship steps of the deploy (tools/hosts/sync_hart_package.sh and the steps in tools/hosts/deploy/).

WHY: a failed gate must leave every host and the Mac as they were, and a one-host retry must not repeat the whole
run. The deploy was one script that checked while it shipped; it is now a gate step, one staging step and one ship
step per host. These tests pin the order and that nothing ships before every check has passed.

MAP, in the order it runs (entry point = tools/hosts/sync_hart_package.sh):

  Entry point    reads the flags (--pi --win --all --dry-run --stage-only --check-only ...), --stage-only needs an
                 empty folder and sets DRY_RUN=1, takes the stamp facts once, opens the ssh sockets (a folder of
                 sockets, closed by its EXIT trap), then runs the steps below.

  gate.sh        nothing is sent or installed by any of it
    G0           refuse_hart_tables, refuse_unrestored_profile, the parked features (hartlib.parked), the live
                 paths list (not for --check-only/--dry-run)                     needs: env, local files, python3
    G0b, G0c     the commit is origin/main (check_on_main); main's push run for it is not red (ci_pass.py
                 --main-red; a dry run asks too)                                 needs: git, gh
    G1           preflight_hosts: one ssh no-op to each host named               needs: ssh (skipped by --dry-run, --stage-only)
    G2           the Pi's unpulled check (Operations Pro files, Store); pi_stop starts PanelPro again; only with
                 --pi; HART_DISCARD_PI_CHANGES=1 skips it. --check-only stops after it.
    G3           audit_panel_contracts.py --strict                               needs: schematic-maps plugin
    G4           build_tables.py --check (not on a redeploy, nor on a real host deploy that CI's full pass
                 covers: ci_pass.py); exit 3/2/other
    G5           disable_digicon_sml_in_tables.py --check
    G6           the Mac's own Store check ("tables.xml changed since the last deploy (a PanelPro Store)"), for a run
                 that installs on the Mac (was inside the Mac install, after it had begun)
    G7           a trial staging into a folder that is thrown away: the package builds (was after the Mac install)
    G8           Windows can take the package: scp and tar and a temp file here, a temp folder and tar there through
                 one read-only ssh probe (was after the Pi step was done)
  stage.sh       builds DIR/pi and DIR/win once                                  needs: local files, rsync, python3
  ship_mac.sh    the Mac install (web override, tables, ops, panels, CTC icons, jython, stamp); with any host flag,
                 and with no flag at all (the Mac only)
  ship_pi.sh     ssh mktemp, rsync, ssh apply, restart check
  ship_win.sh    the Windows step: tarball, ssh mktemp, scp, ssh unpack, ssh apply, ssh cleanup

THE OPERATING FLAG is not in the scripts: .claude/hooks/main_guard.py refuses a command whose program is
sync_hart_package.sh or redeploy_commit.sh with --pi/--win/--all, gate.sh with --pi/--win, ship_pi.sh or ship_win.sh,
or a make deploy target. A new step name is not covered until the hook's program list names it.

Everything below runs with ssh, scp, rsync-to-a-host and tar as recorders on PATH (the hosts are example.invalid
names) and a temporary HOME; nothing reaches a host, and nothing publishes MQTT.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_preflight import FAKE_RSYNC, PI, ROOT, SYNC, WIN, DeployHarness  # noqa: E402
from test_deploy_stage import stage_env  # noqa: E402

REDEPLOY = ROOT / "tools/hosts/redeploy_commit.sh"

sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
HOOK = ROOT / ".claude/hooks/main_guard.py"
OPERATING = ROOT / "tools/hosts/operating.sh"
# Read-only ssh calls a gate step may make: the no-ops, the unpulled check, the restart check.
READ_ONLY_COMMANDS = ("true", "exit 0", "bash -s")
UNPULLED_PREFIX = "bash -s -- '"
# The Windows probe (gate.sh): makes and removes a temp folder and looks for tar; it names itself with this.
WIN_PROBE = "hart-probe-"


def is_read_only(call: str) -> bool:
    """Whether a logged ssh call ran exactly one of the read-only remote commands. The log line is
    "ssh <options> <host> <command>": the command is what follows the host name."""
    if not call.startswith("ssh "):
        return False
    for host in (PI, f"nobody@{WIN}"):
        if f" {host} " in call:
            command = call.split(f" {host} ", 1)[1]
            return command in READ_ONLY_COMMANDS or command.startswith(UNPULLED_PREFIX) or WIN_PROBE in command
    raise AssertionError(f"an ssh call to no known host: {call}")


def git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return env


def git_in(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args], env=git_env(),
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


def throwaway_repo(path: Path) -> Path:
    """A repo with one commit and refs/remotes/origin/main on it."""
    path.mkdir(parents=True)
    git_in(path, "init", "-q", "-b", "main")
    git_in(path, "commit", "-q", "--allow-empty", "-m", "first")
    git_in(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return path


def add_worktree(repo: Path, path: Path, branch: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    git_in(repo, "worktree", "add", "-q", "-b", branch, str(path))
    git_in(path, "commit", "-q", "--allow-empty", "-m", "an auto-pull")


def wrapper(tmp: Path, real: Path) -> None:
    """A python3 in front of the harness one that fails a named step while its marker file exists, and
    otherwise hands over to the harness python3 (the tables and Digicon stand-ins)."""
    tool = tmp / "bin2/python3"
    tool.parent.mkdir()
    tool.write_text(f"""#!/bin/bash
for a in "$@"; do
  case "$a" in
    hartlib.parked) [[ ! -f "{tmp}/fail_parked" ]] || {{ echo "stand-in: parked features unreadable" >&2; exit 1; }} ;;
    */audit_panel_contracts.py) [[ ! -f "{tmp}/fail_audit" ]] || {{ echo "stand-in: panel audit failed" >&2; exit 1; }} ;;
    */live_paths.py) [[ ! -f "{tmp}/fail_live_paths" ]] || {{ echo "stand-in: live path gone" >&2; exit 1; }} ;;
    */build_mimic_web.py) echo build >>"{tmp}/builds.log"; [[ ! -f "{tmp}/fail_stage" ]] || {{ echo "stand-in: staging failed" >&2; exit 1; }} ;;
  esac
done
exec "{real}" "$@"
""", encoding="utf-8")
    tool.chmod(0o755)


class GateHarness(DeployHarness):
    """DeployHarness plus recorders: rsync to a host, scp and tar log to network.log / ship.log; the Pi's
    unpulled check answers what unpulled.txt holds (or fails while unpulled_fail exists); the Pi and Windows
    apply steps succeed after hosts_ok()."""

    def setUp(self) -> None:
        super().setUp()
        wrapper(self.tmp, self.tmp / "bin/python3")
        self.env["PATH"] = f"{self.tmp / 'bin2'}{os.pathsep}{self.env['PATH']}"
        rsync, tar = shutil.which("rsync"), shutil.which("tar")
        for name, path in (("rsync", rsync), ("tar", tar)):
            if not path:
                raise RuntimeError(f"{name} is not on PATH: the deploy staging tests need it")
        bins = self.tmp / "bin"
        (bins / "rsync").write_text(FAKE_RSYNC.replace("@TMP@", str(self.tmp)).replace("@RSYNC@", rsync),
                                    encoding="utf-8")
        (bins / "tar").write_text(f'#!/bin/bash\necho "tar $*" >>"{self.tmp}/ship.log"\nexec "{tar}" "$@"\n',
                                  encoding="utf-8")
        (bins / "scp").write_text(f'#!/bin/sh\necho "scp $*" >>"{self.tmp}/network.log"\nexit 0\n', encoding="utf-8")
        # the unpulled check prints what unpulled.txt holds (ops, tables)
        ssh = (bins / "ssh").read_text(encoding="utf-8")
        old = '''"bash -s -- '"*) cat >/dev/null; exit 0 ;;'''
        if old not in ssh:
            raise RuntimeError("the preflight ssh stand-in (test_deploy_preflight.FAKE_SSH) changed: update this test")
        ssh = ssh.replace(old, f'''"bash -s -- '"*) cat >/dev/null; [[ ! -f "{self.tmp}/unpulled_fail" ]] || exit 5; '''
                               f'''cat "{self.tmp}/unpulled.txt" 2>/dev/null; exit 0 ;;''')
        (bins / "ssh").write_text(ssh, encoding="utf-8")
        for name in ("rsync", "tar", "scp", "ssh"):
            (bins / name).chmod(0o755)
        self.autopull_stubs()

    def autopull_stubs(self) -> None:
        """The gate's own pulls (common.sh autopull_pi_changes) run stand-ins that log to autopull.log and fail
        while fail_<name> exists: quit, tables (prints the pull's own "Pulled" line), ops (logs its folder) and the
        worktree maker (prints a folder made here)."""
        d = self.tmp / "autopull"
        d.mkdir()
        log = self.tmp / "autopull.log"
        t = self.tmp
        (d / "quit.sh").write_text(f'echo "quit $*" >>"{log}"\n[[ ! -f "{t}/fail_quit" ]] || exit 4\n', encoding="utf-8")
        (d / "tables.sh").write_text(
            f'echo "tables" >>"{log}"\n[[ ! -f "{t}/fail_tables" ]] || {{ echo "ssh dropped" >&2; exit 1; }}\n'
            'echo "Pulled: the Pi\'s Store is kept as /pulled/pi-20261121.xml (outside every checkout), '
            'its base (abc) in /pulled/pi-20261121.xml.base."\n', encoding="utf-8")
        (d / "ops.sh").write_text(
            f'echo "ops in $(pwd) $*" >>"{log}"\n[[ ! -f "{t}/fail_ops" ]] || {{ echo "scp dropped" >&2; exit 1; }}\n'
            'echo "Operations files -> $(pwd)/jmri/layouts/hart/operations. Commit any changes."\n', encoding="utf-8")
        (d / "newwt.sh").write_text(
            f'echo "newwt $1" >>"{log}"\n[[ ! -f "{t}/fail_newwt" ]] || exit 1\n'
            f'mkdir -p "{t}/wt/$1" && echo "{t}/wt/$1"\n', encoding="utf-8")
        (d / "rmwt.sh").write_text(f'echo "rmwt $2" >>"{log}"\nrm -rf "$1"\n', encoding="utf-8")
        self.env.update(HART_AUTOPULL_RMWT=str(d / "rmwt.sh"), HART_AUTOPULL_WT_DIR=str(t / "wt"),
                        HART_AUTOPULL_QUIT=str(d / "quit.sh"), HART_AUTOPULL_TABLES=str(d / "tables.sh"),
                        HART_AUTOPULL_OPS=str(d / "ops.sh"), HART_AUTOPULL_NEWWT=str(d / "newwt.sh"),
                        HART_AUTOPULL_FROM_MAIN="0", HART_AUTOPULL_DETACHED="0")
        del self.env["HART_NO_AUTOPULL"]

    def autopull_log(self) -> list[str]:
        log = self.tmp / "autopull.log"
        return log.read_text().splitlines() if log.exists() else []

    def hosts_ok(self) -> None:
        """Both hosts take the package and their apply steps succeed (the folder cleanup on Windows fails, as in
        the preflight tests, which is only a warning)."""
        (self.tmp / "pi_ok").touch()
        (self.tmp / "win_ok").touch()
        (self.tmp / "win_apply_rc").write_text("0\n", encoding="utf-8")

    def unpulled(self, *what: str) -> None:
        (self.tmp / "unpulled.txt").write_text("".join(f"{w}\n" for w in what), encoding="utf-8")

    def ship_log(self) -> list[str]:
        log = self.tmp / "ship.log"
        return log.read_text().splitlines() if log.exists() else []

    def shipped(self) -> list[str]:
        """Everything that is not a read-only gate call: any other ssh, an rsync to a host, scp or the tarball."""
        sent = [c for c in self.calls()
                if c.startswith(("rsync ", "scp ")) or (c.startswith("ssh ") and not is_read_only(c))]
        return sent + self.ship_log()

    def mac_installed(self) -> bool:
        return (self.tmp / "home/JMRI_UserFiles/cats/deploy_stamp.txt").exists()

    def assert_nothing_shipped(self, done: subprocess.CompletedProcess, *, mac: bool = False) -> None:
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertEqual([], self.shipped(), self.calls())
        self.assertNotIn("Deploy →", done.stdout)
        self.assertEqual(mac, self.mac_installed(), "the Mac install " + ("did not run" if mac else "ran"))
        self.assertEqual([], sorted(p.name for p in self.scratch.iterdir()), "staging or tarball left behind")


class EveryGateStopsBeforeAnythingShips(GateHarness):
    """A failed gate leaves the hosts, the Mac and the scratch folder as they were: no ssh beyond the read-only
    checks, no rsync, scp or tar, no Mac install."""

    def stops(self, marker: str, text: str, *flags: str) -> None:
        (self.tmp / marker).touch()
        done = self.deploy(*(flags or ("--pi", "--win")))
        self.assertIn(text, done.stderr)
        self.assert_nothing_shipped(done)

    def test_tables_not_what_the_generator_writes(self) -> None:
        self.stops("tables_stale", "STOP: tables.xml is not what tools/schematic/build_tables.py writes")

    def test_tables_check_needs_the_plugin(self) -> None:
        self.stops("tables_no_plugin", "STOP: the tables check needs the schematic-maps plugin")

    def test_tables_source_error(self) -> None:
        self.stops("tables_source_error", "cannot make tables.xml from its sources")

    def test_digicon_destination_enabled(self) -> None:
        self.stops("digicon_enabled", "STOP: a Digicon mast's Signal Mast Logic is stored enabled")

    def test_panel_audit_failure(self) -> None:
        self.stops("fail_audit", "stand-in: panel audit failed")

    def test_unreadable_parked_features_stop_before_any_ssh(self) -> None:
        self.stops("fail_parked", "cannot read the parked features")
        self.assertEqual([], self.calls(), "the script asked a host before it knew what is parked")

    def test_a_missing_live_path_stops_before_any_ssh(self) -> None:
        self.stops("fail_live_paths", "stand-in: live path gone")
        self.assertEqual([], self.calls())

    def test_the_gates_also_stop_a_single_host_and_the_mac_only_run(self) -> None:
        for flags in (("--pi",), ("--win",), ()):
            with self.subTest(flags=flags):
                (self.tmp / "tables_stale").touch()
                done = self.deploy(*flags)
                self.assertIn("STOP: tables.xml is not what", done.stderr)
                self.assert_nothing_shipped(done)

    def test_stage_only_runs_the_local_gates_and_builds_nothing_when_one_fails(self) -> None:
        (self.tmp / "tables_stale").touch()
        stage = self.tmp / "stage"
        done = self.deploy("--pi", "--win", "--stage-only", str(stage))
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertIn("STOP: tables.xml is not what", done.stderr)
        self.assertFalse(stage.exists() and any(stage.iterdir()), "a package was built after a failed gate")
        self.assertEqual([], self.calls())

    def test_the_host_gates_run_before_the_local_gates(self) -> None:
        """Order: ssh no-ops, then the Pi's unpulled check, then the local gates. A stale tables.xml is not
        reported while the Pi has a Store, and an unreachable host hides every local gate."""
        (self.tmp / "tables_stale").touch()
        self.unpulled("tables")
        done = self.deploy("--pi", "--win")
        self.assertIn("kept the Pi's Store as", done.stderr)
        self.assertNotIn("is not what tools/schematic/build_tables.py writes", done.stderr)
        self.assertFalse((self.tmp / "tables_check.log").exists())
        self.assert_nothing_shipped(done)
        (self.tmp / "unpulled.txt").unlink()
        self.down(WIN)
        done = self.deploy("--pi", "--win")
        self.assertIn("STOP: cannot reach Windows", done.stderr)
        self.assertFalse((self.tmp / "tables_check.log").exists())


class G4TrustsCiPass(GateHarness):
    """G4 (build_tables.py --check) is skipped only when ci_pass.py says CI's full check.sh pass covers the commit
    shipped, and only for a real deploy to a host; G4b and G5 run either way, and the gate says which way G4 went.
    ci_pass.py's own decision is tested in test_ci_pass.py; here the python3 stand-in answers for it."""

    def test_a_ci_pass_skips_the_regeneration_and_g5_still_runs(self) -> None:
        for marker in ("ci_pass_skip", "tables_stale", "digicon_enabled"):
            (self.tmp / marker).touch()
        done = self.deploy("--pi", "--win")
        self.assertIn("skipped G4: CI full pass for", done.stdout)
        self.assertFalse((self.tmp / "tables_check.log").exists(), "G4 regenerated tables.xml after a CI pass")
        self.assertIn("STOP: a Digicon mast's Signal Mast Logic is stored enabled", done.stderr)
        self.assert_nothing_shipped(done)
        self.assertIn("--commit", (self.tmp / "ci_pass.log").read_text())

    def test_no_ci_pass_runs_g4_and_says_why(self) -> None:
        """The real ci_pass.py against the gh stand-in, which fails: G4 runs and stops the stale file."""
        (self.tmp / "tables_stale").touch()
        done = self.deploy("--pi", "--win")
        self.assertRegex(done.stdout, r"ran G4: (CI stamps unreadable|no CI pass|the checkout cannot be read) for [0-9a-f]{12}: ")
        self.assertIn("STOP: tables.xml is not what tools/schematic/build_tables.py writes", done.stderr)
        self.assertNotIn("Traceback", done.stdout + done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_crashed_check_runs_g4(self) -> None:
        for marker in ("ci_pass_crash", "tables_stale"):
            (self.tmp / marker).touch()
        done = self.deploy("--pi", "--win")
        self.assertIn("ran G4: the CI pass check failed (exit 7)", done.stdout)
        self.assertIn("STOP: tables.xml is not what", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_silent_no_still_says_g4_ran(self) -> None:
        for marker in ("ci_pass_silent", "tables_stale"):
            (self.tmp / marker).touch()
        done = self.deploy("--pi", "--win")
        self.assertIn("ran G4: the CI pass check said no and gave no reason (exit 1)", done.stdout)
        self.assertIn("STOP: tables.xml is not what", done.stderr)
        self.assert_nothing_shipped(done)


class OnlyMergedCommitsShip(GateHarness):
    """G0b (check_on_main, common.sh): a real deploy to a host ships a commit on origin/main, as a rollback does.
    HART_MAIN_REF=HEAD~1 stands in for an origin/main the checkout's HEAD is not on (CI fetches two commits)."""

    def test_a_commit_not_on_main_stops_before_any_ssh(self) -> None:
        self.env["HART_MAIN_REF"] = "HEAD~1"
        for flags in (("--pi",), ("--win",), ("--pi", "--win")):
            with self.subTest(flags=flags):
                done = self.deploy(*flags)
                self.assertIn("is not on origin/main", done.stderr)
                self.assertIn("HART_ALLOW_UNMERGED=1", done.stderr)
                self.assert_nothing_shipped(done)
                self.assertEqual([], self.calls())

    def test_no_main_ref_stops(self) -> None:
        self.env["HART_MAIN_REF"] = "refs/remotes/nowhere/main"
        done = self.deploy("--pi", "--win")
        self.assertIn("STOP: no refs/remotes/nowhere/main here", done.stderr)
        self.assert_nothing_shipped(done)

    def test_the_override_ships_and_says_so(self) -> None:
        self.env.update(HART_MAIN_REF="HEAD~1", HART_ALLOW_UNMERGED="1")
        self.hosts_ok()
        done = self.deploy("--pi", "--win")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertIn("HART_ALLOW_UNMERGED=1: deploying", done.stderr)
        self.assertIn("Windows deploy done.", done.stdout)
        self.assertIn("Pi deploy done.", done.stdout)

    def test_a_commit_behind_main_stops_and_names_the_rollback(self) -> None:
        """A merged but older commit (a stale main checkout) would roll the hosts back: it stops too. The newer
        origin/main is a commit on top of HEAD, made with fixed dates so every run makes the same object."""
        env = dict(git_env(), GIT_AUTHOR_DATE="2026-01-01T00:00:00Z", GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")
        newer = subprocess.run(["git", "-C", str(ROOT), "commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "newer main"],
                               env=env, capture_output=True, text=True, check=True).stdout.strip()
        self.env["HART_MAIN_REF"] = newer
        done = self.deploy("--pi", "--win")
        self.assertIn("is behind origin/main", done.stderr)
        self.assertIn("redeploy_commit.sh", done.stderr)
        self.assert_nothing_shipped(done)

    def test_dry_run_and_check_only_get_past_it(self) -> None:
        self.env["HART_MAIN_REF"] = "HEAD~1"
        self.hosts_ok()
        for flags in (("--pi", "--win", "--dry-run"), ("--check-only", "--pi", "--win")):
            with self.subTest(flags=flags):
                done = self.deploy(*flags)
                self.assertEqual(0, done.returncode, done.stderr[-2000:])
                self.assertNotIn("origin/main", done.stderr)

    def test_a_ship_step_run_alone_checks_it_too(self) -> None:
        self.env["HART_MAIN_REF"] = "HEAD~1"
        self.hosts_ok()
        for script in ("ship_pi.sh", "ship_win.sh"):
            with self.subTest(script=script):
                folder = self.tmp / "staged" / script
                folder.mkdir(parents=True)
                (folder / "tables.xml").write_text("<x/>\n", encoding="utf-8")
                done = subprocess.run(["bash", str(ROOT / "tools/hosts/deploy" / script), str(folder)], cwd=ROOT,
                                      env=self.env, capture_output=True, text=True, timeout=300)
                self.assertEqual(1, done.returncode, done.stderr[-1500:])
                self.assertIn("is not on origin/main", done.stderr)
                self.assertEqual([], self.calls())


class PiChangedSinceLastDeploy(GateHarness):
    """The Pi's Operations Pro files or tables.xml changed since the last deploy or pull: stop before anything
    is sent, and name the way out. HART_NO_AUTOPULL=1 here: the plain stop (the gate's own pull is below)."""

    def setUp(self) -> None:
        super().setUp()
        self.env["HART_NO_AUTOPULL"] = "1"

    def test_operations_files_changed(self) -> None:
        self.unpulled("ops")
        done = self.deploy("--pi", "--win")
        self.assertIn("make ops-pull", done.stderr)
        self.assertNotIn("make tables-pull-pi", done.stderr)
        self.assertIn("HART_DISCARD_PI_CHANGES=1 replaces them anyway.", done.stderr)
        self.assert_nothing_shipped(done)
        # Windows was asked for its no-op only, and the gate ran before the local ones.
        self.assertEqual(["exit 0"], [c.split(f"{WIN} ", 1)[1] for c in self.calls() if f"{WIN} " in c])
        self.assertFalse((self.tmp / "tables_check.log").exists())

    def test_the_store_changed(self) -> None:
        self.unpulled("tables")
        done = self.deploy("--pi")
        self.assertIn("STOP: the Pi's tables.xml changed since the last deploy (a PanelPro Store)", done.stderr)
        self.assertNotIn("make ops-pull", done.stderr)
        self.assert_nothing_shipped(done)

    def test_both_changed_name_both(self) -> None:
        self.unpulled("ops", "tables")
        done = self.deploy("--pi", "--win")
        self.assertIn("make ops-pull", done.stderr)
        self.assertIn("make tables-pull-pi", done.stderr)
        self.assert_nothing_shipped(done)

    def test_the_stop_starts_panelpro_again_when_it_was_quit_for_the_deploy(self) -> None:
        self.unpulled("ops")
        (self.tmp / "restart.txt").write_text("yes\n", encoding="utf-8")
        done = self.deploy("--pi")
        self.assertIn("Starting PanelPro on the Pi again (it was quit for this deploy)", done.stdout)
        self.assertEqual(1, done.returncode, done.stderr)

    def test_only_a_pi_deploy_asks(self) -> None:
        self.unpulled("ops", "tables")
        self.hosts_ok()
        done = self.deploy("--win")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertFalse(any("bash -s --" in c for c in self.calls()), self.calls())
        self.assertIn("Windows deploy done.", done.stdout)

    def test_discarding_goes_on_to_ship_to_both(self) -> None:
        self.unpulled("ops", "tables")
        self.hosts_ok()
        self.env["HART_DISCARD_PI_CHANGES"] = "1"
        done = self.deploy("--pi", "--win")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertFalse(any("bash -s --" in c for c in self.calls()), self.calls())
        self.assertIn("Pi deploy done.", done.stdout)
        self.assertIn("Windows deploy done.", done.stdout)

    def test_a_failed_check_stops_too(self) -> None:
        """The check itself failing (ssh drops) is a stop with its own text, not a pass."""
        (self.tmp / "unpulled_fail").touch()
        done = self.deploy("--pi")
        self.assertIn("STOP: could not check the Pi for unpulled changes", done.stderr)
        self.assert_nothing_shipped(done)


class PiChangesAreSavedByTheGate(GateHarness):
    """T9a: a changed Pi Store or Operations session is pulled by the gate (the same scripts a person runs), and the
    deploy still stops with nothing shipped."""

    def test_the_store_is_kept_then_the_deploy_stops(self) -> None:
        self.unpulled("tables")
        done = self.deploy("--pi", "--win")
        self.assertEqual(["tables"], self.autopull_log(), "a Store pull needs no PanelPro quit")
        self.assertIn("kept the Pi's Store as /pulled/pi-20261121.xml; split it "
                      "(python3 tools/schematic/split_store.py /pulled/pi-20261121.xml), merge, then deploy", done.stderr)
        self.assertNotIn("brought the Pi's Operations", done.stderr)
        self.assert_nothing_shipped(done)

    def test_operations_are_pulled_into_this_checkout_from_a_worktree(self) -> None:
        self.unpulled("ops")
        done = self.deploy("--pi")
        self.assertEqual(["quit --for-deploy", f"ops in {ROOT} --no-mark"], self.autopull_log())
        self.assertIn(f"brought the Pi's Operations session into {ROOT}/jmri/layouts/hart/operations; "
                      "review, commit and merge it, then deploy", done.stderr)
        self.assert_nothing_shipped(done)

    def test_from_the_main_checkout_operations_go_to_a_new_worktree(self) -> None:
        self.env["HART_AUTOPULL_FROM_MAIN"] = "1"
        self.unpulled("ops")
        done = self.deploy("--pi")
        log = self.autopull_log()
        self.assertRegex(log[1], r"^newwt ops-pull-\d{8}-\d{6}$")
        wt = self.tmp / "wt" / log[1].split()[1]
        self.assertEqual(f"ops in {wt} --no-mark", log[2])
        self.assertIn(f"into {wt}/jmri/layouts/hart/operations", done.stderr)
        self.assert_nothing_shipped(done)

    def test_both_are_saved_and_both_named(self) -> None:
        self.unpulled("ops", "tables")
        done = self.deploy("--pi", "--win")
        self.assertEqual(["tables", "quit --for-deploy", f"ops in {ROOT} --no-mark"], self.autopull_log())
        self.assertIn("kept the Pi's Store as", done.stderr)
        self.assertIn("brought the Pi's Operations session into", done.stderr)
        self.assert_nothing_shipped(done)

    def test_no_autopull_is_the_plain_stop(self) -> None:
        self.env["HART_NO_AUTOPULL"] = "1"
        self.unpulled("ops", "tables")
        done = self.deploy("--pi")
        self.assertEqual([], self.autopull_log())
        self.assertIn("make ops-pull", done.stderr)
        self.assertIn("make tables-pull-pi", done.stderr)
        self.assert_nothing_shipped(done)

    def test_discarding_pulls_nothing(self) -> None:
        self.unpulled("ops", "tables")
        self.hosts_ok()
        self.env["HART_DISCARD_PI_CHANGES"] = "1"
        done = self.deploy("--pi", "--win")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertEqual([], self.autopull_log())

    def test_a_failed_store_pull_says_nothing_was_kept(self) -> None:
        (self.tmp / "fail_tables").touch()
        self.unpulled("tables")
        done = self.deploy("--pi")
        self.assertIn("STOP: the pull failed. the pull of the Pi's Store failed; nothing was kept for it", done.stderr)
        self.assertNotIn("kept the Pi's Store as", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_failed_operations_pull_says_nothing_was_kept(self) -> None:
        (self.tmp / "fail_ops").touch()
        self.unpulled("ops")
        done = self.deploy("--pi")
        self.assertIn("the pull of the Pi's Operations files failed (see above); nothing was kept for them", done.stderr)
        self.assertNotIn("brought the Pi's Operations", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_failed_worktree_stops_without_pulling(self) -> None:
        self.env["HART_AUTOPULL_FROM_MAIN"] = "1"
        (self.tmp / "fail_newwt").touch()
        self.unpulled("ops")
        done = self.deploy("--pi")
        self.assertIn("could not make the worktree", done.stderr)
        self.assertFalse(any(c.startswith("ops in") for c in self.autopull_log()))
        self.assert_nothing_shipped(done)

    def test_a_failed_quit_pulls_nothing(self) -> None:
        (self.tmp / "fail_quit").touch()
        self.unpulled("ops", "tables")
        done = self.deploy("--pi")
        self.assertEqual(["tables", "quit --for-deploy"], self.autopull_log(), "the Store pull does not wait for the quit")
        self.assertIn("kept the Pi's Store as", done.stderr)
        self.assertIn("could not quit PanelPro on the Pi", done.stderr)
        self.assertIn("nothing was kept for the Operations files", done.stderr)
        self.assert_nothing_shipped(done)

    def test_one_failing_pull_still_reports_the_other_as_kept(self) -> None:
        (self.tmp / "fail_ops").touch()
        self.unpulled("ops", "tables")
        done = self.deploy("--pi")
        self.assertIn("kept the Pi's Store as", done.stderr)
        self.assertIn("nothing was kept for them", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_failed_operations_pull_removes_the_worktree_it_made(self) -> None:
        self.env["HART_AUTOPULL_FROM_MAIN"] = "1"
        (self.tmp / "fail_ops").touch()
        self.unpulled("ops")
        done = self.deploy("--pi")
        log = self.autopull_log()
        topic = log[1].split()[1]
        self.assertIn(f"rmwt {topic}", log)
        self.assertFalse((self.tmp / "wt" / topic).exists())
        self.assertIn(f"the new worktree {self.tmp}/wt/{topic} was removed", done.stderr)
        self.assert_nothing_shipped(done)

    def test_an_unmerged_ops_pull_worktree_is_reused(self) -> None:
        self.env["HART_AUTOPULL_FROM_MAIN"] = "1"
        repo = throwaway_repo(self.tmp / "repo")
        old = self.tmp / "wt" / "ops-pull-20261120-101010"
        add_worktree(repo, old, "agent/claude/ops-pull-20261120-101010")
        old = old.resolve()   # git lists real paths
        self.env["HART_AUTOPULL_WT_REPO"] = str(repo)
        self.unpulled("ops")
        done = self.deploy("--pi")
        self.assertEqual(["quit --for-deploy", f"ops in {old} --no-mark"], self.autopull_log())
        self.assertIn(f"into {old}/jmri/layouts/hart/operations", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_plain_folder_named_like_one_is_not_reused(self) -> None:
        self.env["HART_AUTOPULL_FROM_MAIN"] = "1"
        self.env["HART_AUTOPULL_WT_REPO"] = str(throwaway_repo(self.tmp / "repo"))
        (self.tmp / "wt" / "ops-pull-20261120-101010").mkdir(parents=True)
        self.unpulled("ops")
        self.deploy("--pi")
        self.assertRegex(self.autopull_log()[1], r"^newwt ops-pull-\d{8}-\d{6}$")

    def test_a_redeploy_never_pulls_into_its_throwaway_worktree(self) -> None:
        self.env["HART_REDEPLOY_FROM"] = "0123abc"
        self.unpulled("ops", "tables")
        done = self.deploy("--pi")
        self.assertEqual([], self.autopull_log())
        self.assertIn("make ops-pull", done.stderr)
        self.assertIn("make tables-pull-pi", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_detached_worktree_never_pulls_either(self) -> None:
        self.env["HART_AUTOPULL_DETACHED"] = "1"
        self.unpulled("ops")
        done = self.deploy("--pi")
        self.assertEqual([], self.autopull_log())
        self.assertIn("make ops-pull", done.stderr)
        self.assert_nothing_shipped(done)

    def test_the_gate_asks_with_the_hash_of_the_operations_files_it_would_ship(self) -> None:
        self.unpulled("ops")
        self.deploy("--pi")
        asks = [c for c in self.calls() if "bash -s -- '" in c]
        self.assertTrue(asks and " ops:" in asks[0], asks)


    def test_panelpro_comes_back_after_the_stop(self) -> None:
        self.unpulled("ops")
        (self.tmp / "restart.txt").write_text("yes\n", encoding="utf-8")
        done = self.deploy("--pi")
        self.assertIn("Starting PanelPro on the Pi again (it was quit for this deploy)", done.stdout)


class ReusableOpsPullWorktree(unittest.TestCase):
    """common.sh reusable_ops_pull_worktree against a real throwaway repo."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = throwaway_repo(self.tmp / "repo")
        self.dir = self.tmp / "wt"

    def pick(self) -> str:
        env = dict(git_env(), PATH=os.environ["PATH"], HOME=str(self.tmp), HART_ENV_FILE=str(self.tmp / "none"))
        done = subprocess.run(["bash", "-c", 'source "$1"; reusable_ops_pull_worktree "$2" "$3"', "x",
                               str(ROOT / "tools/hosts/deploy/common.sh"), str(self.repo), str(self.dir)],
                              env=env, capture_output=True, text=True, check=True)
        return done.stdout.strip()

    def test_an_unmerged_worktree_is_picked_and_a_merged_one_is_not(self) -> None:
        wt = self.dir / "ops-pull-20261120-101010"
        add_worktree(self.repo, wt, "agent/claude/ops-pull-20261120-101010")
        self.assertEqual(str(wt.resolve()), str(Path(self.pick()).resolve()))
        git_in(wt, "update-ref", "refs/remotes/origin/main", "HEAD")   # origin/main now holds its branch
        self.assertEqual("", self.pick())

    def test_the_newest_unmerged_one_wins(self) -> None:
        a, b = self.dir / "ops-pull-20261120-101010", self.dir / "ops-pull-20261121-101010"
        add_worktree(self.repo, a, "agent/claude/ops-pull-20261120-101010")
        add_worktree(self.repo, b, "agent/claude/ops-pull-20261121-101010")
        self.assertEqual(str(b.resolve()), str(Path(self.pick()).resolve()))

    def test_a_plain_folder_other_names_and_other_places_are_ignored(self) -> None:
        (self.dir / "ops-pull-20261120-101010").mkdir(parents=True)
        add_worktree(self.repo, self.dir / "other-task", "agent/claude/other-task")
        add_worktree(self.repo, self.tmp / "elsewhere" / "ops-pull-1", "agent/claude/ops-pull-1")
        self.assertEqual("", self.pick())

    def test_no_origin_main_means_no_reuse(self) -> None:
        add_worktree(self.repo, self.dir / "ops-pull-20261120-101010", "agent/claude/ops-pull-20261120-101010")
        git_in(self.repo, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual("", self.pick())


class WhatShipsWhere(GateHarness):
    """The ship steps: --pi --win ships both, each flag alone ships one, no flag is the Mac only."""

    def setUp(self) -> None:
        super().setUp()
        self.hosts_ok()

    def pi_pushes(self) -> list[str]:
        return [c for c in self.calls() if c.startswith("rsync ")]

    def pi_applies(self) -> list[str]:
        return [c for c in self.calls() if "apply_hart_package_local.sh" in c]

    def win_applies(self) -> list[str]:
        return [c for c in self.calls() if "apply_hart_package_local.ps1" in c]

    def scps(self) -> list[str]:
        return [c for c in self.calls() if c.startswith("scp ")]

    def test_pi_and_win_ship_both_pi_first_after_the_mac(self) -> None:
        done = self.deploy("--pi", "--win")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertEqual(1, len(self.pi_pushes()), self.calls())
        self.assertEqual(1, len(self.pi_applies()), self.calls())
        self.assertEqual(1, len(self.scps()), self.calls())
        self.assertEqual(1, len(self.win_applies()), self.calls())
        self.assertEqual(1, len(self.ship_log()), "one tarball for Windows")
        self.assertTrue(self.mac_installed())
        calls = self.calls()
        first_win_step = next(i for i, c in enumerate(calls) if WIN in c and not is_read_only(c))
        self.assertLess(calls.index(self.pi_applies()[0]), first_win_step, "Windows came before the Pi's apply")
        self.assertLess(done.stdout.index("Deploy → Pi"), done.stdout.index("Deploy → Windows"))
        self.assertTrue(done.stdout.rstrip().endswith("DONE"), done.stdout[-300:])
        # each host runs the apply step its package carries, into the user files stage_env names; the tarball is in TMPDIR
        pi, win = self.pi_applies()[0], self.win_applies()[0]
        self.assertRegex(pi, r" HART=/tmp/hart-deploy\.fake JMRI_USERFILES='/srv/fake-pi/JMRI_UserFiles' .* "
                             r"bash /tmp/hart-deploy\.fake/cats/scripts/pi/apply_hart_package_local\.sh$")
        self.assertIn('-File "C:\\Temp\\hart-deploy-fake\\cats\\scripts\\windows\\apply_hart_package_local.ps1" '
                      '-Hart "C:\\Temp\\hart-deploy-fake"', win)
        self.assertTrue(win.endswith('-UserFiles "X:/fake-win/JMRI_UserFiles"'), win)
        self.assertIn(f" {self.scratch}/hart-pkg.", self.scps()[0])
        self.assertEqual([], sorted(p.name for p in self.scratch.iterdir()))

    def test_all_is_pi_and_win(self) -> None:
        done = self.deploy("--all")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertIn("Pi deploy done.", done.stdout)
        self.assertIn("Windows deploy done.", done.stdout)

    def test_pi_alone_ships_only_the_pi(self) -> None:
        done = self.deploy("--pi")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertEqual(1, len(self.pi_pushes()))
        self.assertEqual(1, len(self.pi_applies()))
        self.assertFalse(any(WIN in c for c in self.calls()), self.calls())
        self.assertEqual([], self.scps())
        self.assertEqual([], self.ship_log(), "a Windows tarball was made for a Pi-only deploy")
        self.assertNotIn("Windows", done.stdout)
        self.assertTrue(self.mac_installed(), "a host flag also installs on the Mac")

    def test_win_alone_ships_only_windows(self) -> None:
        done = self.deploy("--win")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertFalse(any(PI in c for c in self.calls()), self.calls())
        self.assertEqual([], self.pi_pushes())
        self.assertEqual(1, len(self.scps()))
        self.assertEqual(1, len(self.win_applies()))
        self.assertNotIn("Pi deploy", done.stdout)
        self.assertTrue(self.mac_installed())

    def test_no_flag_is_the_mac_only(self) -> None:
        done = self.deploy()
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertEqual([], self.calls(), "a Mac-only deploy reached for a host")
        self.assertEqual([], self.ship_log())
        self.assertTrue(self.mac_installed())
        self.assertIn("deploy stamp ->", done.stdout)
        self.assertIn("target=mac", (self.tmp / "home/JMRI_UserFiles/cats/deploy_stamp.txt").read_text())

    def test_dry_run_installs_and_sends_nothing(self) -> None:
        done = self.deploy("--pi", "--win", "--dry-run")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertFalse(self.mac_installed())
        # the only network call is rsync -n (statistics, no copy); no apply, no scp
        self.assertEqual(1, len(self.pi_pushes()), self.calls())
        self.assertTrue(all(" -n " in c for c in self.pi_pushes()), self.pi_pushes())
        self.assertEqual([], self.scps())
        self.assertEqual([], self.pi_applies() + self.win_applies())
        self.assertEqual([], [c for c in self.calls() if c.startswith("ssh ")])

    def test_a_pi_failure_stops_before_windows(self) -> None:
        (self.tmp / "pi_ok").unlink()
        done = self.deploy("--pi", "--win")
        self.assertNotEqual(0, done.returncode)
        self.assertFalse(any(WIN in c and not is_read_only(c) for c in self.calls()), self.calls())
        self.assertEqual([], self.ship_log())


class EveryCheckRunsBeforeAnythingShips(GateHarness):
    """The four gates that used to run after shipping had started (the Mac Store check, staging, Windows' scp, tar
    and temp folder, the operating flag) now run in the gate step: a failure leaves the Mac, the Pi and Windows as
    they were."""

    def mac_store(self) -> Path:
        uf = self.tmp / "home/JMRI_UserFiles"
        uf.mkdir(parents=True)
        (uf / "tables.xml").write_text("<!-- a Store the owner saved -->\n", encoding="utf-8")
        (uf / ".tables_deployed.sha256").write_text("0" * 64 + "\n", encoding="utf-8")
        return uf

    def mac_files(self) -> list[str]:
        home = self.tmp / "home"
        return sorted(str(p.relative_to(home)) for p in home.rglob("*")) if home.exists() else []

    def test_a_mac_store_stops_before_the_mac_install_begins(self) -> None:
        uf = self.mac_store()
        done = self.deploy("--pi", "--win")
        self.assertIn(f"STOP: {uf}/tables.xml changed since the last deploy (a PanelPro Store)", done.stderr)
        self.assert_nothing_shipped(done)
        self.assertEqual("<!-- a Store the owner saved -->\n", (uf / "tables.xml").read_text())
        self.assertEqual(["JMRI_UserFiles", "JMRI_UserFiles/.tables_deployed.sha256", "JMRI_UserFiles/tables.xml"],
                         self.mac_files(), "the Mac install began before the Store check")
        # the hosts are still asked first: both no-ops and the Pi's unpulled check ran before the Mac gate
        self.assertTrue(any(" bash -s -- '" in c for c in self.calls()), self.calls())

    def test_the_mac_store_gate_stops_a_mac_only_run_too(self) -> None:
        self.mac_store()
        done = self.deploy()
        self.assertEqual(1, done.returncode)
        self.assertIn("a PanelPro Store", done.stderr)
        self.assertEqual(3, len(self.mac_files()))

    def test_a_staging_failure_stops_before_the_mac_install(self) -> None:
        (self.tmp / "fail_stage").touch()
        done = self.deploy("--pi", "--win")
        self.assertIn("stand-in: staging failed", done.stderr)
        self.assert_nothing_shipped(done)
        self.assertEqual([], self.mac_files(), "the Mac install ran before the package was known to build")

    def test_a_windows_failure_stops_before_the_pi_is_touched(self) -> None:
        (self.tmp / "pi_ok").touch()          # the Pi would take the package; Windows fails the probe
        (self.tmp / "win_probe_fails").touch()
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertIn("STOP: Windows", done.stderr)
        self.assert_nothing_shipped(done)
        self.assertNotIn("Pi deploy done.", done.stdout)
        self.assertNotIn("The Pi has this deploy", done.stderr)
        self.assertEqual([], self.mac_files())

    def test_windows_without_tar_stops_before_anything_ships(self) -> None:
        self.hosts_ok()
        (self.tmp / "win_no_tar").touch()
        done = self.deploy("--pi", "--win")
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertIn("STOP: Windows", done.stderr)
        self.assertIn("tar", done.stderr)
        self.assert_nothing_shipped(done)
        self.assertEqual([], self.mac_files())

    def test_the_windows_probe_is_not_asked_of_a_pi_only_deploy(self) -> None:
        self.hosts_ok()
        done = self.deploy("--pi")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertFalse(any(WIN in c for c in self.calls()), self.calls())

    def test_a_passing_run_probes_windows_once_then_ships_in_order(self) -> None:
        self.hosts_ok()
        done = self.deploy("--pi", "--win")
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        calls = self.calls()
        probes = [i for i, c in enumerate(calls) if WIN_PROBE in c]
        self.assertEqual(1, len(probes), calls)
        first_pi_ship = next(i for i, c in enumerate(calls) if c.startswith("rsync "))
        self.assertLess(probes[0], first_pi_ship, "the Windows probe came after the Pi was shipped")
        self.assertLess(done.stdout.index("deploy stamp ->"), done.stdout.index("Deploy → Pi"))


class StepsRunAlone(GateHarness):
    """A step run on its own is as careful as the gate: ship_pi.sh and ship_win.sh repeat the host checks unless the
    entry point exported HART_GATED=1 after gate.sh passed; every changing step refuses first; the package is built
    once per run; what a step does comes from its flags, never from DO_PI, DO_WIN or DRY_RUN in the environment."""

    def step(self, script: str, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(ROOT / "tools/hosts/deploy" / script), *args], cwd=ROOT,
                              env={**self.env, **env}, capture_output=True, text=True, timeout=300)

    def staged(self, host: str) -> str:
        folder = self.tmp / "staged" / host
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "tables.xml").write_text("<x/>\n", encoding="utf-8")
        return str(folder)

    def builds(self) -> int:
        log = self.tmp / "builds.log"
        return len(log.read_text().splitlines()) if log.exists() else 0

    def test_ship_pi_alone_repeats_the_unpulled_check(self) -> None:
        self.hosts_ok()
        self.unpulled("ops")
        done = self.step("ship_pi.sh", self.staged("pi"))
        self.assertEqual(1, done.returncode, done.stderr[-1500:])
        self.assertIn("brought the Pi's Operations session into", done.stderr)
        self.assertEqual([], self.shipped(), self.calls())

    def test_ship_pi_alone_asks_the_pi_to_answer_first(self) -> None:
        self.hosts_ok()
        self.down(PI)
        done = self.step("ship_pi.sh", self.staged("pi"))
        self.assertEqual(1, done.returncode, done.stderr[-1500:])
        self.assertIn("STOP: cannot reach the Pi", done.stderr)
        self.assertEqual([], [c for c in self.calls() if c.startswith("rsync ")])

    def test_ship_pi_after_the_gate_does_not_ask_again(self) -> None:
        self.hosts_ok()
        self.unpulled("ops")
        done = self.step("ship_pi.sh", self.staged("pi"), HART_GATED="1")
        self.assertEqual(0, done.returncode, done.stderr[-1500:])
        self.assertFalse(any(c.endswith(f"{PI} true") or " bash -s -- '" in c for c in self.calls()), self.calls())

    def test_ship_win_alone_repeats_the_ssh_and_package_checks(self) -> None:
        self.hosts_ok()
        self.down(WIN)
        done = self.step("ship_win.sh", self.staged("win"))
        self.assertIn("STOP: cannot reach Windows", done.stderr)
        self.assertEqual(1, done.returncode)
        self.down()
        (self.tmp / "win_no_tar").touch()
        done = self.step("ship_win.sh", self.staged("win"))
        self.assertIn("STOP: Windows", done.stderr)
        self.assertEqual(1, done.returncode)
        self.assertEqual([], self.ship_log(), "a tarball was made")

    def test_ship_win_after_the_gate_does_not_ask_again(self) -> None:
        self.hosts_ok()
        done = self.step("ship_win.sh", self.staged("win"), HART_GATED="1")
        self.assertEqual(0, done.returncode, done.stderr[-1500:])
        self.assertFalse(any(WIN in c and ("exit 0" in c or WIN_PROBE in c) for c in self.calls()), self.calls())

    def test_ship_mac_alone_refuses_hart_tables(self) -> None:
        done = self.step("ship_mac.sh", HART_TABLES="/nowhere/tables.xml")
        self.assertEqual(1, done.returncode)
        self.assertIn("HART_TABLES is set", done.stderr)
        self.assertFalse((self.tmp / "home").exists(), "the Mac install began")

    def test_every_changing_step_refuses_hart_tables(self) -> None:
        for script, args in (("ship_pi.sh", ("PI",)), ("ship_win.sh", ("WIN",)), ("gate.sh", ())):
            with self.subTest(script=script):
                argv = [self.staged(a.lower()) for a in args]
                done = self.step(script, *argv, HART_TABLES="/nowhere/tables.xml")
                self.assertEqual(1, done.returncode)
                self.assertIn("HART_TABLES is set", done.stderr)
        self.assertEqual([], self.calls())

    def test_a_real_run_builds_the_package_once(self) -> None:
        self.hosts_ok()
        for flags in (("--pi", "--win"), ("--pi",), ("--win",)):
            (self.tmp / "builds.log").unlink(missing_ok=True)
            done = self.deploy(*flags)
            self.assertEqual(0, done.returncode, done.stderr[-1500:])
            self.assertEqual(1, self.builds(), flags)

    def test_a_dry_run_builds_it_once_too(self) -> None:
        done = self.deploy("--pi", "--win", "--dry-run")
        self.assertEqual(0, done.returncode, done.stderr[-1500:])
        self.assertEqual(1, self.builds())

    def test_stage_only_asks_for_no_scp_and_no_ssh(self) -> None:
        done = self.deploy("--win", "--stage-only", str(self.tmp / "stage"))
        self.assertEqual(0, done.returncode, done.stderr[-1500:])
        self.assertEqual([], self.calls())

    def test_an_exported_dry_run_or_host_flag_changes_nothing(self) -> None:
        self.hosts_ok()
        done = self.step("gate.sh", "--pi", DRY_RUN="1")
        self.assertEqual(0, done.returncode, done.stderr[-1500:])
        self.assertTrue(any(c.endswith(f"{PI} true") for c in self.calls()), "the gate took the exported DRY_RUN")
        (self.tmp / "network.log").unlink()
        done = self.step("gate.sh", DO_PI="1", DO_WIN="1")
        self.assertEqual(0, done.returncode, done.stderr[-1500:])
        self.assertEqual([], self.calls(), "the gate took the exported DO_PI and DO_WIN")


class ParkedFeaturesAreNotInstalled(GateHarness):
    """The parked skip list (hartlib.parked) also governs the Mac install; the host packages are pinned in
    test_deploy_stage and again here, so the split keeps one list for the gate and the ship steps."""

    def parked(self) -> set[str]:
        from hartlib import parked
        return set(parked.PARKED)

    def test_mac_install_skips_parked_folders_and_says_so(self) -> None:
        parked = self.parked()
        done = self.deploy()
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        home = self.tmp / "home/JMRI_UserFiles"
        self.assertEqual("dispatcher" in parked, "Dispatcher traininfo parked: not installed" in done.stdout)
        self.assertEqual("uss" in parked, "USS CTC icons parked: not installed" in done.stdout)
        self.assertEqual("dispatcher" not in parked, (home / "dispatcher").exists())
        self.assertEqual("uss" not in parked, (home / "ctc").exists())

    def test_the_package_leaves_parked_folders_out_for_both_hosts(self) -> None:
        parked = self.parked()
        out = self.tmp / "stage"
        done = self.deploy("--pi", "--win", "--stage-only", str(out))
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        for host in ("pi", "win"):
            self.assertEqual("dispatcher" not in parked, (out / host / "jmri/layouts/hart/dispatcher").exists())
            self.assertEqual("uss" not in parked, (out / host / "ctc").exists())


class OperatingFlagRefusal(unittest.TestCase):
    """Two guards: the main guard hook refuses an agent's command, and sync_hart_package.sh and redeploy_commit.sh
    refuse a real deploy to the Pi or Windows themselves, so one run from a terminal stops too (owner, 2026-11-23).
    A ship step split out under another name stays open to a host while the flag is set until the hook names it."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.flag = Path(tmp.name) / "operating"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("HART_", "CLAUDE_"))}
        # git only on PATH: no ssh, no MQTT tool can run from here
        self.env.update(HART_OPERATING_FLAG=str(self.flag), PATH="/usr/bin:/bin")

    def operating(self, *args: str) -> None:
        subprocess.run(["bash", str(OPERATING), *args], env=self.env, check=True, capture_output=True)

    def hook(self, command: str) -> subprocess.CompletedProcess:
        payload = json.dumps({"tool_input": {"command": command}, "cwd": str(ROOT)})
        return subprocess.run([sys.executable, str(HOOK)], input=payload, env=self.env,
                              capture_output=True, text=True, timeout=60)

    def deploy(self, script: Path, *args: str, **extra: str) -> subprocess.CompletedProcess:
        """Run a deploy script as the staging tests do (stage_env: hosts that cannot resolve, ssh and scp stubs that log
        to network.log and fail, no autopull), with a temporary HOME and this test's flag file. Nothing reaches a host."""
        tmp = Path(tempfile.mkdtemp(dir=self.flag.parent))
        env = dict(stage_env(tmp), HOME=str(tmp), HART_OPERATING_FLAG=str(self.flag), **extra)
        self.network_log = tmp / "network.log"
        return subprocess.run(["bash", str(script), *args], cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=300)

    def test_the_deploy_scripts_refuse_a_host_while_the_flag_is_set(self) -> None:
        self.operating("on", "ops session")
        for script, args in ((SYNC, ("--pi",)), (SYNC, ("--win",)), (SYNC, ("--all",)),
                             (REDEPLOY, ("HEAD", "--pi")), (REDEPLOY, ("HEAD", "--pi", "--win"))):
            with self.subTest(script=script.name, args=args):
                done = self.deploy(script, *args)
                self.assertEqual(3, done.returncode, done.stdout + done.stderr)
                self.assertIn("the operating flag is set", done.stderr)
                self.assertIn("ops session", done.stderr)
                self.assertFalse(self.network_log.exists(), "the refusal comes before any host is asked")

    def test_the_owner_override_and_the_read_only_runs_pass_the_flag(self) -> None:
        """HART_DEPLOY_WHILE_OPERATING=1, --dry-run and --check-only get past the flag; they stop later, at the stub
        ssh or another gate, never at the flag's refusal, and never reach a real host (stage_env)."""
        self.operating("on", "ops session")
        for script, args, extra in ((SYNC, ("--pi",), {"HART_DEPLOY_WHILE_OPERATING": "1"}),
                                    (SYNC, ("--pi", "--dry-run"), {}), (SYNC, ("--check-only", "--pi"), {}),
                                    (REDEPLOY, ("HEAD", "--pi", "--dry-run"), {})):
            with self.subTest(script=script.name, args=args, extra=extra):
                done = self.deploy(script, *args, **extra)
                self.assertNotIn("REFUSED: the operating flag", done.stderr)
                self.assertNotEqual(0, done.returncode, "a stub host cannot take a deploy: " + done.stdout + done.stderr)

    def test_deploys_to_a_host_are_refused_while_the_flag_is_set(self) -> None:
        self.operating("on", "ops session")
        for command in ("./tools/hosts/sync_hart_package.sh --pi --win", "tools/hosts/sync_hart_package.sh --pi",
                        "./tools/hosts/sync_hart_package.sh --win", "./tools/hosts/sync_hart_package.sh --all",
                        "make deploy-layout", 'make redeploy COMMIT=abc HOSTS="--pi --win"'):
            with self.subTest(command=command):
                done = self.hook(command)
                self.assertEqual(2, done.returncode, done.stdout + done.stderr)
                self.assertIn("the operating flag is set", done.stderr)
                self.assertIn("a deploy to the Pi or Windows", done.stderr)

    def test_the_split_deploy_scripts_are_refused_while_the_flag_is_set(self) -> None:
        """tools/hosts/deploy/: the ship steps for a host and the gate with a host flag name a host, whatever runs
        them. The Mac step, staging and a gate for the Mac stay open."""
        self.operating("on", "ops session")
        for command in ("./tools/hosts/deploy/ship_pi.sh /tmp/stage/pi", "bash tools/hosts/deploy/ship_win.sh /tmp/stage/win",
                        "tools/hosts/deploy/ship_pi.sh --dry-run /tmp/stage/pi",
                        "./tools/hosts/deploy/gate.sh --pi --win", "bash tools/hosts/deploy/gate.sh --win --dry-run",
                        "cd tools/hosts/deploy && ./ship_win.sh /tmp/stage/win"):
            with self.subTest(command=command):
                done = self.hook(command)
                self.assertEqual(2, done.returncode, done.stdout + done.stderr)
                self.assertIn("the operating flag is set", done.stderr)
        for command in ("./tools/hosts/deploy/ship_mac.sh", "./tools/hosts/deploy/stage.sh --pi --win /tmp/stage",
                        "./tools/hosts/deploy/gate.sh", "./tools/hosts/deploy/gate.sh --mac --dry-run"):
            with self.subTest(command=command):
                done = self.hook(command)
                self.assertEqual(0, done.returncode, done.stdout + done.stderr)

    def test_the_mac_only_deploy_stays_open_while_the_flag_is_set(self) -> None:
        self.operating("on", "ops session")
        done = self.hook("./tools/hosts/sync_hart_package.sh")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)

    def test_deploys_are_open_when_the_flag_is_clear(self) -> None:
        done = self.hook("./tools/hosts/sync_hart_package.sh --pi --win")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
