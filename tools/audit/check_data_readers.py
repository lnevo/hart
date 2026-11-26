#!/usr/bin/env python3
"""No script outside hartlib reads a layout data file itself (ADR-033): every read of
jmri/layouts/hart/data/ (its schematic/ folder included) goes through tools/hartlib, so a rename or a new key changes
one reader.

    python3 tools/audit/check_data_readers.py          # tools/check.sh runs it (job data-readers)
    python3 tools/audit/check_data_readers.py --list   # every script and data file it allows, with the reason

A script names a data file when a string in it (a name, a path, a glob, one part of an f-string, with no whitespace)
is the file's name or ends in "/<name>": every file git tracks under the data folder counts. The scripts are the
tracked .py files outside tools/hartlib/ (hartlib, its tests and master_edit.py), reference/, archive/ and
external/ (vendor and retired code), and this check (its table names the files); test files (a tests/ folder, test_*.py) are left out, as they copy data files
into fixtures. A script that names a data file fails unless ALLOWED lists that script and file, with the reason it
may; an ALLOWED pair no longer named fails too, so the list stays honest.

Jython that runs inside JMRI (a script that imports jmri, apps, java, javax, org or jarray, or that only Python 2
parses; a script Python 3 cannot parse that shows no mark of Python 2 fails as unreadable) cannot import
hartlib and reads only generated outputs (jmri/layouts/hart/output/, the JMRI profile): a Jython script that names a
data file fails unless JYTHON_ALLOWED lists it by name (one today, loco_roster_import.py).

Limits. A message sentence that names a file holds whitespace, so it is allowed; a path built from pieces ("block_" +
"lengths.csv") or read from a config is not seen; a script that names a file only to pass it to a hartlib reader is
still listed, as the check cannot see where the path goes (reason THROUGH). tools/hartlib/tests/test_devices_one_path.py
also holds the device master's two files to hartlib.devices.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = "jmri/layouts/hart/data/"
SKIP = ("tools/hartlib/", "reference/", "archive/", "external/")
# What it reads, as git globs: every tracked .py (less SKIP, the tests and itself). The step's quiet_inputs in
# tools/pipeline/checks.toml are these (tools/audit/tests/test_manifest_scans.py).
SCAN_GLOBS = ("**/*.py",)
SELF = "tools/audit/check_data_readers.py"    # its ALLOWED table names the files it allows
TEXT_ONLY = {"README.md"}        # a doc beside the data, named by many docs tools as any README

# reasons a script may name a data file
WRITES = "writes it (its own output)"
THROUGH = "names the path only to hand it to a hartlib reader"
PLAN = "a schematic plan input (inputs/*.json) the panel build and the plugin read"
STAMP = "hashes the file's bytes for a build stamp; reads no row"
TEXT = "a text search for names (check_name_copies), not a read of the rows"
PI = ("runs on the Pi with copies of the block length files and no hartlib (tools/hosts/deploy/stage.sh); reads "
      "them by block id, and its measured file beside the plan file")
REF = ("the speed-match publisher's 2026-11-08 reference speeds: it runs on the Pi with a copy of the file and no "
       "hartlib (tools/hosts/deploy/stage.sh), and the Mac dashboard reads the same file")

# script -> {data file name: reason}. Only what the scan finds; a pair no longer found fails.
MESSAGE = "names the path in a message only (the rows come from another module)"
TAG = "a device master written_by tag that happens to be the file's name, not a path"
ALLOWED: dict[str, dict[str, str]] = {
    "jmri/layouts/hart/scripts/speedmatch/analyze.py": {"block_lengths.csv": PI},
    "jmri/layouts/hart/scripts/speedmatch/dashboard/dashsources.py": {"speed_by_step_2026-11-08.csv": REF},
    "jmri/layouts/hart/scripts/speedmatch/dashboard/publish_live.py": {"speed_by_step_2026-11-08.csv": REF},
    "ops/hart-ops/card_pipeline/locos.py": {"new_locos.json": WRITES + "; the card pipeline adds to the import list"},
    "tools/audit/check_name_copies.py": {
        n: TEXT for n in ("block_numbering.csv", "discovered_sml.xml", "mast_cells.csv", "masts.csv",
                          "retired_virtual_masts.csv", "signals.json")},
    "tools/schematic/approval.py": {
        n: WRITES + "; --check compares the drawing against it"
        for n in ("approved_cats_abs.sha256", "approved_cats_ctc.sha256", "approved_le_panel.sha256")},
    "tools/schematic/build_cats_panel.py": {"stations.csv": THROUGH},
    "tools/schematic/build_hands.py": {"main.json": PLAN},
    "tools/schematic/build_main_route.py": {"main.json": PLAN, "staging.json": PLAN},
    "tools/schematic/build_signals.py": {"main.json": PLAN, "staging.json": PLAN},
    "tools/schematic/build_staging_sets.py": {"stations.csv": THROUGH, "switches.csv": THROUGH},
    "tools/schematic/device_map_inputs.py": {"stations.csv": THROUGH},
    "tools/schematic/device_map_masts.py": {"interlockings.csv": THROUGH},
    "tools/schematic/le_common.py": {"stations.csv": THROUGH},
    "tools/schematic/panel_items.py": {"panel_items.json": TAG},
    # the steps' data files are named in tools/pipeline/panels.toml since ADR-037 stage 5; only these stay here
    "tools/schematic/panel_stamps.py": {n: STAMP for n in ("devices_field.csv", "devices_generated.csv")},
    "tools/schematic/plan_lengths.py": {"main.json": PLAN, "parts.json": PLAN, "staging.json": PLAN},
    "tools/schematic/publish_draft.py": {"main.json": PLAN, "staging.json": PLAN},
    "tools/schematic/split_store.py": {"tables_template.xml": WRITES + " from a PanelPro Store"},
    "tools/schematic/staging_device_map.py": {"stations.csv": THROUGH},
    "www/scripts/build_layout_index.py": {"stations.csv": THROUGH, "switches.csv": THROUGH},
    "www/scripts/tables_page.py": {"switches.csv": THROUGH},
}

# Jython inside JMRI that reads a data file: it cannot import hartlib. Every other Jython script names none (it reads
# only generated outputs), and the check holds it to that.
JYTHON_ALLOWED: dict[str, dict[str, str]] = {
    "jmri/layouts/hart/scripts/loco_roster_import.py": {
        "new_locos.json": ("the list of new locomotives: tools/ops/loco_roster_import.sh embeds it for JMRI on the "
                           "Pi; the path is the CPython plan run's default")},
}


def tracked(pattern: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", pattern], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if (REPO / p).is_file()]


def data_names() -> set[str]:
    """The names of every file git tracks under the data folder."""
    return {Path(p).name for p in tracked(DATA)} - TEXT_ONLY


def is_test(path: str) -> bool:
    return "/tests/" in f"/{path}" or Path(path).name.startswith("test_")


def scripts() -> list[str]:
    return [p for g in SCAN_GLOBS for p in tracked(f":(glob){g}") if not p.startswith(SKIP) and not is_test(p) and p != SELF]


# the top-level packages only Jython inside JMRI imports: JMRI's own (jmri, apps), Java's (java, javax, org) and
# Jython's array module for Java arrays (jarray)
JYTHON_ROOTS = {"jmri", "apps", "java", "javax", "org", "jarray"}
# what only Python 2 parses: a print or exec statement, "except E, e", "raise E, msg", a ur"" string, and a Python 3
# keyword used as a name (Java's CountDownLatch.await)
PY2 = re.compile(r"""^\s*print\s+[^\s(=]|^\s*exec\s+["'\w]|^\s*except\s+[\w.]+\s*,\s*\w+\s*:|^\s*raise\s+[\w.]+\s*,"""
                 r"""|\bur["']|\.(?:await|async)\b""", re.M)


class Unparseable(ValueError):
    """A script neither Python 3 nor (by its Python 2 marks) Jython parses; the message says where."""


def imported_roots(tree: ast.AST) -> set[str]:
    """The top-level packages a parsed script imports (Import and ImportFrom nodes, relative imports left out)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module.split(".")[0])
    return out


def is_jython(src: str, tree: ast.AST | None) -> bool:
    """A Python 2 script (`tree` None) is Jython; a Python 3 one is when it imports a JYTHON_ROOTS package."""
    return tree is None or bool(imported_roots(tree) & JYTHON_ROOTS)


def named(path: str, names: set[str]) -> tuple[dict[str, int], bool]:
    """named_in of the script at `path` (from the repo root)."""
    return named_in((REPO / path).read_text(encoding="utf-8", errors="replace"), names)


def named_in(src: str, names: set[str]) -> tuple[dict[str, int], bool]:
    """({data file name of `names`: first line naming it}, is Jython) of a script's text. Unparseable when Python 3
    cannot parse it and it shows no mark of Python 2 (PY2)."""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        if not PY2.search(src):
            raise Unparseable(f"line {exc.lineno}: {exc.msg}; not Python 3, and no mark of Python 2 (Jython)") from exc
        tree = None
    found: dict[str, int] = {}
    if tree is None:                       # Python 2 (Jython): a text scan for a quoted name
        for n, line in enumerate(src.splitlines(), 1):
            for m in re.finditer(r"""["'](?:\S*/)?([^"'/\s]+)["']""", line):
                if m.group(1) in names:
                    found.setdefault(m.group(1), n)
        return found, True
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value \
                and not any(c.isspace() for c in node.value):
            name = node.value.rsplit("/", 1)[-1]
            if name in names:
                first = found.get(name)
                found[name] = node.lineno if first is None else min(first, node.lineno)
    return found, is_jython(src, tree)


def problems(allowed: dict[str, dict[str, str]] = ALLOWED,
             jython_allowed: dict[str, dict[str, str]] = JYTHON_ALLOWED) -> list[str]:
    names = data_names()
    out = []
    seen: dict[str, set[str]] = {}
    kind: dict[str, bool] = {}          # script -> is Jython
    for path in scripts():
        try:
            found, jython = named(path, names)
        except Unparseable as exc:
            out.append(f"{path}: cannot be read for data file names ({exc})")
            continue
        kind[path] = jython
        for name, line in sorted(found.items()):
            if jython and name not in jython_allowed.get(path, {}):
                out.append(f"{path}:{line}: names {name}, a layout data file; Jython inside JMRI cannot import "
                           "hartlib and reads only generated outputs (jmri/layouts/hart/output/)")
            elif not jython and name not in allowed.get(path, {}):
                out.append(f"{path}:{line}: names {name}, a layout data file; read it through hartlib "
                           "(hartlib.railroad, hand_lists, devices, wiring, layer_files, track_names, level_masts)")
            else:
                seen.setdefault(path, set()).add(name)
    for table, jython in ((allowed, False), (jython_allowed, True)):
        for path, files in table.items():
            if kind.get(path, jython) != jython:
                continue                # a script of the other kind: its names already failed above
            for name in files:
                if name not in seen.get(path, set()):
                    label = "JYTHON_ALLOWED" if jython else "ALLOWED"
                    out.append(f"{label} lists {path} naming {name}, which it no longer does (or the file is gone): "
                               "take the row out of tools/audit/check_data_readers.py")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", action="store_true", help="print every allowed script and data file with its reason")
    args = ap.parse_args(argv)
    if args.list:
        for path, files in sorted({**ALLOWED, **JYTHON_ALLOWED}.items()):
            for name, why in sorted(files.items()):
                print(f"{path}: {name}: {why}")
        return 0
    bad = problems()
    for line in bad:
        print(f"FAIL {line}")
    if bad:
        return 1
    pairs = sum(len(f) for f in (*ALLOWED.values(), *JYTHON_ALLOWED.values()))
    print(f"OK: no script outside hartlib names a layout data file but the {pairs} allowed pair(s) in "
          f"{len(ALLOWED) + len(JYTHON_ALLOWED)} script(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
