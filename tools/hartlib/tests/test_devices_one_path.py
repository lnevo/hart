"""The device master is reached through hartlib.devices only (T6a step 0), so splitting it in two changes one module.

No tracked .py outside tools/hartlib names the file (a string "devices.csv" or ".../devices.csv") or reads or writes
it with open/read_text/write_text on a path it got from a master constant; it asks hartlib.devices (MASTER_FILE,
MASTER, master_path, load, index, parse, write_master). The one exception is jmri/scripts/check_hart_phase02.py,
Jython inside JMRI that cannot import hartlib: a test below pins its path to devices.MASTER.
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

EXCEPTION = "jmri/scripts/check_hart_phase02.py"
HOME = "tools/hartlib/"                  # hartlib itself, and its tests
NAME = re.compile(r"^(\S*/)?devices\.csv$")
IO = {"open", "read_text", "write_text", "read_bytes", "write_bytes"}
# an expression that holds the master's path
MASTER_REF = re.compile(r"\bdevices\.MASTER\b|\bdevice_master\.MASTER\b|\bDEVICE_MAP\b|\bDEVICES\b|\.master\b|"
                        r"\bmaster_path\(")


def tracked_py() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines()
            if not p.startswith((HOME, "reference/", "archive/", "external/")) and p != EXCEPTION
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
            bad.append(f"{path}:{node.lineno}: names {node.value!r}; use hartlib.devices.MASTER_FILE or master_path()")
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in IO and MASTER_REF.search(ast.get_source_segment(src, node) or ""):
                bad.append(f"{path}:{node.lineno}: reads or writes the master directly; use hartlib.devices")
    return bad


class OnePathTest(unittest.TestCase):
    def test_nothing_outside_hartlib_names_or_opens_the_master(self):
        bad = [m for p in tracked_py() for m in offences(p)]
        self.assertEqual(bad, [], "reach the master through hartlib.devices (load, index, parse, write_master)")

    def test_the_jython_exception_uses_hartlibs_path(self):
        spec = importlib.util.spec_from_file_location("check_hart_phase02", REPO / EXCEPTION)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(Path(mod.DEVICES).resolve(), devices.MASTER.resolve())
        self.assertEqual(devices.MASTER.name, devices.MASTER_FILE)

    def test_master_path_under_a_folder(self):
        self.assertEqual(devices.master_path(Path("/x")), Path("/x") / devices.MASTER_FILE)
        self.assertEqual(devices.master_path(), devices.MASTER)


if __name__ == "__main__":
    unittest.main()
