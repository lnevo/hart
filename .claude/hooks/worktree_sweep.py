#!/usr/bin/env python3
"""Remove agent worktrees whose PR is merged, or that hold nothing beyond origin/main: at session start and after
`gh pr merge`.

Calls tools/agent/worktrees.py sweep, keeping the session's working and project directories. A merge done
on GitHub is caught at the next session start. The sweep also covers the worktrees of the checked-out submodules
(agent/* branches only). The sweep runs under TIMEOUT (keep it below the hook's own 60 s in
.claude/settings.json); no removal starts and no submodule is looked at after BUDGET, which leaves each removal TIMEOUT - BUDGET seconds, so a long
backlog waits for the next sweep, or `make wt-sweep`, instead of being cut off mid-delete. At session start it
also sets the pipeline map's git merge drivers (tools/ops/merge_pipeline_map.py --install, silent once set; a
failure is shown in the session context), starts the build of wiki/STATUS.md in the session's checkout and the
project's beside the sweep (tools/ops/status_counts.py --quiet, under STATUS_TIMEOUT; ADR-038: the page is gitignored,
so readers by path find it; a problem with the entries is one line), and starts tools/ops/orient.py --short (open claims and worktrees in
progress; local git and files only, no network) beside the sweep, under ORIENT_TIMEOUT. Its lines come first in the
session context; it reads the worktrees while the sweep runs, so it may list one the sweep then removes. At session
start tools/agent/progress_prune.py also runs beside the sweep, under PRUNE_TIMEOUT: it archives the progress files of
lanes that are done. The sweep and the prune reach the session context as one summary line (what was removed, kept
and archived, naming only the worktrees that need a look); their full lines go to LOG in the project, which the
summary names. At session start it also checks the project's Claude Code auto-memory folder (memory_folder; file
reads only) and adds at most one warning line (memory_line). A timeout or failure is one line. Never blocks: any
failure exits 0.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

TIMEOUT = 45  # seconds for the whole sweep; with DRIVER_TIMEOUT before it, under the hook's 60 s
DRIVER_TIMEOUT = 8  # seconds for setting the merge drivers (well under 1 s when they are set)
BUDGET = TIMEOUT - 25  # no removal starts after this many seconds of removing
STATUS_TIMEOUT = 10  # seconds the status page builds may take (well under 1 s); they run beside the sweep
STATUS_SCRIPT = "tools/ops/status_counts.py"
ORIENT_TIMEOUT = 10  # seconds orient may take; it runs beside the sweep, so the hook's total stays under 60 s
PRUNE_TIMEOUT = 25  # seconds the progress prune may take (one GitHub call); it runs beside the sweep
PRUNE_SCRIPT = "tools/agent/progress_prune.py"
LOG = ".claude/logs/worktree-sweep.log"  # the last sweep's full lines (gitignored), overwritten each run
MERGE = re.compile(r"(^|[;&|\n]\s*)gh\s+pr\s+merge\b")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    event = data.get("hook_event_name", "")
    if event == "PostToolUse" and not MERGE.search(data.get("tool_input", {}).get("command", "")):
        return 0
    cwd = data.get("cwd") or os.getcwd()
    project = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    # first, so a sweep that fails or runs out of time cannot leave a fresh clone without them
    context = merge_drivers(project) if event == "SessionStart" else []
    status = start_status_pages(project, cwd) if event == "SessionStart" else []
    orient = start_orient(project, cwd) if event == "SessionStart" else None
    prune = start_prune(project) if event == "SessionStart" else None
    swept = sweep_lines(project, cwd)
    pruned = prune_lines(*prune) if prune is not None else Lines([], [])
    context += status_lines(status)
    if orient is not None:
        context = orient_lines(*orient) + context
    context += report(swept, pruned, Path(project) / LOG)
    if event == "SessionStart":
        context += memory_line(memory_folder(project))
    if context and event in ("PostToolUse", "SessionStart"):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": "\n".join(context),
        }}))
    return 0


def start_orient(project: str, cwd: str) -> tuple[subprocess.Popen | str, float] | None:
    """Start orient --short from the session's folder (so it marks the session's own worktree), or the line saying
    why it could not start; None for a checkout from before orient."""
    script = Path(project) / "tools" / "ops" / "orient.py"
    if not script.exists():
        return None
    try:
        proc = subprocess.Popen([sys.executable, str(script), "--short"], cwd=cwd if os.path.isdir(cwd) else project,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError as err:
        return f"Orient did not start ({err}); run make orient", time.monotonic()
    return proc, time.monotonic()


def orient_lines(proc: subprocess.Popen | str, started: float) -> list[str]:
    """Orient's lines, under a heading; one line when it failed or ran past ORIENT_TIMEOUT (counted from its start)."""
    if isinstance(proc, str):
        return [proc]
    try:
        out, err = proc.communicate(timeout=max(0.1, ORIENT_TIMEOUT - (time.monotonic() - started)))
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return [f"Orient took over {ORIENT_TIMEOUT} s and was stopped; run make orient"]
    if proc.returncode != 0:
        # orient's own errors start "orient:"; an uncaught one ends in a traceback whose last line names it
        lines = [l for l in err.splitlines() if l.strip()]
        message = next((l for l in lines if l.startswith("orient:")), lines[-1] if lines else f"exit {proc.returncode}")
        return [f"Orient failed: {message.strip()}; run make orient"]
    return ["Who is working on what (make orient for PRs, deploys and the operating flag):", *out.splitlines()]


def checkout_of(folder: str) -> Path | None:
    """The checkout that holds `folder`: the nearest folder at or above it with STATUS_SCRIPT."""
    here = Path(folder).resolve()
    return next((p for p in (here, *here.parents) if (p / STATUS_SCRIPT).is_file()), None)


def start_status_pages(project: str, cwd: str) -> list[tuple[Path, subprocess.Popen | str, float]]:
    """Start the build of wiki/STATUS.md in the session's checkout and the project's (one when they are the same);
    for each, the process or the line saying why it did not start, and when it started."""
    out = []
    for root in dict.fromkeys(c for c in (checkout_of(cwd), checkout_of(project)) if c):
        try:
            proc = subprocess.Popen([sys.executable, str(root / STATUS_SCRIPT), "--quiet"], cwd=root,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except OSError as err:
            out.append((root, f"wiki/STATUS.md not built in {root} ({err}); run make status", time.monotonic()))
            continue
        out.append((root, proc, time.monotonic()))
    return out


def status_lines(started: list[tuple[Path, subprocess.Popen | str, float]]) -> list[str]:
    """One line per build that failed, ran past STATUS_TIMEOUT (counted from its start) or found a problem with the
    entries; none when all is well."""
    out = []
    for root, proc, began in started:
        if isinstance(proc, str):
            out.append(proc)
            continue
        try:
            stdout, stderr = proc.communicate(timeout=max(0.1, STATUS_TIMEOUT - (time.monotonic() - began)))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            out.append(f"wiki/STATUS.md build in {root} took over {STATUS_TIMEOUT} s and was stopped; run make status")
            continue
        if proc.returncode != 0:
            lines = [l.strip() for l in (stdout + stderr).splitlines() if l.strip()]
            out.append(f"wiki/STATUS.md in {root}: {'; '.join(lines[-3:]) or f'exit {proc.returncode}'}; "
                       "run make status")
    return out


class Lines(NamedTuple):
    details: list[str]  # the script's own lines, for LOG and the summary
    problems: list[str]  # why it failed, did not run or was stopped: shown as they are


def sweep_lines(project: str, cwd: str) -> Lines:
    """Run the sweep, keeping `cwd` and `project`: its removed/kept/waiting/left lines, and one problem line when it
    failed or ran past TIMEOUT; nothing when the checkout predates it."""
    script = Path(project) / "tools" / "agent" / "worktrees.py"
    if not script.exists():
        return Lines([], [])
    try:
        done = subprocess.run([sys.executable, str(script), "sweep", "--keep", cwd, "--keep", project, "--budget",
                               str(BUDGET)], capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return Lines([], [f"Worktree sweep took over {TIMEOUT} s and was stopped; run make wt-sweep"])
    except (OSError, subprocess.SubprocessError) as err:
        return Lines([], [f"Worktree sweep did not run ({err}); run make wt-sweep"])
    lines = [l for l in done.stdout.splitlines() if l.startswith(("removed", "kept", "waiting", "left"))]
    if done.returncode != 0:
        errors = [l.strip() for l in done.stderr.splitlines() if l.strip()]
        return Lines(lines, [f"Worktree sweep failed: {errors[-1] if errors else f'exit {done.returncode}'}; "
                            "run make wt-sweep"])
    return Lines(lines, [])


def start_prune(project: str) -> tuple[subprocess.Popen | str, float] | None:
    """Start the progress prune, or the line saying why it could not start; None for a checkout from before it."""
    script = Path(project) / PRUNE_SCRIPT
    if not script.exists():
        return None
    try:
        proc = subprocess.Popen([sys.executable, str(script)], cwd=project, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except OSError as err:
        return f"Progress files not pruned ({err}); run python3 {PRUNE_SCRIPT}", time.monotonic()
    return proc, time.monotonic()


def prune_lines(proc: subprocess.Popen | str, started: float) -> Lines:
    """The prune's archived/left lines, and one problem line when it failed or ran past PRUNE_TIMEOUT."""
    if isinstance(proc, str):
        return Lines([], [proc])
    try:
        out, err = proc.communicate(timeout=max(0.1, PRUNE_TIMEOUT - (time.monotonic() - started)))
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return Lines([], [f"Progress prune took over {PRUNE_TIMEOUT} s and was stopped; run python3 {PRUNE_SCRIPT}"])
    lines = [l for l in out.splitlines() if l.startswith(("archived", "left"))]
    if proc.returncode != 0:
        errors = [l.strip() for l in err.splitlines() if l.strip()]
        return Lines(lines, [f"Progress files not pruned: {errors[-1] if errors else f'exit {proc.returncode}'}; "
                            f"run python3 {PRUNE_SCRIPT}"])
    return Lines(lines, [])


def summary(swept: list[str], pruned: list[str]) -> str:
    """One line: how many worktrees were removed and kept, naming those kept for a look (not the ones a later sweep
    removes by itself), and how many progress files were archived."""
    def count(lines: list[str], word: str) -> int:
        return sum(1 for l in lines if l.startswith(word + " "))

    look = [os.path.basename(l.split(" ", 2)[1].rstrip(":")) for l in swept if l.startswith("kept ")]
    text = f"Worktree sweep: removed {count(swept, 'removed')}, kept {len(look) + count(swept, 'waiting')}"
    if look:
        text += f" ({len(look)} need a look: {', '.join(look)})"
    if count(swept, "left"):
        text += "; some left for the next sweep (make wt-sweep)"
    if pruned:
        text += f"; progress files archived {count(pruned, 'archived')}"
        if count(pruned, "left"):
            text += f", {count(pruned, 'left')} left (archive name taken)"
    return text


def report(swept: Lines, pruned: Lines, log: Path) -> list[str]:
    """The summary line, naming `log` (which gets every line), then the problem lines; none when all is quiet."""
    details = swept.details + pruned.details
    if not details:
        return swept.problems + pruned.problems
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("".join(f"{l}\n" for l in [f"{datetime.now():%Y-%m-%d %H:%M:%S}", *details]), encoding="utf-8")
        saved = f"details: {log}"
    except OSError as err:
        saved = f"details not saved ({err})"
    return [f"{summary(swept.details, pruned.details)}; {saved}", *swept.problems, *pruned.problems]


MEMORY_CAP = 40  # memory files (MEMORY.md aside) before the warning asks for rulings to move out
MEMORY_ENV = "HART_MEMORY_DIR"  # a memory folder to check instead of the project's (the tests set it)
WIKI_LINK = re.compile(r"\[\[([^\]|#]+)")
INDEX_LINK = re.compile(r"\]\(([^)\s]+\.md)\)")
SHOWN = 3  # names per problem in the warning, then "and N more"


def memory_folder(project: str) -> Path:
    """The auto-memory folder of the project's main checkout: ~/.claude/projects/<slug>/memory/, where the slug is
    the checkout's absolute path with each character other than a letter or digit made "-" (/Users/x/hart is
    -Users-x-hart). MEMORY_ENV, when set, names the folder instead."""
    if os.environ.get(MEMORY_ENV):
        return Path(os.environ[MEMORY_ENV])
    main = Path(project).resolve()
    try:
        common = subprocess.run(["git", "-C", project, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, timeout=5)
        if common.returncode == 0 and common.stdout.strip():
            main = Path(common.stdout.strip()).parent  # the main checkout, also from inside a worktree
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(main)) / "memory"


def shown(names: list[str]) -> str:
    more = f" and {len(names) - SHOWN} more" if len(names) > SHOWN else ""
    return ", ".join(names[:SHOWN]) + more


def memory_line(folder: Path) -> list[str]:
    """One warning line when the memory folder holds more than MEMORY_CAP files, a [[name]] link with no name.md,
    a MEMORY.md entry whose file is missing, or a file MEMORY.md does not list; none when all is well or there is
    no folder."""
    if not folder.is_dir():
        return []
    try:
        files = {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.md"))}
    except (OSError, UnicodeDecodeError) as err:
        return [f"Memory: {folder} not read ({err})"]
    index = files.pop("MEMORY.md", "")
    listed = {os.path.basename(m) for m in INDEX_LINK.findall(index)}
    dangling = sorted({f"[[{n.strip()}]]" for text in [index, *files.values()] for n in WIKI_LINK.findall(text)
                       if f"{n.strip()}.md" not in files})
    problems = []
    if len(files) > MEMORY_CAP:
        problems.append(f"{len(files)} files (cap {MEMORY_CAP})")
    if dangling:
        problems.append(f"{len(dangling)} dangling link(s) {shown(dangling)}")
    if missing := sorted(listed - set(files)):
        problems.append(f"{len(missing)} MEMORY.md entr{'y' if len(missing) == 1 else 'ies'} with no file: "
                        f"{shown(missing)}")
    if unlisted := sorted(set(files) - listed):
        problems.append(f"{len(unlisted)} file(s) not in MEMORY.md: {shown(unlisted)}")
    if not problems:
        return []
    return [f"Memory: {', '.join(problems)}; move rulings into the skill or wiki they govern."]


def merge_drivers(project: str) -> list[str]:
    """Set the repo's git merge drivers (tools/ops/merge_pipeline_map.py --install; git config is shared by every
    worktree, so a no-op once set). Return the lines to show: what it changed, or why it failed; none when set."""
    script = Path(project) / "tools" / "ops" / "merge_pipeline_map.py"
    if not script.exists():  # a checkout from before the driver: nothing to set
        return []
    try:
        done = subprocess.run([sys.executable, str(script), "--install", "--repo", project],
                              capture_output=True, text=True, timeout=DRIVER_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as err:
        return [f"Merge drivers not set ({err}); run python3 tools/ops/merge_pipeline_map.py --install"]
    if done.returncode != 0:
        return [f"Merge drivers not set: {done.stderr.strip()}; run python3 tools/ops/merge_pipeline_map.py --install"]
    return ["Merge drivers:", *done.stdout.splitlines()] if done.stdout.strip() else []


if __name__ == "__main__":
    sys.exit(main())
