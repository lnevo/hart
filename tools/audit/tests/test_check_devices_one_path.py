"""check_devices_one_path fails a tracked .py outside hartlib that names a devices file or opens the master itself,
and passes the same tree once the file asks hartlib.devices; it runs on a scratch git checkout, not the repo."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import devices  # noqa: E402

spec = importlib.util.spec_from_file_location("check_devices_one_path", ROOT / "tools/audit/check_devices_one_path.py")
assert spec is not None and spec.loader is not None
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)

GOOD = "from hartlib import devices\nROWS = devices.load()\nPATH = devices.master_path()\n"
# the names come from hartlib.devices, so this file names no devices file itself
BAD_NAME = f'PATH = "jmri/layouts/hart/data/{devices.MASTER_FILE}"\n'
BAD_OPEN = "from hartlib import devices\nTEXT = open(devices.MASTER).read()\n"
JYTHON = f'print "hello"\nPATH = "{devices.MASTER_FILE.replace("_generated", "")}"\n'


class OnePathCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.repo)], check=False))
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)

    def tree(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", *files], check=True)

    def run_check(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = C.main([], root=self.repo)
        return code, out.getvalue()

    def test_a_good_file_passes_and_a_bad_one_fails_with_where_and_what_to_use(self) -> None:
        self.tree({"tools/good.py": GOOD, "tools/bad.py": BAD_NAME})
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn(f"FAIL tools/bad.py:1: names 'jmri/layouts/hart/data/{devices.MASTER_FILE}'; use "
                      "hartlib.devices.MASTER_FILE, FIELD_FILE, master_path() or field_path()", out)
        self.assertIn("FAIL 1 place(s): reach the master through hartlib.devices", out)
        self.assertNotIn("good.py", out)

    def test_opening_the_master_fails(self) -> None:
        self.tree({"tools/bad.py": BAD_OPEN})
        self.assertEqual(C.problems(self.repo),
                         ["tools/bad.py:2: reads or writes the master directly; use hartlib.devices"])

    def test_a_python_2_file_gets_the_text_scan(self) -> None:
        self.tree({"jmri/jython/old.py": JYTHON})
        self.assertEqual(C.problems(self.repo), ["jmri/jython/old.py:2: names the master's file"])

    def test_hartlib_the_allowed_file_and_untracked_files_are_left_out(self) -> None:
        self.tree({"tools/hartlib/src/hartlib/x.py": BAD_NAME, C.ALLOWED[0]: BAD_NAME, "tools/good.py": GOOD})
        (self.repo / "tools/untracked.py").write_text(BAD_NAME, encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual((code, out.splitlines()[0][:3]), (0, "OK:"))


if __name__ == "__main__":
    unittest.main()
