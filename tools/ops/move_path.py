#!/usr/bin/env python3
"""Move or rename a tracked file or folder, and rewrite every place in the repo that names it.

    python3 tools/ops/move_path.py OLD NEW              show what would change; change nothing
    python3 tools/ops/move_path.py OLD NEW --apply      move it (git mv) and rewrite the references
        [--include-history]   also rewrite archive/ and wiki/STATUS_LOG.md (they keep the old name by default)
        [--no-rebuild]        skip rebuilding the docs index and the pipeline-map pages afterwards

OLD and NEW are paths from the repo root. OLD is a tracked file or a folder of tracked files; NEW must not exist.
Run it from the checkout to change (a task worktree), then ./tools/check.sh.

What it rewrites, in every tracked text file outside the submodules:
- the repo-root path (`tools/x/y.py`, `./tools/x/y.py`, and any path under a moved folder), wherever it stands as a
  whole path: `mytools/x/y.py` and `tools/x/y.pyc` are left alone;
- relative links in Markdown and HTML (`](../x.md)`, `href="..."`, `src="..."`) that lead to a moved file, and the
  relative links inside a moved file, recomputed from its new folder;
- in a moved Python file, `Path(__file__).resolve().parents[N]` when N was its depth below the repo root (the repo
  root lookup), set to the new depth.

What it only reports, for a person or an agent to check: other lines that name a moved file by its file name alone,
`import <module>` lines for a moved Python module, and a moved file's other `__file__` lookups when its depth
changed. Paths built in pieces in code are not seen; ./tools/check.sh catches what is left.
"""
from __future__ import annotations

import argparse
import os
import posixpath
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import files  # noqa: E402

HISTORY_PREFIXES = ("archive/",)
HISTORY_FILES = ("wiki/STATUS_LOG.md",)
LINK_SUFFIXES = (".md", ".html", ".htm")
MAX_BYTES = 4 * 1024 * 1024
# a markdown link target, or an HTML href/src value
LINK_RE = re.compile(r'(\]\()([^)\s]+)((?:\s+"[^"]*")?\))|((?:href|src)=")([^"]+)(")')
PARENTS_RE = re.compile(r"(Path\(__file__\)\.resolve\(\)\.parents\[)(\d+)(\])")


class MoveError(Exception):
    pass


@dataclass
class Plan:
    old: str
    new: str
    moves: dict[str, str]                                   # tracked file: its new path
    edits: dict[str, tuple[str, str]] = field(default_factory=dict)   # file (current path): (old text, new text)
    notes: list[str] = field(default_factory=list)          # lines to check by hand


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise MoveError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def repo_root(start: Path) -> Path:
    return Path(git(start, "rev-parse", "--show-toplevel").strip())


def tracked_files(root: Path) -> list[str]:
    """Tracked paths that are files in this checkout (submodule entries and their contents left out)."""
    try:
        return files.tracked_files(root, submodules=False)
    except files.GitError as err:
        raise MoveError(str(err)) from err


def clean(path: str) -> str:
    path = posixpath.normpath(path.strip().replace(os.sep, "/"))
    if path.startswith("./"):
        path = path[2:]
    if path.startswith("/") or path.startswith("..") or path in ("", "."):
        raise MoveError(f"{path!r}: give a path from the repo root")
    return path


def plan_moves(root: Path, old: str, new: str, files: list[str]) -> dict[str, str]:
    same_name = new.lower() == old.lower()          # a case-only rename on a case-insensitive disk (the Mac)
    if (root / new).exists() and not same_name:
        raise MoveError(f"{new} already exists")
    if new == old or new.startswith(old + "/"):
        raise MoveError(f"cannot move {old} into itself")
    gitlinks = [line.split("\t", 1)[1] for line in git(root, "ls-files", "-s").splitlines()
                if line.startswith("160000")]
    for sub in gitlinks:
        if new == sub or new.startswith(sub + "/") or old.startswith(sub + "/") or old == sub:
            raise MoveError(f"{sub} is a submodule: move files there in its own repository")
    if old in files:
        return {old: new}
    under = {f: new + f[len(old):] for f in files if f.startswith(old + "/")}
    if not under:
        raise MoveError(f"{old} is not a tracked file or a folder of tracked files")
    return under


def is_history(path: str) -> bool:
    return path.startswith(HISTORY_PREFIXES) or path in HISTORY_FILES


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


REPO_VARS = re.compile(r"(ROOT|REPO|\w*_ROOT|\w*REPO\w*)$")   # shell variables that hold the repo root


def root_path_re(old: str) -> re.Pattern:
    """`old` as a whole repo-root path: at a start, after a character that cannot be part of a path, or after a
    leading `./` (not `../`, a relative path the link rewrite handles); and not running on into a longer name."""
    before = r"(?:(?<![\w.\-/])|(?<=\./)(?<!\.\./))"
    if "/" not in old:
        # one segment (docs, Makefile) is also a word: a path only with a slash after it, or alone in quotes
        return re.compile(before + re.escape(old) + r"(?=/)|(?<=[`'\"])" + re.escape(old) + r"(?=[`'\"])")
    return re.compile(before + re.escape(old) + r"(?![\w\-]|\.\w)")


def var_path_re(old: str) -> re.Pattern:
    """`old` after a shell variable and a slash (`"$ROOT/tools/x.sh"`, `${ROOT}/tools/x.sh`); group 2 is the name."""
    return re.compile(r"(\$\{?([A-Za-z_]\w*)\}?/)" + re.escape(old) + r"(?![\w\-]|\.\w)")


def map_path(target: str, old: str, moves: dict[str, str], new: str) -> str | None:
    """The new repo-root path of `target` if the move takes it (the folder itself or anything in or under it)."""
    if target in moves:
        return moves[target]
    if target == old:
        return new
    if target.startswith(old + "/"):
        return new + target[len(old):]
    return None


def rewrite_links(text: str, here_old: str, here_new: str, plan: Plan, known: set[str], root: Path) -> str:
    """Relative links in a Markdown or HTML file now at `here_old`, to be at `here_new`."""
    dir_old, dir_new = posixpath.dirname(here_old), posixpath.dirname(here_new)

    def fix(m: re.Match[str]) -> str:
        pre, target, post = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
        cut = min([i for i in (target.find("#"), target.find("?")) if i >= 0], default=len(target))
        path, frag = target[:cut], target[cut:]
        sep = ""
        if not path or re.match(r"^[a-z][a-z0-9+.-]*:", path, re.I) or path.startswith(("/", "<", "{", "$")):
            return m.group(0)
        resolved = posixpath.normpath(posixpath.join(dir_old, path))
        if resolved.startswith(".."):
            return m.group(0)
        moved = map_path(resolved, plan.old, plan.moves, plan.new)
        if moved is None:
            if dir_old == dir_new or not (resolved in known or (root / resolved).exists()):
                return m.group(0)
            moved = resolved
        rel = posixpath.relpath(moved, dir_new or ".")
        if path.endswith("/") and not rel.endswith("/"):
            rel += "/"
        return pre + rel + sep + frag + post

    return LINK_RE.sub(fix, text)


def build_plan(root: Path, old: str, new: str, include_history: bool = False) -> Plan:
    files = tracked_files(root)
    plan = Plan(old, new, plan_moves(root, old, new, files))
    known = set(files)
    known |= {posixpath.dirname(f) for f in files}
    path_re, var_re = root_path_re(old), var_path_re(old)
    # a file name shared by another tracked file (README.md, index.html) says nothing alone: not reported
    counts: dict[str, int] = {}
    for f in files:
        counts[posixpath.basename(f)] = counts.get(posixpath.basename(f), 0) + 1
    names = {posixpath.basename(f): f for f in plan.moves if counts[posixpath.basename(f)] == 1}
    modules = {posixpath.splitext(posixpath.basename(f))[0]: f for f in plan.moves
               if f.endswith(".py") and posixpath.dirname(f) != posixpath.dirname(plan.moves[f])}
    for f in files:
        moved = f in plan.moves
        if is_history(f) and not include_history and not moved:
            continue
        text = read_text(root / f)
        if text is None:
            continue
        here_new = plan.moves.get(f, f)
        out = text
        if f.endswith(LINK_SUFFIXES):
            out = rewrite_links(out, f, here_new, plan, known, root)
        out = path_re.sub(lambda m: new, out)
        out = var_re.sub(lambda m: m.group(1) + new if REPO_VARS.match(m.group(2)) else m.group(0), out)
        for n, line in enumerate(out.splitlines(), 1):
            for m in var_re.finditer(line):
                plan.notes.append(f"{here_new}:{n}: {old} after ${m.group(2)}, not the repo root: {line.strip()[:120]}")
        if moved and f.endswith(".py"):
            out = fix_depth(out, f, here_new, plan)
        if out != text:
            plan.edits[f] = (text, out)
        note_names(f, out, names, modules, plan)
    return plan


def fix_depth(text: str, old_file: str, new_file: str, plan: Plan) -> str:
    """A moved script's repo-root lookup (parents[depth]) follows it; other __file__ lookups are reported."""
    d_old, d_new = len(Path(old_file).parts) - 1, len(Path(new_file).parts) - 1
    if d_old == d_new:
        return text

    def fix(m: re.Match[str]) -> str:
        if int(m.group(2)) == d_old:
            return f"{m.group(1)}{d_new}{m.group(3)}"
        return m.group(0)

    lines = text.splitlines(keepends=True)
    out = []
    for n, line in enumerate(lines, 1):
        fixed = PARENTS_RE.sub(fix, line)
        if "__file__" in line and fixed == line:
            plan.notes.append(f"{new_file}:{n}: a __file__ lookup; the file is now {d_new} folder(s) deep, "
                              f"was {d_old}: {line.strip()[:120]}")
        out.append(fixed)
    return "".join(out)


def note_names(f: str, text: str, names: dict[str, str], modules: dict[str, str], plan: Plan) -> None:
    """Lines that still name a moved file by its file name alone, or import a moved module."""
    where = plan.moves.get(f, f)
    name_res = {name: re.compile(r"(?<![\w.\-])" + re.escape(name) + r"(?![\w\-])") for name in names}
    for n, line in enumerate(text.splitlines(), 1):
        for name, src in names.items():
            if name_res[name].search(line) and plan.moves[src] not in line and src != f:
                plan.notes.append(f"{where}:{n}: names {name} without its path: {line.strip()[:120]}")
        if f.endswith(".py"):
            for mod, src in modules.items():
                if src != f and re.match(rf"\s*(from\s+{re.escape(mod)}\s+import|import\s+{re.escape(mod)}\b)", line):
                    plan.notes.append(f"{where}:{n}: imports {mod}, which moved to "
                                      f"{posixpath.dirname(plan.moves[src])}/: check its sys.path")


def show(plan: Plan, apply: bool) -> None:
    print(f"move: {plan.old} -> {plan.new} ({len(plan.moves)} file(s))")
    for f in sorted(plan.edits):
        before, after = plan.edits[f]
        where = plan.moves.get(f, f)
        b_lines, a_lines = before.splitlines(), after.splitlines()
        changed = [i for i, (x, y) in enumerate(zip(b_lines, a_lines)) if x != y]
        print(f"edit {where}: {len(changed)} line(s)")
        for i in changed:
            print(f"  {i + 1:>5} - {b_lines[i].strip()[:160]}")
            print(f"        + {a_lines[i].strip()[:160]}")
    if plan.notes:
        print(f"check by hand ({len(plan.notes)}):")
        for note in plan.notes:
            print(f"  {note}")
    if not apply:
        print("nothing changed; --apply moves it and writes these edits")


def apply_plan(root: Path, plan: Plan) -> None:
    (root / plan.new).parent.mkdir(parents=True, exist_ok=True)
    git(root, "mv", plan.old, plan.new)
    for f, (_, text) in plan.edits.items():
        (root / plan.moves.get(f, f)).write_bytes(text.encode("utf-8"))    # line endings as read


def rebuild(root: Path, plan: Plan) -> None:
    """The generated files that list paths: the docs index, and, when the map changed, the map's agent-doc lane and
    its local pages (one plain build_pipeline_map.py run writes all three; the pages are not committed, ADR-036)."""
    steps = []
    if (root / "tools/ops/build_docs_index.py").is_file():
        steps.append([sys.executable, "tools/ops/build_docs_index.py"])
    if "docs/pipeline-map/pipeline_map.json" in plan.edits and (root / "tools/ops/build_pipeline_map.py").is_file():
        steps.append([sys.executable, "tools/ops/build_pipeline_map.py"])
    for cmd in steps:
        done = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        print(f"rebuilt: {' '.join(cmd[1:2])}" if done.returncode == 0 else
              f"REBUILD FAILED: {' '.join(cmd)}\n{done.stdout}{done.stderr}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--apply", action="store_true", help="move it and write the edits")
    ap.add_argument("--include-history", action="store_true", help="also rewrite archive/ and wiki/STATUS_LOG.md")
    ap.add_argument("--no-rebuild", action="store_true", help="skip the docs index and pipeline-map rebuild")
    args = ap.parse_args(argv)
    try:
        root = repo_root(Path.cwd())
        plan = build_plan(root, clean(args.old), clean(args.new), args.include_history)
        show(plan, args.apply)
        if args.apply:
            apply_plan(root, plan)
            if not args.no_rebuild:
                rebuild(root, plan)
            print("moved; now run ./tools/check.sh")
    except MoveError as exc:
        print(f"move_path.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
