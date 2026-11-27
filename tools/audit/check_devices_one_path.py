#!/usr/bin/env python3
"""The device master is reached through hartlib.devices only, so a change to its files changes one module.

    python3 tools/audit/check_devices_one_path.py      # tools/check.sh runs it (job devices-one-path)

No tracked .py outside tools/hartlib names either file (devices_generated.csv, devices_field.csv; the one-file
devices.csv before the split): no string constant (a name, a path, a glob, one part of an f-string) holds "devices"
and ".csv" with no whitespace in it, and none calls open/read_text/write_text/read_bytes/write_bytes on an
expression that mentions a master constant (devices.MASTER, DEVICE_MAP, DEVICES, .master, master_path). Code asks
hartlib.devices (MASTER_FILE, FIELD_FILE, master_path, field_path, load, index, field_index, write_generated,
write_field). Tests count as code here: a test that needs a devices file builds its name from hartlib.devices.

Limits. A message sentence that names devices.csv holds whitespace, so it is allowed; a path built from pieces
("dev" + "ices.csv") or read from a config is not seen; a master path passed through a variable with another name
into open() is not seen; Python 2 files (Jython) get a text scan for the quoted name only. ALLOWED lists the one
file that may name them (tools/hartlib/tests/test_devices_one_path.py pins its copies to hartlib); CHECKS the checks
whose own tables or patterns name the files (tools/audit/check_data_readers.py holds every layout data file the same
way, and lists panel_stamps' two names too).
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.files import GitError, tracked_files  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
# What it reads, as git globs: every tracked .py (less SKIP, ALLOWED and CHECKS). The step's quiet_inputs in
# tools/pipeline/checks.toml are these (tools/audit/tests/test_manifest_scans.py).
SCAN_GLOBS = ("**/*.py",)
SKIP = ("tools/hartlib/", "reference/", "archive/", "external/")     # hartlib and its tests; vendor and retired code
ALLOWED = ("tools/schematic/panel_stamps.py",)      # cannot import hartlib in its shell test; pinned by a hartlib test
CHECKS = ("tools/audit/check_data_readers.py",      # the data-readers check: its table names the files it allows
          "tools/audit/check_devices_one_path.py")  # this check: its patterns name them
NAME = re.compile(r"^\S*devices\S*\.csv\S*$")
PY2_NAME = re.compile(r"""["'](\S*/)?devices\.csv["']""")
LINE_END = re.compile(r"\r\n|\r|\n")           # the line ends ast counts lines by
IO = {"open", "read_text", "write_text", "read_bytes", "write_bytes"}
# an expression that holds the master's path
MASTER_REF = re.compile(r"\bdevices\.MASTER\b|\bdevice_master\.MASTER\b|\bDEVICE_MAP\b|\bDEVICES\b|\.master\b|"
                        r"\bmaster_path\(")
HINT = "reach the master through hartlib.devices (load, index, field_index, write_field)"


def in_scope(rel: str) -> bool:
    return rel.endswith(".py") and not rel.startswith(SKIP) and rel not in ALLOWED + CHECKS


def offences(rel: str, src: str) -> list[str]:
    """Each place in one file's source that names a devices file or opens the master itself, as "path:line: why"."""
    if "devices" not in src and not MASTER_REF.search(src):     # neither can match: skip the parse
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:                  # Jython 2 (jmri/jython): a text scan for the quoted name
        return [f"{rel}:{n}: names the master's file" for n, line in enumerate(src.splitlines(), 1)
                if PY2_NAME.search(line)]
    lines = LINE_END.split(src)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and NAME.match(node.value):
            bad.append(f"{rel}:{node.lineno}: names {node.value!r}; use hartlib.devices.MASTER_FILE, FIELD_FILE, "
                       "master_path() or field_path()")
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            # the call's whole lines first (cheap, and they hold the call), then the call's own text
            if (name in IO and MASTER_REF.search("\n".join(lines[node.lineno - 1:node.end_lineno or node.lineno]))
                    and MASTER_REF.search(ast.get_source_segment(src, node) or "")):
                bad.append(f"{rel}:{node.lineno}: reads or writes the master directly; use hartlib.devices")
    return bad


def problems(root: Path = ROOT) -> list[str]:
    """Every offence in the tracked .py files under `root` that the check covers. GitError when git cannot list them."""
    files = tracked_files(root, *(f":(glob){g}" for g in SCAN_GLOBS))
    return [m for rel in files if in_scope(rel) and (root / rel).is_file()
            for m in offences(rel, (root / rel).read_text(encoding="utf-8"))]


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.parse_args(argv)
    try:
        bad = problems(root)
    except GitError as err:
        print(f"FAIL {err}")
        return 1
    for line in bad:
        print(f"FAIL {line}")
    if bad:
        print(f"FAIL {len(bad)} place(s): {HINT}")
        return 1
    print("OK: no script outside hartlib names a devices file or opens the master itself")
    return 0


if __name__ == "__main__":
    sys.exit(main())
