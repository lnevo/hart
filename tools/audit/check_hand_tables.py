#!/usr/bin/env python3
"""No new railroad data typed into code: a top-level table in a script that holds the railroad's own names, or that
this check cannot tell from a code setting, fails unless tools/audit/hand_tables.csv lists it (the owner's rule:
anything kept by hand goes in a CSV read through hartlib).

    python3 tools/audit/check_hand_tables.py            # tools/check.sh runs it (job hand-tables)
    python3 tools/audit/check_hand_tables.py --list     # every table it finds, with its class and why
    python3 tools/audit/check_hand_tables.py --update   # drop rows for tables gone, lower entries that fell

What it reads. Every tracked .py outside archive/, external/ and reference/ (vendor and retired code) and every
tracked .js under www/, less tests (a tests/ folder, test_*.py) and minified or vendor files. A table is a top-level
assignment of a dict, list, tuple or set literal (also one wrapped in a call, such as frozenset({...})) with at least
MIN_ENTRIES entries and MIN_LITERALS string or number literals in it. Smaller lookups and tables inside functions
are not seen.

How it classes a table (classify):
- railroad: at least MIN_HITS different strings in it are railroad names or ids, as the data masters hold them
  (hartlib.hand_tables.railroad_names: the key and name columns of every CSV master in docs/data/entities.csv).
  It must be listed; its row's status is `move` until it moves to a CSV.
- setting: no railroad name, no number and no repo path (a string starting with a top folder of the repo and a
  slash), and every string in it is one word (no whitespace): column names, keywords, patterns, attribute names. It
  passes and is not listed.
- unclear: anything else (sentences, numbers by item, lists of repo files, rows of values). It must be listed; `unreviewed` until the
  owner decides, then `move` or `keep` with the reason.

A listed table may not grow: its entries may not pass the row's. A row for a table no longer found fails, so the
list only shrinks (--update drops such rows and lowers entries; it never adds a row or raises one). A new table that
must stay in code is added by hand with status keep and the reason.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import files, hand_tables, paths  # noqa: E402
from hartlib.hand_tables import HandTablesError, Listed  # noqa: E402

REPO = paths.REPO_ROOT
SCAN_GLOBS = ("**/*.py", "www/**/*.js")
SKIP = ("archive/", "external/", "reference/")
ENTITIES = "docs/data/entities.csv"
LISTED = "tools/audit/hand_tables.csv"
MIN_ENTRIES = 4
MIN_LITERALS = 8
MIN_HITS = 2
ONE_WORD = re.compile(r"\S*")


@dataclass(frozen=True)
class Table:
    file: str
    name: str
    line: int
    entries: int
    strings: tuple[str, ...]      # every string literal in it, keys and values
    numbers: int                  # how many number literals


def is_scanned(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return not (path.startswith(SKIP) or "/tests/" in f"/{path}" or name.startswith("test_")
                or name.endswith(".min.js") or "/vendor/" in f"/{path}")


def scripts(root: Path = REPO) -> list[str]:
    return sorted({p for g in SCAN_GLOBS for p in files.tracked_files(root, f":(glob){g}", submodules=False)
                   if is_scanned(p) and (root / p).is_file()})


# ---------------------------------------------------------------- Python

def py_tables(path: str, src: str) -> list[Table]:
    """The top-level tables of a Python script's text ([] when Python 3 cannot parse it: Jython is left out)."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):     # ValueError: a NUL byte, before Python 3.12
        return []
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            name, value = node.target.id, node.value
        else:
            continue
        if isinstance(value, ast.Call) and len(value.args) == 1:
            value = value.args[0]
        if not isinstance(value, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
            continue
        entries = len(value.keys) if isinstance(value, ast.Dict) else len(value.elts)
        consts = [c.value for c in ast.walk(value) if isinstance(c, ast.Constant)]
        strings = tuple(c for c in consts if isinstance(c, str))
        numbers = sum(1 for c in consts if isinstance(c, (int, float)) and not isinstance(c, bool))
        out.append(Table(path, name, node.lineno, entries, strings, numbers))
    return out


# ---------------------------------------------------------------- JavaScript

# a table: `const|let|var NAME = ` then `[` or `{`, or one wrapper call round it (Object.freeze, new Map, new Set)
JS_START = re.compile(r"^(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
                      r"(?:Object\.freeze\(|new\s+(?:Map|Set)\()?(?=[\[{])", re.M)
JS_TOKEN = re.compile(r"""(?P<skip>\s+|//[^\n]*|/\*.*?\*/)"""
                      r"""|(?P<str>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)"""
                      r"""|(?P<key>[A-Za-z_$][\w$]*)(?=\s*:)|(?P<num>\d+(?:\.\d+)?)(?![\w$])"""
                      r"""|(?P<word>[A-Za-z_$][\w$]*)|(?P<op>[\[\]{}(),:]|=>|.)""", re.S)
# a regex literal, taken where the token before a `/` cannot end a value (so `/` is not division)
JS_REGEX = re.compile(r"/(?![*/])(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n\[])+/[a-z]*")
REGEX_AFTER = {"[", "(", ",", ":", "=", "!", "&", "|", "?", "{", ";", "=>", "return"}


def _unquote(tok: str) -> str:
    return re.sub(r"\\(.)", r"\1", tok[1:-1])


def js_tokens(src: str, pos: int) -> Iterator[tuple[str, str]]:
    """(kind, text) of the tokens of `src` from `pos`: str, key (a bare object key), num, word, op and regex, with
    whitespace and comments dropped."""
    prev = "="
    while pos < len(src):
        if src[pos] == "/" and prev in REGEX_AFTER:
            rx = JS_REGEX.match(src, pos)
            if rx:
                pos = rx.end()
                prev = "regex"
                yield "regex", rx.group()
                continue
        m = JS_TOKEN.match(src, pos)
        if m is None:
            return
        pos = m.end()
        kind = m.lastgroup or "op"
        if kind == "skip":
            continue
        prev = m.group() if kind in ("op", "word") else kind
        yield kind, m.group()


def js_tables(path: str, src: str) -> list[Table]:
    """The tables of a script's text that start a line as JS_START. A lexical scan: strings, template strings,
    comments and regex literals are whole tokens, a bare object key counts as a string, and an entry is an item
    at depth 1 (a trailing comma adds none)."""
    out = []
    for m in JS_START.finditer(src):
        depth, entries, item, strings, numbers = 0, 0, False, [], 0
        for kind, t in js_tokens(src, m.end()):
            if kind == "op" and t in "[{(":
                depth += 1
                item = item or depth == 2
            elif kind == "op" and t in "]})":
                depth -= 1
                if depth == 0:
                    break
            elif kind == "op" and t == "," and depth == 1:
                entries, item = entries + item, False
            elif kind in ("str", "key"):
                strings.append(_unquote(t) if kind == "str" else t)
                item = item or depth == 1
            elif kind == "num":
                numbers += 1
                item = item or depth == 1
            elif depth == 1 and kind in ("word", "regex"):
                item = True
        entries += item
        line = src.count("\n", 0, m.start()) + 1
        out.append(Table(path, m.group(1), line, entries, tuple(strings), numbers))
    return out


def tables_in(path: str, src: str) -> list[Table]:
    found = js_tables(path, src) if path.endswith(".js") else py_tables(path, src)
    return [t for t in found if t.entries >= MIN_ENTRIES and len(t.strings) + t.numbers >= MIN_LITERALS]


# ---------------------------------------------------------------- classes

def top_dirs(root: Path = REPO) -> frozenset[str]:
    """The top folders of the files git tracks at `root`."""
    return frozenset(p.split("/", 1)[0] for p in files.tracked_files(root, submodules=False) if "/" in p)


def is_repo_path(s: str, tops: frozenset[str]) -> bool:
    """A string that starts with one of the top folders `tops` and a slash, such as tools/audit/."""
    head, sep, _ = s.lstrip("./").partition("/")
    return bool(sep) and head in tops


def classify(table: Table, names: dict[str, str], tops: frozenset[str] = frozenset()) -> tuple[str, str]:
    """(railroad | setting | unclear, why) of a table, against `names` (railroad_names) and the checkout's top
    folders `tops` (top_dirs)."""
    hits = sorted({s for s in table.strings if s in names})
    if len(hits) >= MIN_HITS:
        shown = ", ".join(hits[:3]) + (f" and {len(hits) - 3} more" if len(hits) > 3 else "")
        kinds = sorted({names[h].split(" (")[0] for h in hits})
        return "railroad", f"{len(hits)} railroad names ({shown}; {', '.join(kinds)})"
    if any(is_repo_path(s, tops) for s in table.strings):
        return "unclear", "names repo files: an exception list?"
    if table.strings and not table.numbers and all(ONE_WORD.fullmatch(s) for s in table.strings):
        return "setting", "one-word strings only: no railroad name, number or repo path"
    if any(len(s.split()) >= 4 for s in table.strings):
        return "unclear", "holds sentences: page or card text?"
    if table.numbers >= table.entries:
        return "unclear", "numbers by item: per-item tweaks or code constants?"
    return "unclear", "rows of values the rule cannot place"


def found_tables(root: Path = REPO) -> list[Table]:
    out = []
    for path in scripts(root):
        src = (root / path).read_text(encoding="utf-8", errors="replace")
        out += tables_in(path, src)
    return out


def problems(tables: list[Table], names: dict[str, str], listed: dict[tuple[str, str], Listed],
             tops: frozenset[str] = frozenset()) -> list[str]:
    out = []
    seen = set()
    for t in tables:
        cls, why = classify(t, names, tops)
        key = (t.file, t.name)
        row = listed.get(key)
        if row is not None:
            seen.add(key)
            if t.entries > row.entries:
                out.append(f"{t.file}:{t.line}: {t.name} has {t.entries} entries, more than its {row.entries} in "
                           "hand_tables.csv: a listed table may not grow; put the new entries in a CSV")
        elif cls != "setting":
            out.append(f"{t.file}:{t.line}: {t.name} is {'an' if cls == 'unclear' else 'a'} {cls} table ({why}); railroad data goes in a CSV read "
                       "through hartlib, or list it in tools/audit/hand_tables.csv with status keep and the reason")
    for key in sorted(set(listed) - seen):
        out.append(f"tools/audit/hand_tables.csv: {key[0]} {key[1]} is no longer found; drop its row (--update)")
    return out


def updated(tables: list[Table], listed: dict[tuple[str, str], Listed]) -> list[Listed]:
    """The rows --update writes: rows of tables still found, entries lowered where the table shrank."""
    now: dict[tuple[str, str], int] = {}
    for t in tables:                     # a name assigned twice in a file: its largest copy
        now[(t.file, t.name)] = max(now.get((t.file, t.name), 0), t.entries)
    return [Listed(r.file, r.table, min(r.entries, now[k]), r.status, r.reason)
            for k, r in listed.items() if k in now]


def main(argv: list[str] | None = None, root: Path = REPO) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="print every table found, with its class and why")
    ap.add_argument("--update", action="store_true", help="drop rows of tables gone and lower entries that fell")
    args = ap.parse_args(argv)
    try:
        names = hand_tables.railroad_names(root / ENTITIES, root)
        listed = hand_tables.read_listed(root / LISTED)
        tables = found_tables(root)
        tops = top_dirs(root)
    except (HandTablesError, files.GitError) as exc:
        print(f"check_hand_tables: {exc}", file=sys.stderr)
        return 2
    if args.list:
        for t in tables:
            cls, why = classify(t, names, tops)
            row = listed.get((t.file, t.name))
            print(f"{t.file}:{t.line}\t{t.name}\t{cls}\t{row.status if row else '-'}\t{why}")
        return 0
    if args.update:
        rows = updated(tables, listed)
        hand_tables.write_listed(root / LISTED, rows)
        print(f"check_hand_tables: {len(rows)} rows kept, {len(listed) - len(rows)} dropped")
        return 0
    found = problems(tables, names, listed, tops)
    for line in found:
        print(line)
    counts = {s: sum(1 for r in listed.values() if r.status == s) for s in hand_tables.STATUSES}
    print(f"check_hand_tables: {len(tables)} tables, {len(listed)} listed "
          f"({', '.join(f'{n} {s}' for s, n in counts.items())}); {len(found)} problems")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
