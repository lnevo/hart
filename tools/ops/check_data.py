#!/usr/bin/env python3
"""Check every master CSV against the column sidecar beside it (ADR-039, decision 3; docs/data/sidecars.md).

A sidecar `<name>.columns.csv` has one row per column of its master, in the master's order. Its columns:
  column       the master column it describes
  file         (optional) for a pair master, which file holds the column: field or generated
  description  text for people
  type         str, int, float, bool (yes or no), enum (one of `values`) or id-list (items separated by ;)
  required     yes, or a condition `col=v1;v2` (empty after = means col is empty): the cell is non-empty on those rows
  key          yes, or a condition: the columns with the same key cell form one key, non-empty and unique on those rows
  refs         `path/file.csv:column`, several separated by ;: each value, or each id-list item, is in one of them
  values       the allowed values of an enum column, separated by ;
An empty rule cell means no rule. Only `column` and `description` must be there.

The master is `<name>.csv` beside the sidecar. When there is none, it is the pair `<name>_generated.csv` (every row
the builders make) and `<name>_field.csv` (the owner's cells), merged as hartlib.devices merges them: a field row is
matched to the generated row with the same key, and its non-empty cells win; a field row with no match is added
when its key keys no generated row (a Store's level-less rows), and is an error otherwise (a stale field row).
A refs path names a master the same way, so `devices.csv:user_name` reads the merged device pair.

Sidecars are the files git lists for SCAN_GLOBS, tracked or untracked but not ignored, leaving out SKIP and folders
whose names start with a dot, so a new sidecar is checked with no list to edit.

    python3 tools/ops/check_data.py              check every sidecar (exit 1 on a problem)
    python3 tools/ops/check_data.py PATH ...     check only these sidecars
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
ROOT = paths.REPO_ROOT
SUFFIX = ".columns.csv"
SCAN_GLOBS = (f"**/*{SUFFIX}",)     # what find_sidecars lists, as git :(glob) pathspecs (checks.toml quiet_inputs)
SKIP =("archive", "external", "reference", "node_modules", "tools/cats/src-repo")   # from the repo root
SIDECAR_COLUMNS = ("column", "file", "description", "type", "required", "key", "refs", "values")
RULE_COLUMNS = ("type", "required", "key", "refs", "values")
TYPES = ("str", "int", "float", "bool", "enum", "id-list")
LIST = ";"
PAIR = ("generated", "field")       # a pair master's files: <name>_generated.csv, then <name>_field.csv over it
MAX_SHOWN = 20                      # problems shown per rule before a count
INT = re.compile(r"-?\d+")
FLOAT = re.compile(r"-?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?")


class DataError(Exception):
    """A sidecar or master that cannot be read or does not hold together."""


def find_sidecars(root: Path = ROOT) -> list[Path]:
    """Every sidecar git lists under root (SCAN_GLOBS, tracked or untracked and not ignored), sorted, outside SKIP and
    dot folders. DataError when git cannot list them."""
    try:
        done = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--",
                               *(f":(glob){g}" for g in SCAN_GLOBS)], cwd=root, capture_output=True, text=True)
    except OSError as exc:
        raise DataError(f"git ls-files could not run: {exc}") from exc
    if done.returncode:
        raise DataError(f"git ls-files failed: {done.stderr.strip() or f'exit {done.returncode}'}")
    rels = sorted({p for p in done.stdout.split("\0") if p and (root / p).is_file()})   # not one deleted, unstaged
    return [root / p for p in rels
            if not any(p == s or p.startswith(f"{s}/") for s in SKIP) and not any(d.startswith(".") for d in p.split("/"))]


def _read_csv(path: Path) -> list[list[str]]:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.reader(fh))
    except (OSError, UnicodeDecodeError) as exc:
        raise DataError(f"{_rel(path)}: cannot read it ({exc})") from exc


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def parse_condition(cell: str, columns: list[str], where: str) -> tuple[str, frozenset[str]] | None:
    """`yes` -> None (every row); `col=v1;v2` -> (col, {v1, v2}); `col=` -> (col, {""})."""
    if cell == "yes":
        return None
    col, eq, vals = cell.partition("=")
    if not eq or col not in columns:
        raise DataError(f"{where}: {cell!r} is not yes or a condition col=value;value on one of its columns")
    return col, frozenset(vals.split(LIST))


def _holds(cond: tuple[str, frozenset[str]] | None, row: dict[str, str]) -> bool:
    return cond is None or row[cond[0]] in cond[1]


def read_sidecar(path: Path) -> list[dict[str, str]]:
    """The sidecar's rows as dicts with every SIDECAR_COLUMNS key; DataError on a bad header, type or rule."""
    rows = _read_csv(path)
    where = _rel(path)
    if not rows:
        raise DataError(f"{where}: empty")
    head = rows[0]
    if "column" not in head or "description" not in head or any(h not in SIDECAR_COLUMNS for h in head) \
            or len(set(head)) != len(head):
        raise DataError(f"{where}: the header {','.join(head)} needs column and description and only "
                        f"{','.join(SIDECAR_COLUMNS)}")
    out = []
    for line, r in enumerate(rows[1:], 2):
        if len(r) != len(head):
            raise DataError(f"{where} line {line}: {len(r)} fields, expected {len(head)}")
        out.append({c: "" for c in SIDECAR_COLUMNS} | dict(zip(head, r)))
    names = [r["column"] for r in out]
    dup = sorted({c for c in names if names.count(c) > 1})
    if dup:
        raise DataError(f"{where}: described twice: {', '.join(dup)}")
    for line, row in enumerate(out, 2):
        at = f"{where} line {line} ({row['column']})"
        if row["type"] and row["type"] not in TYPES:
            raise DataError(f"{at}: type {row['type']!r} is not one of {', '.join(TYPES)}")
        if (row["type"] == "enum") != bool(row["values"]):
            raise DataError(f"{at}: an enum column has values, and only an enum column")
        for rule in ("required", "key"):
            if row[rule]:
                parse_condition(row[rule], names, at)
        for ref in filter(None, row["refs"].split(LIST)):
            if ":" not in ref:
                raise DataError(f"{at}: refs {ref!r} is not path/file.csv:column")
    return out


def master_files(sidecar: Path) -> list[Path]:
    """The master's file(s) for a sidecar or a refs path: <name>.csv, else the pair (generated, then field)."""
    base = sidecar.name[:-len(SUFFIX)] if sidecar.name.endswith(SUFFIX) else sidecar.name[:-len(".csv")]
    single = sidecar.parent / f"{base}.csv"
    if single.is_file():
        return [single]
    pair = [sidecar.parent / f"{base}_{p}.csv" for p in PAIR]
    if all(p.is_file() for p in pair):
        return pair
    raise DataError(f"{_rel(single)}: no master (nor {pair[0].name} with {pair[1].name})")


def _key_groups(spec: list[dict[str, str]]) -> dict[str, list[str]]:
    """{key cell: [columns]} in sidecar order; the columns with one key cell form one key."""
    groups: dict[str, list[str]] = {}
    for r in spec:
        if r["key"]:
            groups.setdefault(r["key"], []).append(r["column"])
    return groups


def _row_key(row: dict[str, str], groups: dict[str, list[str]], names: list[str]) -> tuple | None:
    for cell, cols in groups.items():
        if _holds(parse_condition(cell, names, ""), row):
            return (cell, *(row[c] for c in cols))
    return None


def read_table(path: Path, names: list[str] | None = None) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """(header, rows, where each row is: "file line N") of one CSV; DataError when the header is not `names` (when
    given) or a row has the wrong number of fields (a blank line is one with none)."""
    table = _read_csv(path)
    if not table or (names is not None and table[0] != names):
        raise DataError(f"{_rel(path)}: the header is not the sidecar's columns in order")
    head = table[0]
    bad = [i for i, r in enumerate(table[1:], 2) if len(r) != len(head)]
    if bad:
        raise DataError(f"{_rel(path)} line {bad[0]}: {len(table[bad[0] - 1])} fields, expected {len(head)}")
    return head, [dict(zip(head, r)) for r in table[1:]], [f"{path.name} line {i}" for i in range(2, len(table) + 1)]


def load_master(files: list[Path], spec: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    """(rows, where each row is) of the master; a pair merged (module docstring). DataError when a header is not the
    sidecar's columns, or a field row has no generated row under a key that keys generated rows (a stale field row;
    only a key no generated row has, such as a Store's level-less rows, may add rows)."""
    names = [r["column"] for r in spec]
    _, merged, where = read_table(files[0], names)
    if len(files) == 2:
        groups = _key_groups(spec)
        if not groups:
            raise DataError(f"{_rel(files[1])}: a pair master needs a key in its sidecar")
        by_key = {k: r for r in merged if (k := _row_key(r, groups, names)) is not None}
        generated_groups = {k[0] for k in by_key}
        _, field, field_where = read_table(files[1], names)
        stale = []
        for frow, fwhere in zip(field, field_where):
            key = _row_key(frow, groups, names)
            if key in by_key:
                by_key[key].update({c: v for c, v in frow.items() if v})
            elif key is not None and key[0] in generated_groups:
                stale.append(f"{fwhere} ({'/'.join(key[1:])})")
            else:
                merged.append(frow)
                where.append(fwhere)
        if stale:
            raise DataError(f"{files[1].name}: field rows with no {files[0].name} row: {'; '.join(stale)}")
    return merged, where


def _items(rule: dict[str, str], value: str) -> list[str]:
    return value.split(LIST) if rule["type"] == "id-list" else [value]


def _type_problem(rule: dict[str, str], value: str) -> str | None:
    kind = rule["type"]
    if kind == "int" and not INT.fullmatch(value):
        return "is not an integer"
    if kind == "float" and not FLOAT.fullmatch(value):
        return "is not a number"
    if kind == "bool" and value not in ("yes", "no"):
        return "is not yes or no"
    if kind == "enum" and value not in rule["values"].split(LIST):
        return f"is not one of {rule['values']}"
    if kind == "id-list":
        items = value.split(LIST)
        if any(not i or i != i.strip() for i in items):
            return "has an empty or padded item"
        if len(set(items)) != len(items):
            return "names an item twice"
    return None


class Checker:
    """Checks sidecars; caches each master it loads, so refs to one master read it once."""

    def __init__(self) -> None:
        self._masters: dict[Path, tuple[list[str], list[str], list[dict[str, str]], list[str]]] = {}

    def master(self, sidecar_or_csv: Path) -> tuple[list[str], list[str], list[dict[str, str]], list[str]]:
        """(file names, header, merged rows, where each row is) of the master a sidecar or a refs path names."""
        p = sidecar_or_csv.resolve()
        if p not in self._masters:
            base = p.name[:-len(SUFFIX)] if p.name.endswith(SUFFIX) else p.name[:-len(".csv")]
            side = p.parent / f"{base}{SUFFIX}"
            files = master_files(p)
            if side.is_file():
                spec = read_sidecar(side)
                head = [r["column"] for r in spec]
                rows, where = load_master(files, spec)
            else:
                head, rows, where = read_table(files[0])
            self._masters[p] = ([f.name for f in files], head, rows, where)
        return self._masters[p]

    def ref_values(self, ref: str, where: str) -> set[str]:
        path, _, col = ref.rpartition(":")
        try:
            _, head, rows, _ = self.master(ROOT / path)
        except DataError as exc:
            raise DataError(f"{where}: refs {ref}: {exc}") from exc
        if col not in head:
            raise DataError(f"{where}: refs {ref}: no column {col}")
        return {r[col] for r in rows}

    def check(self, sidecar: Path) -> list[str]:
        """The problems of one sidecar and its master, each a line; DataError when they cannot be read."""
        spec = read_sidecar(sidecar)
        names = [r["column"] for r in spec]
        files, _, rows, wheres = self.master(sidecar)
        label = " + ".join(files)
        line_of = {id(r): w for r, w in zip(rows, wheres)}
        problems: list[str] = []

        def report(what: str, found: list[str]) -> None:
            if found:
                more = f" (and {len(found) - MAX_SHOWN} more)" if len(found) > MAX_SHOWN else ""
                problems.append(f"{label}: {what}: {'; '.join(found[:MAX_SHOWN])}{more}")

        def at(row: dict[str, str]) -> str:
            keys = [row[c] for cols in _key_groups(spec).values() for c in cols if row[c]]
            return "/".join(keys) or line_of[id(row)]

        for rule in spec:
            col = rule["column"]
            if rule["required"]:
                cond = parse_condition(rule["required"], names, col)
                report(f"{col} is required" + (f" where {cond[0]} is {'|'.join(sorted(cond[1]))}" if cond else ""),
                       [at(r) for r in rows if _holds(cond, r) and not r[col]])
            if rule["type"]:
                report(f"{col} ({rule['type']})",
                       [f"{at(r)} {r[col]!r} {msg}" for r in rows if r[col] and (msg := _type_problem(rule, r[col]))])
            if rule["refs"]:
                known: set[str] = set()
                for ref in rule["refs"].split(LIST):
                    known |= self.ref_values(ref, f"{_rel(sidecar)} ({col})")
                report(f"{col} names what is not in {rule['refs']}",
                       [f"{at(r)} {i!r}" for r in rows if r[col] for i in _items(rule, r[col]) if i and i not in known])
        for cell, cols in _key_groups(spec).items():
            cond = parse_condition(cell, names, ",".join(cols))
            seen: dict[tuple, int] = {}
            empty, dups = [], []
            for r in rows:
                if not _holds(cond, r):
                    continue
                k = tuple(r[c] for c in cols)
                if not all(k):
                    empty.append(at(r))
                elif k in seen:
                    dups.append("/".join(k))
                seen[k] = seen.get(k, 0) + 1
            report(f"key {','.join(cols)} is empty", empty)
            report(f"key {','.join(cols)} is not unique", dups)
        return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sidecars", nargs="*", type=Path, help="sidecars to check (default: every one in the repo)")
    args = ap.parse_args(argv)
    sidecars = args.sidecars or find_sidecars()
    if not sidecars:
        print("check_data: no sidecar found", file=sys.stderr)
        return 1
    checker, failed = Checker(), 0
    for side in sidecars:
        try:
            problems = checker.check(side)
        except DataError as exc:
            problems = [str(exc)]
        failed += bool(problems)
        for p in problems:
            print(f"check_data: {_rel(side)}: {p}", file=sys.stderr)
    print(f"check_data: {len(sidecars) - failed} of {len(sidecars)} sidecars pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
