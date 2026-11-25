"""The device master is reached through hartlib.devices only (T6a step 0), so splitting it in two changes one module.

No tracked .py outside tools/hartlib names either file (devices_generated.csv, devices_field.csv; the one-file
devices.csv before the split of 2026-11-21): no string constant (a name, a path, a glob, one part of an
f-string) holds "devices" and ".csv" with no whitespace in it, and none calls open/read_text/write_text/read_bytes/
write_bytes on an expression that mentions a master constant (devices.MASTER, DEVICE_MAP, DEVICES, .master,
master_path). Code asks hartlib.devices (MASTER_FILE, FIELD_FILE, master_path, field_path, load, index, field_index,
write_generated, write_field).

Limits that remain. A message sentence that names devices.csv holds whitespace, so it is allowed; a path built from
pieces ("dev" + "ices.csv") or read from a config is not seen; a master path passed through a variable with another
name into open() is not seen; Python 2 files (Jython) get a text scan for the quoted name only. ALLOWED lists the one
file that may name them, with a test that pins its copies to hartlib; CHECKS the check that holds every layout data
file the same way (tools/audit/check_data_readers.py, which lists panel_stamps' two names too).
"""
from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools/hartlib/src"))
from hartlib import devices  # noqa: E402

ALLOWED = ("tools/schematic/panel_stamps.py",)      # cannot import hartlib in its shell test; pinned below
HOME = "tools/hartlib/"                  # hartlib itself, and its tests
CHECKS = ("tools/audit/check_data_readers.py",)    # the data-readers check: its table names the files it allows
NAME = re.compile(r"^\S*devices\S*\.csv\S*$")
IO = {"open", "read_text", "write_text", "read_bytes", "write_bytes"}
# an expression that holds the master's path
MASTER_REF = re.compile(r"\bdevices\.MASTER\b|\bdevice_master\.MASTER\b|\bDEVICE_MAP\b|\bDEVICES\b|\.master\b|"
                        r"\bmaster_path\(")


def tracked_py() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines()
            if not p.startswith((HOME, "reference/", "archive/", "external/")) and p not in ALLOWED + CHECKS
            and (REPO / p).is_file()]


def offences(path: str) -> list[str]:
    src = (REPO / path).read_text(encoding="utf-8")
    bad = []
    try:
        tree = ast.parse(src)
    except SyntaxError:                  # Jython 2 (jmri/jython): a text scan for the quoted name
        return [f"{path}:{n}: names the master's file" for n, line in enumerate(src.splitlines(), 1)
                if re.search(r"""["'](\S*/)?devices\.csv["']""", line)]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and NAME.match(node.value):
            bad.append(f"{path}:{node.lineno}: names {node.value!r}; use hartlib.devices.MASTER_FILE, FIELD_FILE, "
                       "master_path() or field_path()")
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in IO and MASTER_REF.search(ast.get_source_segment(src, node) or ""):
                bad.append(f"{path}:{node.lineno}: reads or writes the master directly; use hartlib.devices")
    return bad


class OnePathTest(unittest.TestCase):
    def test_nothing_outside_hartlib_names_or_opens_the_master(self):
        bad = [m for p in tracked_py() for m in offences(p)]
        self.assertEqual(bad, [], "reach the master through hartlib.devices (load, index, field_index, write_field)")

    def test_the_allowed_copy_is_hartlibs_name(self):
        spec = importlib.util.spec_from_file_location("panel_stamps", REPO / ALLOWED[0])
        mod = importlib.util.module_from_spec(spec)
        sys.modules["panel_stamps"] = mod         # dataclasses look their module up here
        spec.loader.exec_module(mod)
        self.assertEqual(mod.DEVICES_FILE, devices.MASTER_FILE)
        self.assertEqual(mod.DEVICES_FIELD_FILE, devices.FIELD_FILE)
        self.assertEqual(devices.MASTER_FILE, devices.GENERATED_FILE)

    def test_master_path_under_a_folder(self):
        self.assertEqual(devices.master_path(Path("/x")), Path("/x") / devices.MASTER_FILE)
        self.assertEqual(devices.master_path(), devices.MASTER)
        self.assertEqual(devices.field_path(Path("/x")), Path("/x") / devices.FIELD_FILE)
        self.assertEqual(devices.Files.under(Path("/x")).field, Path("/x") / devices.FIELD_FILE)


if __name__ == "__main__":
    unittest.main()
