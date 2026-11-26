"""check_stamps.py's parts (stamps_cache.py, stamps_audit.py): an edit to one reruns what an edit to check_stamps.py
reruns, and they load beside it, by path, from any folder, or refuse a part from another folder."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_stamps as cs  # noqa: E402

REPO = cs.ROOT


class PartsTest(unittest.TestCase):
    """check_stamps.py and its parts (FILES: stamps_cache.py, stamps_audit.py): an edit to a part reruns the jobs an
    edit to check_stamps.py reruns, and the parts load beside it, by path, from any folder, or not at all."""

    def probe(self, code: str, cwd: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-c", code, str(REPO / "tools/audit/check_stamps.py")], cwd=cwd,
                              capture_output=True, text=True, timeout=60)

    def test_a_part_is_an_input_wherever_check_stamps_py_is(self) -> None:
        self.assertEqual(cs.FILES[0], "tools/audit/check_stamps.py")
        self.assertEqual(set(cs.FILES[1:]), {"tools/audit/stamps_cache.py", "tools/audit/stamps_audit.py"})
        jobs = (*cs.BY_KIND, *cs.EXTRA, *cs.pm.job_keys(), "unit-guards test_x")
        for pats in (cs.ALWAYS, (*cs.ALWAYS, *cs.ps.CODE), *(cs.declared(job) for job in jobs)):
            whole = any(cs.ps._glob_match(cs.FILES[0], p) for p in pats)
            for part in cs.FILES[1:]:
                with self.subTest(part=part, patterns=pats[:3]):
                    self.assertEqual(any(cs.ps._glob_match(part, p) for p in pats), whole)

    def test_it_loads_by_path_from_another_folder_and_leaves_sys_path_as_it_found_it(self) -> None:
        code = ("import importlib.util, sys\n"
                "spec = importlib.util.spec_from_file_location('cs_by_path', sys.argv[1])\n"
                "cs = importlib.util.module_from_spec(spec)\n"
                "sys.modules[spec.name] = cs\n"
                "spec.loader.exec_module(cs)\n"
                "assert str(cs.HERE) not in sys.path, sys.path\n"
                "print(cs.declared('unit-mimic')[-1], cs.stamps_audit.stamps_cache is cs.stamps_cache)\n")
        with tempfile.TemporaryDirectory() as cwd:
            done = self.probe(code, cwd)
            self.assertEqual((done.returncode, done.stdout), (0, "tools/check.sh True\n"), done.stderr)
            cli = subprocess.run([sys.executable, str(REPO / "tools/audit/check_stamps.py"), "declared", "unit-mimic"],
                                 cwd=cwd, capture_output=True, text=True, timeout=60)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual(cli.stdout.splitlines()[-1], "tools/check.sh")

    def test_a_part_from_another_folder_is_refused(self) -> None:
        for part, says in (("stamps_cache", "stamps_audit.py: stamps_cache must be the file beside it"),
                           ("stamps_audit", "check_stamps.py: its parts must be the files beside it")):
            code = ("import importlib.util, sys, types\n"
                    f"stray = types.ModuleType({part!r})\n"
                    f"stray.__file__ = '/elsewhere/tools/audit/{part}.py'\n"
                    f"sys.modules[{part!r}] = stray\n"
                    "spec = importlib.util.spec_from_file_location('cs_by_path', sys.argv[1])\n"
                    "cs = importlib.util.module_from_spec(spec)\n"
                    "try:\n"
                    "    spec.loader.exec_module(cs)\n"
                    "except ImportError as exc:\n"
                    "    print(exc)\n"
                    "else:\n"
                    "    print('loaded')\n")
            with self.subTest(part=part), tempfile.TemporaryDirectory() as cwd:
                done = self.probe(code, cwd)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertIn(says, done.stdout)
                self.assertIn(f"/elsewhere/tools/audit/{part}.py", done.stdout)


if __name__ == "__main__":
    unittest.main()
