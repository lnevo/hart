"""tools/agent/housekeeping.py: the branch prune, the land job's sweep call, the launchd agent and make housekeeping.

Temporary repos stand in for hart; the sweep and prune scripts are stubs that write down how they were called, and
launchctl is never run."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/agent"))


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


HK = _load("hart_housekeeping_test", ROOT / "tools/agent/housekeeping.py")


def git(*args: str, cwd: str | Path) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


def new_repo(base: Path) -> Path:
    """A clone of a bare origin, on main with one commit."""
    origin, repo = base / "origin.git", base / "repo"
    git("init", "-q", "--bare", "-b", "main", str(origin), cwd=base)
    git("clone", "-q", str(origin), str(repo), cwd=base)
    git("config", "user.email", "t@example.invalid", cwd=repo)
    git("config", "user.name", "t", cwd=repo)
    git("checkout", "-q", "-b", "main", cwd=repo)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    return repo


class Branches(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.repo = new_repo(self.base)
        repo = self.repo
        git("branch", "agent/claude/merged", cwd=repo)                   # on origin/main already
        git("checkout", "-q", "-b", "agent/claude/unmerged", cwd=repo)
        git("commit", "-q", "--allow-empty", "-m", "work nowhere else", cwd=repo)
        git("checkout", "-q", "main", cwd=repo)
        git("worktree", "add", "-q", "-b", "agent/claude/in-tree", str(self.base / "in-tree"), cwd=repo)

    def branches(self) -> set[str]:
        return set(git("for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=self.repo).splitlines())

    def test_merged_deleted_unmerged_and_worktree_branches_kept(self) -> None:
        ok, lines = HK.prune_branches(self.repo, dry_run=False)
        self.assertTrue(ok, lines)
        self.assertEqual(self.branches(), {"main", "agent/claude/unmerged", "agent/claude/in-tree"})
        self.assertIn("deleted agent/claude/merged", lines)
        self.assertEqual(lines[-1], "branches: deleted 1, refused 0, kept 1 merged ones a worktree has out")

    def test_dry_run_deletes_nothing(self) -> None:
        before = self.branches()
        ok, lines = HK.prune_branches(self.repo, dry_run=True)
        self.assertTrue(ok)
        self.assertEqual(self.branches(), before)
        self.assertEqual(lines, ["would delete agent/claude/merged",
                                 "branches: would delete 1, keep 1 merged ones a worktree has out"])

    def test_a_refusal_is_a_line_and_the_branch_stays(self) -> None:
        # merged into origin/main, but the main checkout's main lags it and the branch has no upstream: -d refuses
        git("commit", "-q", "--allow-empty", "-m", "newer main", cwd=self.repo)
        git("push", "-q", "origin", "main", cwd=self.repo)
        git("branch", "agent/claude/lagging", cwd=self.repo)
        git("reset", "-q", "--hard", "HEAD~1", cwd=self.repo)
        ok, lines = HK.prune_branches(self.repo, dry_run=False)
        self.assertTrue(ok)
        self.assertIn("agent/claude/lagging", self.branches())
        self.assertTrue(any(line.startswith("kept agent/claude/lagging: ") for line in lines), lines)
        self.assertEqual(lines[-1], "branches: deleted 1, refused 1, kept 1 merged ones a worktree has out")


STUB = """import sys
from pathlib import Path
with open(Path(__file__).resolve().parents[2] / "calls.txt", "a") as out:
    out.write(Path(__file__).name + " " + " ".join(sys.argv[1:]) + "\\n")
print("stub line from " + Path(__file__).name)
sys.exit({code})
"""


def dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def age(worktree: Path, seconds: float) -> None:
    """Make the worktree look untouched for `seconds`: its git files (HEAD, index) and its folder."""
    gitdir = Path(git("rev-parse", "--path-format=absolute", "--git-dir", cwd=worktree))
    then = time.time() - seconds
    for path in (gitdir / "HEAD", gitdir / "index", worktree):
        if path.exists():
            os.utime(path, (then, then))


class Locks(unittest.TestCase):
    """Only a lock that still binds goes to the sweep as --keep; a dead session's lock is the sweep's to judge."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.repo = new_repo(self.base)

    def tree(self, name: str, pid: int) -> Path:
        path = self.base / ".claude-worktrees" / name
        git("worktree", "add", "-q", "--detach", str(path), "main", cwd=self.repo)
        git("worktree", "lock", "--reason", f"claude agent {name} (pid {pid})", str(path), cwd=self.repo)
        return path

    def test_a_live_lock_is_kept_and_a_dead_idle_one_is_not(self) -> None:
        live = self.tree("agent-live", os.getpid())
        dead = self.tree("agent-dead", dead_pid())
        age(dead, 2 * 3600)
        self.assertEqual(HK.locked_paths(self.repo), [str(live)])

    def test_a_dead_lock_still_in_use_is_kept(self) -> None:
        fresh = self.tree("agent-fresh", dead_pid())  # touched now: inside LOCK_IDLE
        self.assertEqual(HK.locked_paths(self.repo), [str(fresh)])

    def test_the_real_sweep_removes_a_dead_idle_locked_worktree_and_keeps_a_live_one(self) -> None:
        for rel in ("tools/agent/worktrees.py", "tools/agent/worktree_rules.py"):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, self.repo / rel)
        (self.repo / "tools/agent/progress_prune.py").write_text("", encoding="utf-8")  # nothing to prune here
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text("#!/bin/sh\necho '[]'\n", encoding="utf-8")  # no PRs, open or merged
        (bin_dir / "gh").chmod(0o755)
        live = self.tree("agent-live", os.getpid())
        dead = self.tree("agent-dead", dead_pid())
        age(dead, 2 * 3600)
        age(live, 2 * 3600)
        with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}):
            ok, lines = HK.tidy(self.repo, False)
        self.assertTrue(ok, lines)
        self.assertFalse(dead.exists(), lines)
        self.assertTrue(live.exists(), lines)


class AfterLand(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.root = new_repo(self.base)
        self.locked = self.base / "agent-held"
        git("worktree", "add", "-q", "-b", "agent/claude/held", str(self.locked), cwd=self.root)
        git("worktree", "lock", "--reason", "claude agent agent-held (pid 1)", str(self.locked), cwd=self.root)
        self.lock = self.base / "cache/housekeeping.lock"
        self.stubs(0)

    def stubs(self, code: int) -> None:
        (self.root / "tools/agent").mkdir(parents=True, exist_ok=True)
        for name in ("worktrees.py", "progress_prune.py"):
            (self.root / "tools/agent" / name).write_text(STUB.format(code=code), encoding="utf-8")

    def calls(self) -> list[str]:
        path = self.root / "calls.txt"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def test_runs_the_sweep_keeping_locked_worktrees_then_the_prune(self) -> None:
        lines = HK.after_land(self.root, lock=self.lock)
        self.assertEqual(self.calls(), [f"worktrees.py sweep --keep {self.root} --keep {self.locked}",
                                        "progress_prune.py "])
        self.assertEqual(lines, ["housekeeping after the merge:", "worktree sweep: 1 line(s)",
                                 "stub line from worktrees.py", "progress prune: 1 line(s)",
                                 "stub line from progress_prune.py"])

    def test_a_failing_step_is_a_line_and_the_next_still_runs(self) -> None:
        self.stubs(3)
        lines = HK.after_land(self.root, lock=self.lock)
        self.assertIn("worktree sweep: exit 3", lines)
        self.assertIn("progress prune: exit 3", lines)
        self.assertEqual(len(self.calls()), 2)

    def test_never_raises(self) -> None:
        lines = HK.after_land(self.base / "not-a-repo", lock=self.lock)
        self.assertIn("not run", lines[-1], lines)

    def test_a_held_lock_skips_the_run(self) -> None:
        with HK.held(self.lock) as got:
            self.assertTrue(got)
            lines = HK.after_land(self.root, lock=self.lock)
        self.assertEqual(lines, ["housekeeping: another run holds the lock; the hourly run takes the rest"])
        self.assertEqual(self.calls(), [])


class BranchFailures(unittest.TestCase):
    def test_a_git_timeout_is_one_line_and_exit_1_and_the_sweep_lines_still_print(self) -> None:
        def run(cmd: list[str], cwd: object, timeout: float) -> subprocess.CompletedProcess[str]:
            if cmd[:2] == ["git", "fetch"]:
                raise subprocess.TimeoutExpired(cmd, timeout)
            return subprocess.CompletedProcess(cmd, 0, "swept\n", "")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(os.path.realpath(tmp))
            repo = new_repo(base)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = HK.run_all(repo, False, run, lock=base / "lock", log=base / "none.log")
        lines = out.getvalue().splitlines()
        self.assertEqual(code, 1)
        self.assertIn("worktree sweep: 1 line(s)", lines)
        self.assertIn("progress prune: 1 line(s)", lines)
        self.assertTrue(lines[-1].startswith("branches: did not run: Command '['git', 'fetch'"), lines)

    def test_branches_subcommand_exits_1_when_git_cannot_run(self) -> None:
        def run(cmd: list[str], cwd: object, timeout: float) -> subprocess.CompletedProcess[str]:
            raise OSError("no git")

        ok, lines = HK.prune_branches(Path("/nowhere"), False, run)
        self.assertFalse(ok)
        self.assertEqual(lines, ["branches: did not run: no git"])


class Trim(unittest.TestCase):
    def test_a_long_log_keeps_its_last_half_whole_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "housekeeping.log"
            log.write_text("".join(f"line {i}\n" for i in range(100)), encoding="utf-8")
            HK.trim(log, limit=100)
            kept = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(kept[-1], "line 99")
            self.assertTrue(40 <= len(kept) <= 60, len(kept))
            self.assertTrue(all(line.startswith("line ") for line in kept))
            self.assertFalse((Path(tmp) / "housekeeping.log.trim").exists())

    def test_a_short_log_is_left(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "housekeeping.log"
            log.write_text("a\n", encoding="utf-8")
            HK.trim(log, limit=100)
            self.assertEqual(log.read_text(encoding="utf-8"), "a\n")


class Launchd(unittest.TestCase):
    def test_plist_runs_make_housekeeping_hourly_in_the_main_checkout(self) -> None:
        data = plistlib.loads(HK.plist(Path("/repo"), "/opt/bin:/usr/bin", Path("/home/u/.cache/hart/housekeeping")))
        self.assertEqual(data["Label"], HK.LABEL)
        self.assertEqual(data["ProgramArguments"], ["/usr/bin/make", "-C", "/repo", "housekeeping"])
        self.assertEqual(data["WorkingDirectory"], "/repo")
        self.assertEqual(data["StartInterval"], 3600)
        self.assertEqual(data["EnvironmentVariables"], {"PATH": "/opt/bin:/usr/bin"})
        self.assertEqual(data["StandardOutPath"], "/home/u/.cache/hart/housekeeping/housekeeping.log")
        self.assertEqual(data["StandardErrorPath"], data["StandardOutPath"])

    def test_install_and_uninstall_write_and_remove_the_file(self) -> None:
        calls: list[list[str]] = []

        def run(cmd: list[str], cwd: object, timeout: float) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(os.path.realpath(tmp))
            repo = new_repo(base)
            agents, logs = base / "LaunchAgents", base / "logs"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(HK.install(repo, run, agents, logs), 0)
            target = agents / f"{HK.LABEL}.plist"
            self.assertEqual(plistlib.loads(target.read_bytes())["ProgramArguments"][2], str(repo))
            self.assertTrue(logs.is_dir())
            domain = f"gui/{os.getuid()}"
            self.assertEqual(calls, [["launchctl", "bootout", f"{domain}/{HK.LABEL}"],
                                     ["launchctl", "bootstrap", domain, str(target)]])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(HK.uninstall(repo, run, agents), 0)
            self.assertFalse(target.exists())
            self.assertEqual(calls[-1], ["launchctl", "bootout", f"{domain}/{HK.LABEL}"])


class MakeTargets(unittest.TestCase):
    def dry(self, *args: str) -> str:
        return subprocess.run(["make", "-n", "-C", str(ROOT), *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def test_the_targets_call_housekeeping_py(self) -> None:
        self.assertEqual(self.dry("housekeeping"), "python3 tools/agent/housekeeping.py run")
        self.assertEqual(self.dry("housekeeping", "DRY=1"), "python3 tools/agent/housekeeping.py run --dry-run")
        self.assertEqual(self.dry("housekeeping-install"), "python3 tools/agent/housekeeping.py install")
        self.assertEqual(self.dry("housekeeping-uninstall"), "python3 tools/agent/housekeeping.py uninstall")


if __name__ == "__main__":
    unittest.main()
