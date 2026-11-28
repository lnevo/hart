#!/usr/bin/env python3
"""Ship a lane's work from its worktree: commit, merge main when the rule says so, check, push, remote run, PR.

    make ready FILES="a.py b.md" MSG="fix(x): what changed" [TITLE="..."] [BODY="..." | BODY_FILE=path]

Run at the top of an agent worktree (under the main checkout's .claude/worktrees/) on an `agent/claude/*` branch.
Each step stops the run with a message when it fails:

1. Refuse the main checkout, a worktree elsewhere, a subfolder, `main` and any branch not named `agent/claude/*`.
2. Stage the named FILES (never `git add -A`; no directories, no .env.local, credentials or tools/cats/src-repo/)
   and commit them with MSG and the attribution lines.
3. `git fetch origin`, then merge `origin/main` only when main changed a file the branch touches since the merge
   base (the Merge rule in the handoff skill). The merge is local, so the merge drivers in .gitattributes run. A
   conflict aborts the merge and stops.
4. After the merge (or none): regenerate the pipeline map, and the docs index when the branch changes docs/; then
   `manifest.py check` and `build_pipeline_map.py --check`.
5. The ratchets without --update (check_mypy, check_habits, check_py_sizes, check_ruff) and `make static`.
6. Commit the regenerated outputs that changed, by name; push the branch to its own name on origin (`-u`, no force).
7. `make pr-kind`: docs or light skips the remote run. Else `make remote CMD="./tools/check.sh"`, which waits for a
   free remote slot (tools/hosts/win_run.sh, the mac lock block), with its whole output in a log file named after
   the branch and head (LOG_DIR); the run must end ALL PASSED.
8. Open the PR with TITLE (default: MSG's first line) and BODY or BODY_FILE plus the attribution footer, or print
   the open one; print its number, the full head SHA and the remote log path.

It never merges a PR, deploys or touches a layout host: gh is called only for `pr view` and `pr create` (GH_ALLOWED),
and git pushes only HEAD to the branch's own name. The attribution lines come from the JSON file named by
HART_READY_ATTRIBUTION, else .claude/ready-attribution.json in the main checkout (gitignored; the coordinator writes
it): {"commit": [lines], "pr": [lines]}. The subagent guard sees only the `make ready` command line, not the git and
gh calls this script makes as child processes, so the script holds the rules those calls need: the place and branch
rule, the file rule, the push rule, the gh allowlist and the private-name check on MSG, TITLE and the body.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

BRANCH = re.compile(r"agent/claude/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")
LOG_DIR = Path("/tmp/hart-ready")
ATTRIBUTION_ENV = "HART_READY_ATTRIBUTION"
ATTRIBUTION_FILE = ".claude/ready-attribution.json"
WORKTREES = ".claude/worktrees"
NAME_CHECK = "ops/hart-ops/card_pipeline/private_name.py"
PASS_LINE = "ALL PASSED"
MAP = "docs/pipeline-map/pipeline_map.json"
DOCS_INDEX = "docs/INDEX.md"
FORBIDDEN_NAMES = {".env.local", "credentials.json", "settings.local.json"}
FORBIDDEN_PREFIX = "tools/cats/src-repo"
GH_ALLOWED = {("pr", "view"), ("pr", "create")}


class ReadyError(Exception):
    """A step failed or a rule refused; the message says which and what to do."""


@dataclass(frozen=True)
class Step:
    """One command the run makes; `outputs` are the files it may rewrite, staged by name when they change."""
    name: str
    argv: tuple[str, ...]
    outputs: tuple[str, ...] = ()
    only_if_changed: str = ""       # run only when the branch changes a path under this prefix


REGENERATE = (
    Step("pipeline map", ("python3", "tools/ops/build_pipeline_map.py"), (MAP,)),
    Step("docs index", ("python3", "tools/ops/build_docs_index.py"), (DOCS_INDEX,), only_if_changed="docs/"),
)
CHECKS = (
    Step("manifest", ("python3", "tools/pipeline/manifest.py", "check")),
    Step("pipeline map check", ("python3", "tools/ops/build_pipeline_map.py", "--check")),
    Step("mypy ratchet", ("python3", "tools/audit/check_mypy.py")),
    Step("habits ratchet", ("python3", "tools/audit/check_habits.py")),
    Step("py sizes", ("python3", "tools/audit/check_py_sizes.py")),
    Step("ruff ratchet", ("python3", "tools/audit/check_ruff.py")),
    Step("make static", ("make", "static")),
)


@dataclass(frozen=True)
class Request:
    """What the lane asks for: the files to stage, the commit message, the PR title and body."""
    files: tuple[str, ...]
    msg: str
    title: str = ""
    body: str = ""


@dataclass(frozen=True)
class Attribution:
    commit: tuple[str, ...]
    pr: tuple[str, ...]


@dataclass(frozen=True)
class Shipped:
    pr: int
    url: str
    head: str
    log: Path | None


GhRun = Callable[[Path, Sequence[str]], "subprocess.CompletedProcess[str]"]


def default_remote(repo: Path, log: Path) -> int:
    """`make remote CMD="./tools/check.sh"`, its output streamed to the terminal and saved whole in `log`."""
    with log.open("w", encoding="utf-8") as out, subprocess.Popen(
            ["make", "remote", "CMD=./tools/check.sh"], cwd=repo, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            out.write(line)
        return proc.wait()


def default_gh(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], cwd=repo, capture_output=True, text=True)


def default_pr_kind(repo: Path) -> str:
    return run(repo, "make", "-s", "pr-kind").strip()


def say_line(text: str) -> None:
    print(text, flush=True)


@dataclass
class Tools:
    """The parts the tests replace: GitHub, the remote run, the check commands and where logs go."""
    remote: Callable[[Path, Path], int] = default_remote
    gh_run: GhRun = default_gh
    pr_kind: Callable[[Path], str] = default_pr_kind
    regenerate: Sequence[Step] = REGENERATE
    checks: Sequence[Step] = CHECKS
    log_dir: Path = LOG_DIR
    say: Callable[[str], None] = field(default=say_line)

    def gh(self, repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """gh, for `pr view` and `pr create` only: this script never merges, closes or edits a PR."""
        if tuple(args[:2]) not in GH_ALLOWED:
            raise ReadyError(f"make ready does not run gh {shlex.join(args[:2])}")
        return self.gh_run(repo, args)


def run(repo: Path, *argv: str, env: dict[str, str] | None = None) -> str:
    """The command's stdout; a failure raises ReadyError with its output."""
    done = subprocess.run(argv, cwd=repo, capture_output=True, text=True, env=env)
    if done.returncode != 0:
        raise ReadyError(f"{shlex.join(argv)} failed ({done.returncode}):\n{(done.stdout + done.stderr).strip()}")
    return done.stdout


def git(repo: Path, *args: str) -> str:
    return run(repo, "git", *args).strip()


def lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line]


def main_checkout(repo: Path) -> Path:
    return Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent


def check_place(repo: Path) -> str:
    """The branch name, once `repo` is the top of an agent worktree on an agent/claude/* branch."""
    git_dir = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-dir"))
    common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    if git_dir == common:
        raise ReadyError("this is the main checkout; run make ready in your agent worktree")
    top = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    if top != repo.resolve():
        raise ReadyError(f"run make ready at the top of the worktree ({top}), not in a subfolder")
    if top.parent != (common.parent / WORKTREES).resolve():
        raise ReadyError(f"{top} is not an agent worktree under {common.parent / WORKTREES}")
    return check_branch(git(repo, "branch", "--show-current"))


def check_branch(branch: str) -> str:
    if branch == "main":
        raise ReadyError("the branch is main; make ready ships agent/claude/* branches only")
    if not BRANCH.fullmatch(branch):
        raise ReadyError(f"branch {branch or '(detached)'} is not agent/claude/*")
    return branch


def file_problem(repo: Path, path: str) -> str:
    """'' when `path` may be staged by name, else why not."""
    norm = os.path.normpath(path)
    if os.path.isabs(path) or norm == ".." or norm.startswith("../"):
        return "outside the worktree"
    if os.path.basename(norm) in FORBIDDEN_NAMES or norm == FORBIDDEN_PREFIX or norm.startswith(
            FORBIDDEN_PREFIX + "/"):
        return "a private file (.env.local, credentials, tools/cats/src-repo/) is never committed"
    if (repo / norm).is_dir():
        return "a directory; name its files"
    if not lines(git(repo, "status", "--porcelain", "--", norm)):
        return "no change to stage"
    return ""


def private_name_check(repo: Path) -> Callable[[str], bool]:
    """The repo's fingerprint check (main_guard uses the same file). Raises when it cannot load: fail closed."""
    spec = importlib.util.spec_from_file_location("hart_private_name_ready", repo / NAME_CHECK)
    if spec is None or spec.loader is None:
        raise ReadyError(f"the private-name check could not load ({NAME_CHECK})")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except OSError as exc:
        raise ReadyError(f"the private-name check could not load ({NAME_CHECK})") from exc
    check: Callable[[str], bool] = module.contains_private_name
    return check


def read_attribution(repo: Path) -> Attribution:
    path = Path(os.environ.get(ATTRIBUTION_ENV) or main_checkout(repo) / ATTRIBUTION_FILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReadyError(f"no attribution lines: {path} is missing or not JSON; the coordinator writes it "
                         f'({{"commit": [...], "pr": [...]}}) or sets {ATTRIBUTION_ENV}') from exc
    found: dict[str, tuple[str, ...]] = {}
    for key in ("commit", "pr"):
        value = data.get(key) if isinstance(data, dict) else None
        if not (isinstance(value, list) and value and all(isinstance(v, str) for v in value)):
            raise ReadyError(f"{path}: {key!r} must be a list of lines")
        found[key] = tuple(value)
    return Attribution(found["commit"], found["pr"])


def commit(repo: Path, paths: Sequence[str], message: str, attribution: Attribution) -> None:
    run(repo, "git", "add", "--", *paths, env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"})
    text = message.rstrip() + "\n\n" + "\n".join(attribution.commit) + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
    try:
        git(repo, "commit", "-q", "-F", f.name)
    finally:
        os.unlink(f.name)


def stage_and_commit(repo: Path, req: Request, attribution: Attribution) -> None:
    named = {os.path.normpath(p) for p in req.files}
    extra = sorted(set(lines(git(repo, "diff", "--cached", "--name-only"))) - named)
    if extra:
        raise ReadyError(f"already staged but not in FILES: {' '.join(extra)}; name them or unstage them")
    problems = [f"{p}: {why}" for p in req.files if (why := file_problem(repo, p))]
    if problems:
        raise ReadyError("FILES:\n  " + "\n  ".join(problems))
    if not req.files:
        return
    if not req.msg.strip():
        raise ReadyError('MSG="..." is needed to commit FILES')
    commit(repo, sorted(named), req.msg, attribution)


def merge_main_if_needed(repo: Path, say: Callable[[str], None]) -> bool:
    """Merge origin/main when main changed a file this branch touches since the merge base; True when merged."""
    git(repo, "fetch", "-q", "origin")
    base = git(repo, "merge-base", "HEAD", "origin/main")
    on_main = set(lines(git(repo, "diff", "--name-only", base, "origin/main")))
    touched = set(lines(git(repo, "diff", "--name-only", base, "HEAD")))
    both = sorted(on_main & touched)
    if not both:
        say("main has no change to a file this branch touches; no merge")
        return False
    say(f"merging origin/main: main changed {', '.join(both[:5])}{' ...' if len(both) > 5 else ''}")
    done = subprocess.run(["git", "merge", "--no-edit", "origin/main"], cwd=repo, capture_output=True, text=True)
    if done.returncode != 0:
        conflicts = lines(git(repo, "diff", "--name-only", "--diff-filter=U"))
        subprocess.run(["git", "merge", "--abort"], cwd=repo, capture_output=True)
        detail = f"; conflicts in: {' '.join(conflicts)}" if conflicts else f":\n{done.stdout}{done.stderr}"
        raise ReadyError("merging origin/main failed and was aborted" + detail)
    return True


def run_steps(repo: Path, steps: Sequence[Step], touched: set[str], say: Callable[[str], None]) -> list[str]:
    """Run each step; the outputs of the ones that ran."""
    outputs: list[str] = []
    for step in steps:
        if step.only_if_changed and not any(p.startswith(step.only_if_changed) for p in touched):
            continue
        say(f"{step.name}: {shlex.join(step.argv)}")
        done = subprocess.run(step.argv, cwd=repo, capture_output=True, text=True)
        if done.returncode != 0:
            tail = (done.stdout + done.stderr).strip()[-4000:]
            raise ReadyError(f"{step.name} failed ({done.returncode}):\n{tail}")
        outputs.extend(step.outputs)
    return outputs


def push(repo: Path, branch: str) -> None:
    """HEAD to the branch's own name on origin; never main, never forced."""
    check_branch(branch)
    git(repo, "push", "-q", "-u", "origin", f"HEAD:refs/heads/{branch}")


def remote_run(repo: Path, tools: Tools, branch: str, head: str) -> Path:
    tools.log_dir.mkdir(parents=True, exist_ok=True)
    log = tools.log_dir / f"{branch.replace('/', '-')}-{head[:12]}.log"
    tools.say(f"{time.strftime('%H:%M')} make remote CMD=./tools/check.sh (it waits for the remote lock; log: {log})")
    code = tools.remote(repo, log)
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    if code != 0 or PASS_LINE not in (line.strip() for line in text.splitlines()):
        raise ReadyError(f"the remote run did not end {PASS_LINE} (exit {code}); log: {log}")
    return log


def pr_view(repo: Path, tools: Tools, branch: str) -> dict[str, object] | None:
    view = tools.gh(repo, ["pr", "view", branch, "--json", "number,url,state"])
    if view.returncode != 0:
        return None
    found: dict[str, object] = json.loads(view.stdout)
    return found


def open_pr(repo: Path, tools: Tools, req: Request, branch: str, kind: str, attribution: Attribution,
            name_check: Callable[[str], bool]) -> tuple[int, str]:
    found = pr_view(repo, tools, branch)
    if found and found.get("state") == "OPEN":
        tools.say(f"PR #{found['number']} is already open: {found['url']}")
        return int(str(found["number"])), str(found["url"])
    title = req.title.strip() or next(iter(req.msg.strip().splitlines()), "")
    if not title:
        raise ReadyError('TITLE="..." (or MSG) is needed to open the PR')
    if not req.body.strip():
        raise ReadyError('BODY="..." or BODY_FILE=path is needed to open the PR')
    body = req.body.rstrip() + "\n"
    if kind.startswith("light"):
        body += "\n`make pr-kind` printed `light`.\n"
    body += "\n" + "\n".join(attribution.pr) + "\n"
    if name_check(title) or name_check(body):
        raise ReadyError("the PR title or body holds the private name")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(body)
    try:
        made = tools.gh(repo, ["pr", "create", "--base", "main", "--head", branch, "--title", title,
                               "--body-file", f.name])
    finally:
        os.unlink(f.name)
    if made.returncode != 0:
        raise ReadyError(f"gh pr create failed:\n{made.stdout}{made.stderr}")
    found = pr_view(repo, tools, branch)
    if not found:
        raise ReadyError("the PR was created but gh pr view cannot find it")
    return int(str(found["number"])), str(found["url"])


def ready(repo: Path, req: Request, tools: Tools | None = None) -> Shipped:
    tools = tools or Tools()
    say = tools.say
    branch = check_place(repo)
    name_check = private_name_check(repo)
    if name_check(req.msg) or name_check(req.title):
        raise ReadyError("MSG or TITLE holds the private name")
    attribution = read_attribution(repo)
    stage_and_commit(repo, req, attribution)
    merge_main_if_needed(repo, say)
    base = git(repo, "merge-base", "HEAD", "origin/main")
    touched = set(lines(git(repo, "diff", "--name-only", base, "HEAD")))
    if not touched:
        raise ReadyError("the branch has no change against origin/main; nothing to ship")
    outputs = run_steps(repo, tools.regenerate, touched, say)
    run_steps(repo, tools.checks, touched, say)
    changed = [p for p in dict.fromkeys(outputs) if lines(git(repo, "status", "--porcelain", "--", p))]
    if changed:
        commit(repo, changed, "chore: regenerate " + ", ".join(changed), attribution)
    dirty = lines(git(repo, "status", "--porcelain", "--untracked-files=no"))
    if dirty:
        say("left uncommitted (not in FILES): " + " ".join(d[3:] for d in dirty))
    push(repo, branch)
    head = git(repo, "rev-parse", "HEAD")
    kind = tools.pr_kind(repo)
    say(f"make pr-kind: {kind}")
    log: Path | None = None
    if kind.startswith(("docs", "light")):
        say("docs or light change: no remote run")
    else:
        log = remote_run(repo, tools, branch, head)
    number, url = open_pr(repo, tools, req, branch, kind, attribution, name_check)
    return Shipped(number, url, head, log)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--files", default="", help="the files to stage, separated by spaces")
    parser.add_argument("--msg", default="", help="the commit message")
    parser.add_argument("--title", default="", help="the PR title (default: the first line of --msg)")
    parser.add_argument("--body", default="", help="the PR body")
    parser.add_argument("--body-file", default="", help="a file holding the PR body")
    args = parser.parse_args(argv)
    try:
        body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
        shipped = ready(Path.cwd(), Request(tuple(args.files.split()), args.msg, args.title, body))
    except (OSError, ReadyError) as exc:
        print(f"make ready: {exc}", file=sys.stderr)
        return 1
    print(f"PR #{shipped.pr} {shipped.url}")
    print(f"head {shipped.head}")
    print(f"remote log {shipped.log if shipped.log else '(none: docs or light change)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
