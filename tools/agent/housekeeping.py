#!/usr/bin/env python3
"""Housekeeping between session starts: the worktree sweep, the progress prune and the local branch prune.

  housekeeping.py run [--dry-run]       the three below in turn (make housekeeping; the launchd agent runs it hourly)
  housekeeping.py branches [--dry-run]  delete local branches merged into origin/main that no worktree has checked out
  housekeeping.py plist                 print the launchd agent's plist
  housekeeping.py install | uninstall   write or remove ~/Library/LaunchAgents/LABEL.plist and load or unload it
                                        (make housekeeping-install, make housekeeping-uninstall)

`run` works on the repository of the folder it runs from, judged from its main checkout:
1. `tools/agent/worktrees.py sweep` with `--keep` for the folder it runs from and for every worktree whose lock
   still binds (worktrees.lock_held: its session runs, or it changed within LOCK_IDLE; of the repo and of each
   checked-out submodule), so a worktree a live session holds is never touched; a dead session's lock is judged by
   the sweep's own rule. The sweep never removes the main checkout or a worktree with changes, and keeps a
   just-merged one for its 30-minute grace (a later hourly run takes it).
2. `tools/agent/progress_prune.py`.
3. The branch prune: `git fetch -q origin main` (it moves only origin/main), then `git branch -d` for each local
   branch that `git for-each-ref --merged origin/main` lists, except main and any branch checked out in a worktree.
   `git branch -d` refuses a branch not merged into its upstream (or the main checkout's HEAD when it has none), so a
   refusal is one line and the branch stays. Remote branches are never touched. A git call that fails to run or
   times out ends the step with one "branches: did not run" line.
No step changes a working tree. A step that fails is one line and the next still runs; the exit is 1 when one
failed. Runs that overlap (the hourly agent and a land job) take LOCK; the second one prints a line and exits 0.
The log trim (below) runs under that lock.

`after_land` is the land job's half (tools/agent/land.py runs it after a merge): steps 1 and 2, its lines for the
land log, never an exception. The land job stays alive for it (up to SWEEP_TIMEOUT plus PRUNE_TIMEOUT) after
make land-wait has returned.

The launchd agent (LABEL) runs `make -C <main checkout> housekeeping` every INTERVAL seconds and at login, with the
installer's PATH (gh, git and python3 as the installer finds them), logging to LOG_DIR/housekeeping.log, which a run
trims to its last half once it passes LOG_MAX bytes (a new file put in place with os.replace; the run's own output
then goes to the new file).
"""
from __future__ import annotations

import argparse
import fcntl
import os
import plistlib
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from worktrees import GitCommandError, Worktree, lock_held, submodule_repos, worktrees  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LABEL = "com.hartrailroad.housekeeping"
INTERVAL = 3600
LOG_DIR = Path.home() / ".cache/hart/housekeeping"
LOG_MAX = 1_000_000
LOCK = LOG_DIR / "housekeeping.lock"
AGENTS = Path.home() / "Library/LaunchAgents"
SWEEP_TIMEOUT = 600
PRUNE_TIMEOUT = 120
GIT_TIMEOUT = 120
BASE = "main"

Run = Callable[..., "subprocess.CompletedProcess[str]"]


def run_cmd(args: Sequence[str], cwd: str | Path, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, timeout=timeout)


@dataclass(frozen=True)
class BranchPlan:
    delete: list[str]     # merged into origin/main, checked out nowhere
    in_worktree: list[str]  # merged, but some worktree has it checked out


def locked_paths(repo: Path) -> list[str]:
    """Every worktree of `repo` and of its checked-out submodules whose lock still binds (lock_held)."""
    trees: list[Worktree] = worktrees(repo)
    found = [t.path for t in trees if lock_held(t)]
    for sub in submodule_repos(trees[0].path) if trees else []:
        try:
            found += [t.path for t in worktrees(sub) if lock_held(t)]
        except GitCommandError:
            continue  # the sweep reports a broken submodule and leaves it alone
    return found


def sweep_command(root: Path, keep: Sequence[str]) -> list[str]:
    cmd = [sys.executable, str(root / "tools/agent/worktrees.py"), "sweep", "--keep", str(root)]
    for path in keep:
        cmd += ["--keep", path]
    return cmd


def step(name: str, cmd: list[str], root: Path, timeout: float, run: Run) -> tuple[bool, list[str]]:
    """Run one step; its output lines under a heading, and whether it ended 0."""
    try:
        done = run(cmd, cwd=root, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, [f"{name}: stopped after {timeout:g} s; the next run goes on"]
    except OSError as err:
        return False, [f"{name}: did not run: {err}"]
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    if done.returncode != 0:
        return False, [f"{name}: exit {done.returncode}", *lines]
    return True, [f"{name}: {len(lines)} line(s)", *lines]


def tidy(root: Path, dry_run: bool, run: Run = run_cmd) -> tuple[bool, list[str]]:
    """Steps 1 and 2 of `run`: the sweep (locked worktrees kept) and the progress prune."""
    try:
        keep = locked_paths(root)
    except GitCommandError as err:
        return False, [f"worktree sweep: not run, the worktrees cannot be listed: {err}"]
    extra = ["--dry-run"] if dry_run else []
    ok1, swept = step("worktree sweep", sweep_command(root, keep) + extra, root, SWEEP_TIMEOUT, run)
    ok2, pruned = step("progress prune", [sys.executable, str(root / "tools/agent/progress_prune.py"), *extra],
                       root, PRUNE_TIMEOUT, run)
    return ok1 and ok2, swept + pruned


def after_land(root: Path = ROOT, run: Run = run_cmd, lock: Path = LOCK) -> list[str]:
    """The land job's housekeeping after a merge: the sweep and the progress prune, as lines; never raises."""
    try:
        with held(lock) as got:
            if not got:
                return ["housekeeping: another run holds the lock; the hourly run takes the rest"]
            return ["housekeeping after the merge:", *tidy(root, False, run)[1]]
    except Exception as err:  # the merge stands whatever happens here
        return [f"housekeeping after the merge not run ({type(err).__name__}: {err})"]


def plan_branches(repo: Path, run: Run = run_cmd) -> BranchPlan:
    """The local branches merged into origin/main (as last fetched), split by whether a worktree has one out."""
    listed = run(["git", "for-each-ref", "--merged", f"origin/{BASE}", "--format=%(refname:short)", "refs/heads"],
                 cwd=repo, timeout=GIT_TIMEOUT)
    if listed.returncode != 0:
        raise GitCommandError(f"git for-each-ref failed: {listed.stderr.strip()}")
    out = {t.branch for t in worktrees(repo) if t.branch}
    merged = [b for b in listed.stdout.splitlines() if b and b != BASE]
    return BranchPlan([b for b in merged if b not in out], [b for b in merged if b in out])


def prune_branches(repo: Path, dry_run: bool, run: Run = run_cmd) -> tuple[bool, list[str]]:
    """Step 3 of `run`: fetch origin main, then `git branch -d` each merged branch no worktree has out. A git call
    that cannot run or times out is one line and a failed step."""
    lines: list[str] = []
    try:
        return _prune_branches(repo, dry_run, run, lines)
    except (subprocess.TimeoutExpired, OSError, GitCommandError) as err:
        return False, lines + [f"branches: did not run: {err}"]


def _prune_branches(repo: Path, dry_run: bool, run: Run, lines: list[str]) -> tuple[bool, list[str]]:
    fetched = run(["git", "fetch", "-q", "origin", BASE], cwd=repo, timeout=GIT_TIMEOUT)
    if fetched.returncode != 0:
        lines.append(f"branches: fetch failed, origin/{BASE} as last fetched: {fetched.stderr.strip()}")
    try:
        plan = plan_branches(repo, run)
    except GitCommandError as err:
        return False, lines + [f"branches: not pruned: {err}"]
    if dry_run:
        return True, lines + [f"would delete {b}" for b in plan.delete] + [
            f"branches: would delete {len(plan.delete)}, keep {len(plan.in_worktree)} merged ones a worktree has out"]
    deleted = refused = 0
    for branch in plan.delete:
        done = run(["git", "branch", "-d", branch], cwd=repo, timeout=GIT_TIMEOUT)
        if done.returncode == 0:
            deleted += 1
            lines.append(f"deleted {branch}")
        else:
            refused += 1
            lines.append(f"kept {branch}: {done.stderr.strip()}")
    return True, lines + [f"branches: deleted {deleted}, refused {refused}, kept {len(plan.in_worktree)} merged "
                          f"ones a worktree has out"]


@contextmanager
def held(lock: Path) -> Iterator[bool]:
    """An exclusive lock on `lock` without waiting: True when taken (released on exit), False when another has it."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def trim(log: Path, limit: int = LOG_MAX) -> None:
    """Keep the last half of `log` once it passes `limit` bytes (launchd appends to it and never trims): written to
    a temporary file put in place with os.replace. Standard output and error that pointed at the old file are
    pointed at the new one, so the rest of the run is logged."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        old = log.stat()
        if old.st_size <= limit:
            return
        text = log.read_text(encoding="utf-8", errors="replace")
        part = log.with_name(log.name + ".trim")
        part.write_text(text[len(text) // 2:].split("\n", 1)[-1], encoding="utf-8")
        os.replace(part, log)
        for fd in (1, 2):
            if os.fstat(fd).st_ino == old.st_ino and os.fstat(fd).st_dev == old.st_dev:
                new = os.open(log, os.O_WRONLY | os.O_APPEND)
                os.dup2(new, fd)
                os.close(new)
    except OSError:
        return


def run_all(root: Path, dry_run: bool, run: Run = run_cmd, lock: Path = LOCK,
            log: Path = LOG_DIR / "housekeeping.log") -> int:
    with held(lock) as got:
        if not got:
            print("housekeeping: another run holds the lock; nothing done")
            return 0
        trim(log)
        ok, lines = tidy(root, dry_run, run)
        ok_b, branch_lines = prune_branches(main_checkout(root), dry_run, run)
    for line in lines + branch_lines:
        print(line)
    return 0 if ok and ok_b else 1


def plist(main: Path, path_env: str, log_dir: Path = LOG_DIR) -> bytes:
    """The launchd agent: `make -C <main> housekeeping` every INTERVAL seconds and at load."""
    log = str(log_dir / "housekeeping.log")
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/make", "-C", str(main), "housekeeping"],
        "WorkingDirectory": str(main),
        "StartInterval": INTERVAL,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "EnvironmentVariables": {"PATH": path_env},
        "StandardOutPath": log,
        "StandardErrorPath": log,
    })


def main_checkout(root: Path) -> Path:
    trees = worktrees(root)
    return Path(trees[0].path) if trees else root


def install(root: Path, run: Run = run_cmd, agents: Path = AGENTS, log_dir: Path = LOG_DIR) -> int:
    target = agents / f"{LABEL}.plist"
    domain = f"gui/{os.getuid()}"
    log_dir.mkdir(parents=True, exist_ok=True)
    agents.mkdir(parents=True, exist_ok=True)
    run(["launchctl", "bootout", f"{domain}/{LABEL}"], cwd=root, timeout=GIT_TIMEOUT)  # an older copy, if loaded
    target.write_bytes(plist(main_checkout(root), os.environ.get("PATH", "/usr/bin:/bin"), log_dir))
    done = run(["launchctl", "bootstrap", domain, str(target)], cwd=root, timeout=GIT_TIMEOUT)
    if done.returncode != 0:
        print(f"wrote {target}; launchctl bootstrap failed: {done.stderr.strip()}", file=sys.stderr)
        return 1
    print(f"installed {target}: make housekeeping every {INTERVAL // 60} minutes; log {log_dir / 'housekeeping.log'}")
    return 0


def uninstall(root: Path, run: Run = run_cmd, agents: Path = AGENTS) -> int:
    target = agents / f"{LABEL}.plist"
    run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], cwd=root, timeout=GIT_TIMEOUT)
    target.unlink(missing_ok=True)
    print(f"removed {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "branches"):
        sub.add_parser(name).add_argument("--dry-run", action="store_true", help="name what would go, change nothing")
    for name in ("plist", "install", "uninstall"):
        sub.add_parser(name)
    a = ap.parse_args(argv)
    root = ROOT
    if a.cmd == "run":
        return run_all(root, a.dry_run)
    if a.cmd == "branches":
        ok, lines = prune_branches(main_checkout(root), a.dry_run)
        print("\n".join(lines))
        return 0 if ok else 1
    if a.cmd == "plist":
        sys.stdout.write(plist(main_checkout(root), os.environ.get("PATH", "/usr/bin:/bin")).decode())
        return 0
    return install(root) if a.cmd == "install" else uninstall(root)


if __name__ == "__main__":
    sys.exit(main())
