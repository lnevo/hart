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
matched to the generated row with the same key, and its non-empty cells win; a field row with no match is added.
A refs path names a master the same way, so `devices.csv:user_name` reads the merged device pair.

Sidecars are found by walking the repo, leaving out SKIP and folders whose names start with a dot, so a new sidecar
is checked with no list to edit.

    python3 tools/ops/check_data.py              check every sidecar (exit 1 on a problem)
    python3 tools/ops/check_data.py PATH ...     check only these sidecars
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUFFIX = ".columns.csv"
SKIP = ("archive", "external", "reference", "node_modules", "tools/cats/src-repo")   # from the repo root
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
    """Every <name>.columns.csv under root, sorted, outside SKIP and dot folders."""
    out = []
    for here, dirs, files in os.walk(root):
        rel = Path(here).relative_to(root).as_posix()
        dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                         and (f"{rel}/{d}" if rel != "." else d) not in SKIP)
        out += [Path(here) / f for f in files if f.endswith(SUFFIX)]
    return sorted(out)


def _read_csv(path: Path) -> list[list[str]]:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.reader(fh))
    except (OSError, UnicodeDecodeError) as exc:
        raise DataError(f"{_rel(path)}: cannot read it ({exc})") from None


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
    for line, r in enumerate(out, 2):
        at = f"{where} line {line} ({r['column']})"
        if r["type"] and r["type"] not in TYPES:
            raise DataError(f"{at}: type {r['type']!r} is not one of {', '.join(TYPES)}")
        if (r["type"] == "enum") != bool(r["values"]):
            raise DataError(f"{at}: an enum column has values, and only an enum column")
        for rule in ("required", "key"):
            if r[rule]:
                parse_condition(r[rule], names, at)
        for ref in filter(None, r["refs"].split(LIST)):
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


def load_master(files: list[Path], spec: list[dict[str, str]]) -> list[dict[str, str]]:
    """The master's rows; a pair merged (module docstring). DataError when a header is not the sidecar's columns."""
    names = [r["column"] for r in spec]
    tables = []
    for f in files:
        rows = _read_csv(f)
        if not rows or rows[0] != names:
            raise DataError(f"{_rel(f)}: the header is not the sidecar's columns in order")
        bad = [i for i, r in enumerate(rows[1:], 2) if len(r) != len(names)]
        if bad:
            raise DataError(f"{_rel(f)} line {bad[0]}: {len(rows[bad[0] - 1])} fields, expected {len(names)}")
        tables.append([dict(zip(names, r)) for r in rows[1:]])
    merged = tables[0]
    if len(tables) == 2:
        groups = _key_groups(spec)
        if not groups:
            raise DataError(f"{_rel(files[1])}: a pair master needs a key in its sidecar")
        by_key = {k: r for r in merged if (k := _row_key(r, groups, names)) is not None}
        for frow in tables[1]:
            grow = by_key.get(_row_key(frow, groups, names))
            if grow is None:
                merged.append(frow)
            else:
                grow.update({c: v for c, v in frow.items() if v})
    return merged


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
        self._masters: dict[Path, tuple[list[str], list[dict[str, str]]]] = {}

    def master(self, sidecar_or_csv: Path) -> tuple[list[str], list[dict[str, str]]]:
        """(file names for messages, merged rows) of the master a sidecar or a refs path names."""
        p = sidecar_or_csv.resolve()
        if p not in self._masters:
            base = p.name[:-len(SUFFIX)] if p.name.endswith(SUFFIX) else p.name[:-len(".csv")]
            side = p.parent / f"{base}{SUFFIX}"
            files = master_files(p)
            if side.is_file():
                rows = load_master(files, read_sidecar(side))
            else:
                rows = [dict(zip(t[0], r)) for t in [_read_csv(files[0])] if t for r in t[1:]]
            self._masters[p] = ([f.name for f in files], rows)
        return self._masters[p]

    def ref_values(self, ref: str, where: str) -> set[str]:
        path, _, col = ref.rpartition(":")
        try:
            _, rows = self.master(ROOT / path)
        except DataError as exc:
            raise DataError(f"{where}: refs {ref}: {exc}") from None
        if rows and col not in rows[0]:
            raise DataError(f"{where}: refs {ref}: no column {col}")
        return {r[col] for r in rows}

    def check(self, sidecar: Path) -> list[str]:
        """The problems of one sidecar and its master, each a line; DataError when they cannot be read."""
        spec = read_sidecar(sidecar)
        names = [r["column"] for r in spec]
        files, rows = self.master(sidecar)
        label = " + ".join(files)
        problems: list[str] = []

        def report(what: str, found: list[str]) -> None:
            if found:
                more = f" (and {len(found) - MAX_SHOWN} more)" if len(found) > MAX_SHOWN else ""
                problems.append(f"{label}: {what}: {'; '.join(found[:MAX_SHOWN])}{more}")

        def at(row: dict[str, str]) -> str:
            keys = [row[c] for cols in _key_groups(spec).values() for c in cols if row[c]]
            return "/".join(keys) or f"row {rows.index(row) + 2}"

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
