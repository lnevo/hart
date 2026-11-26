#!/usr/bin/env python3
"""Ratchet on five code habits in the tracked Python files: a file's count of each may go down, never up.

    python3 tools/audit/check_habits.py            fail when a count rises above tools/audit/habits_baseline.json
    python3 tools/audit/check_habits.py --update   write the lower counts; refuses while any count is higher

The habits, counted per file over tracked CPython and Jython .py files (not archive/, external/, reference/, the
parked features or tools/cats/src-repo/):
- lost-cause: `raise X(str(err)) from None` or `raise X(f"...{err}...") from None` inside `except ... as err`: the
  message keeps the error's text but the traceback loses it. A bare `from None` that drops no cause is allowed.
- dated-note: a dated owner note such as "(owner, <date>)" with a real date in a comment or docstring; git and the wiki hold it.
- source-asserts: in a test file whose asserts mostly test the text of a .py file it read, each such assert.
- import-exit: `raise SystemExit` or `sys.exit(...)` outside `main()` and outside `if __name__ == "__main__":`, in a
  file other files import.
- exec-parts: `exec(...)` or `globals().update(...)`, the ways a script loads its parts into its own namespace.

A count below the baseline passes with one note; --update locks the lower count in. A new file with a habit is a rise
from 0, so it fails.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal, get_args

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.files import GitError, tracked_files  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tools/audit/habits_baseline.json"
# what it reads: every tracked .py file (the step's quiet_inputs in tools/pipeline/checks.toml are these)
SCAN_GLOBS = ("**/*.py",)
EXCLUDED = ("archive/", "external/", "reference/", "jmri/layouts/hart/parked/", "tools/cats/src-repo/")
Habit = Literal["lost-cause", "dated-note", "source-asserts", "import-exit", "exec-parts"]
HABITS: tuple[str, ...] = get_args(Habit)
Counts = dict[str, dict[str, int]]

DATED_NOTE = re.compile(r"owner,?\s*20\d\d-\d\d-\d\d", re.I)   # "(owner, 2026-...)", "owner 2026-...", "(owner, 2026-...: ...)"
# Python 2 (Jython) files ast cannot parse: the two habits a line can show
PY2_LOST_CAUSE = re.compile(r"\braise\b[^\n]*\b(?:str\(\w+\)|\{\w+[^}]*\})[^\n]*\bfrom\s+None\b")
PY2_EXEC = re.compile(r"^\s*(?:exec\b|.*\bglobals\(\)\.update\()", re.M)
IMPORT_NAME = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w., ]+))", re.M)
FILE_NAME = re.compile(r"""["'/\\]([A-Za-z_]\w*)\.py["']""")


class HabitsError(Exception):
    """The files or the baseline cannot be read; the message names which and why."""


def in_scope(rel: str) -> bool:
    return rel.endswith(".py") and not rel.startswith(EXCLUDED)


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def lost_causes(tree: ast.AST) -> int:
    """Raises `from None` inside `except ... as name` whose new exception reads `name`."""
    found: set[int] = set()          # a raise inside nested handlers is one raise
    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler) or not handler.name:
            continue
        for node in (n for stmt in handler.body for n in ast.walk(stmt)):
            if (isinstance(node, ast.Raise) and isinstance(node.cause, ast.Constant) and node.cause.value is None
                    and node.exc is not None and handler.name in _names(node.exc)):
                found.add(id(node))
    return len(found)


def dated_notes(text: str) -> int:
    """Dated owner notes in comments and strings (docstrings among them); the whole text when it does not tokenize."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return len(DATED_NOTE.findall(text))
    kinds = {tokenize.COMMENT, tokenize.STRING, *([tokenize.FSTRING_MIDDLE] if hasattr(tokenize, "FSTRING_MIDDLE") else [])}
    return sum(len(DATED_NOTE.findall(t.string)) for t in tokens if t.type in kinds)


def is_test(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.startswith("test_") or "/tests/" in f"/{rel}"


READERS = ("read_text", "read", "source", "getsource")


def _source_vars(tree: ast.Module) -> set[str]:
    """Names (and self.attributes) bound to the text of a .py file: a read (read_text, read, inspect.getsource, a
    source() helper) of something that names a .py file, or a call of a function in the file that returns one."""
    py_names = {t.id for node in tree.body if isinstance(node, ast.Assign) and ".py" in ast.unparse(node.value)
                for t in node.targets if isinstance(t, ast.Name)}
    funcs: set[str] = set()

    def is_source(expr: ast.AST) -> bool:
        calls = [c for c in ast.walk(expr) if isinstance(c, ast.Call)]
        called = {c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", "") for c in calls}
        if called & funcs:
            return True
        return bool(called & set(READERS)) and (".py" in ast.unparse(expr) or bool(_names(expr) & py_names))

    defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for _ in range(2):          # a helper may call another helper
        funcs |= {d.name for d in defs if any(isinstance(r, ast.Return) and r.value is not None and is_source(r.value)
                                              for r in ast.walk(d))}
    found: set[str] = set(funcs)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and is_source(node.value):
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                if isinstance(t, ast.Name):
                    found.add(t.id)
                elif isinstance(t, ast.Attribute):
                    found.add(t.attr)
    return found


def _refers(node: ast.AST, names: set[str]) -> bool:
    return any(isinstance(n, ast.Name) and n.id in names or isinstance(n, ast.Attribute) and n.attr in names
               for n in ast.walk(node))


def source_asserts(tree: ast.Module) -> int:
    """In a test file, the asserts that check a .py file's text for a substring; 0 unless they are most asserts."""
    sources = _source_vars(tree)
    total = text_checks = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.startswith("assert"):
            total += 1
            if node.func.attr in ("assertIn", "assertNotIn") and len(node.args) >= 2 and _refers(node.args[1], sources):
                text_checks += 1
        elif isinstance(node, ast.Assert):
            total += 1
            test = node.test.operand if isinstance(node.test, ast.UnaryOp) else node.test
            if (isinstance(test, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in test.ops)
                    and any(_refers(c, sources) for c in test.comparators)):
                text_checks += 1
    return text_checks if sources and text_checks * 2 > total else 0


def _is_main_guard(node: ast.AST) -> bool:
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
            and "__name__" in _names(node.test) and "__main__" in ast.unparse(node.test))


def _is_exit(node: ast.AST) -> bool:
    if isinstance(node, ast.Raise) and node.exc is not None:
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        return isinstance(exc, ast.Name) and exc.id == "SystemExit"
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "exit"
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "sys")


def _is_hartlib_bootstrap(node: ast.AST) -> bool:
    """`sys.path[:0] = [...] or sys.exit(...)`: the standard line that finds hartlib, which may stop a script."""
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return False
    target = node.targets[0]
    return (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Attribute)
            and target.value.attr == "path" and isinstance(target.value.value, ast.Name)
            and target.value.value.id == "sys")


def import_exits(tree: ast.AST) -> int:
    """Exits outside main(), the __main__ block and the hartlib bootstrap line."""
    count = 0

    def visit(node: ast.AST) -> None:
        nonlocal count
        for child in ast.iter_child_nodes(node):
            if _is_main_guard(child) or isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "main":
                continue
            if _is_hartlib_bootstrap(child):
                continue
            if _is_exit(child):
                count += 1
            visit(child)
    visit(tree)
    return count


def exec_parts(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name) and f.id == "exec":
            count += 1
        elif (isinstance(f, ast.Attribute) and f.attr == "update" and isinstance(f.value, ast.Call)
              and isinstance(f.value.func, ast.Name) and f.value.func.id == "globals"):
            count += 1
    return count


def imported_stems(texts: Mapping[str, str]) -> set[str]:
    """Module names some file imports, by an import statement or by naming the file (importlib, execfile)."""
    stems: set[str] = set()
    for text in texts.values():
        for frm, imp in IMPORT_NAME.findall(text):
            for name in ([frm] if frm else [n.strip().split(" ")[0] for n in imp.split(",")]):
                stems.add(name.rsplit(".", 1)[-1])
        stems.update(FILE_NAME.findall(text))
    return stems


def count_file(rel: str, text: str, imported: bool) -> dict[str, int]:
    """The habit counts of one file, without the zeros."""
    try:
        tree = ast.parse(text)
    except SyntaxError:        # a Python 2 (Jython) file: line patterns only
        counts = {"lost-cause": len(PY2_LOST_CAUSE.findall(text)), "dated-note": len(DATED_NOTE.findall(text)),
                  "exec-parts": len(PY2_EXEC.findall(text))}
    else:
        counts = {"lost-cause": lost_causes(tree), "dated-note": dated_notes(text),
                  "source-asserts": source_asserts(tree) if is_test(rel) else 0,
                  "import-exit": import_exits(tree) if imported else 0,
                  "exec-parts": exec_parts(tree)}
    return {h: n for h, n in counts.items() if n}


def count_all(root: Path, files: Iterable[str]) -> Counts:
    texts: dict[str, str] = {}
    for rel in files:
        path = root / rel
        if not path.is_file():      # tracked, deleted, not yet staged
            continue
        try:
            texts[rel] = path.read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            raise HabitsError(f"cannot read {rel}: {err}") from err
    stems = imported_stems(texts)
    out = {rel: count_file(rel, text, Path(rel).stem in stems) for rel, text in sorted(texts.items())}
    return {rel: c for rel, c in out.items() if c}


def scan(root: Path = ROOT) -> Counts:
    try:
        files = tracked_files(root, *(f":(glob){g}" for g in SCAN_GLOBS))
    except GitError as err:
        raise HabitsError(str(err)) from err
    return count_all(root, (f for f in files if in_scope(f)))


def read_baseline(path: Path = BASELINE) -> Counts | None:
    """The committed counts, or None when there is no baseline file yet."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as err:
        raise HabitsError(f"cannot read {path}: {err}") from err
    if not isinstance(data, dict):
        raise HabitsError(f"{path}: must be an object of file -> habit -> count")
    for rel, counts in data.items():
        if not isinstance(counts, dict) or any(h not in HABITS or not isinstance(n, int) or n < 1
                                               for h, n in counts.items()):
            raise HabitsError(f"{path}: {rel}: each count must be a habit ({', '.join(HABITS)}) and a whole number "
                              f"above 0")
    return data


def compare(now: Counts, base: Counts) -> tuple[list[str], list[str]]:
    """(rises, falls): each file and habit whose count is above, or below, the baseline."""
    rises, falls = [], []
    for rel in sorted({*now, *base}):
        for habit in HABITS:
            a, b = base.get(rel, {}).get(habit, 0), now.get(rel, {}).get(habit, 0)
            if b > a:
                rises.append(f"{rel}: {habit} {a} -> {b}")
            elif b < a:
                falls.append(f"{rel}: {habit} {a} -> {b}")
    return rises, falls


def baseline_text(counts: Counts) -> str:
    return json.dumps({rel: dict(sorted(c.items())) for rel, c in sorted(counts.items())}, indent=1) + "\n"


def main(argv: list[str] | None = None, root: Path = ROOT, baseline: Path = BASELINE) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update", action="store_true",
                    help="write the lower counts to the baseline (or the first baseline, when there is none)")
    args = ap.parse_args(argv)
    try:
        now, base = scan(root), read_baseline(baseline)
    except HabitsError as err:
        print(f"FAIL {err}")
        return 1
    if base is None:
        if not args.update:
            print(f"FAIL no baseline at {baseline}: run {Path(__file__).name} --update once to write the first one")
            return 1
        baseline.write_text(baseline_text(now), encoding="utf-8")
        print(f"wrote the first baseline, {baseline}: {len(now)} file(s)")
        return 0
    rises, falls = compare(now, base)
    for line in rises:
        print(f"FAIL higher than the baseline: {line} (fix the new ones; the baseline never goes up)")
    if args.update:
        if rises:
            print(f"refused: {len(rises)} count(s) are higher; {baseline} is unchanged")
            return 1
        baseline.write_text(baseline_text(now), encoding="utf-8")
        print(f"wrote {baseline}: {len(falls)} count(s) lowered")
        return 0
    if rises:
        return 1
    if falls:
        # a note, not a failure: with strict up-to-date merges a fall on main would otherwise fail every open branch
        files_below = len({line.split(": ", 1)[0] for line in falls})
        print(f"{files_below} file(s) below the baseline; `--update` locks them in")
    total = {h: sum(c.get(h, 0) for c in now.values()) for h in HABITS}
    print("OK: no habit count rose (" + ", ".join(f"{h} {n}" for h, n in total.items()) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
