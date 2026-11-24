"""tools/audit/test_classes.py: the classes check.sh runs as separate jobs for a BY_CLASS file."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/audit/test_classes.py"
CHECK = ROOT / "tools/check.sh"


def _ids(suite) -> list[str]:
    out = []
    for item in suite:
        out += _ids(item) if isinstance(item, unittest.TestSuite) else [item.id()]
    return out


def classes(source: str, *args: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "test_sample.py"
        path.write_text(source, encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPT), str(path), *args], capture_output=True, text=True,
                              timeout=30)


class TestClasses(unittest.TestCase):
    def test_only_classes_that_hold_tests_in_file_order(self) -> None:
        done = classes("import unittest\n"
                       "class Base(unittest.TestCase):\n    def setUp(self): pass\n"
                       "class B(Base):\n    def test_one(self): pass\n"
                       "class A(unittest.TestCase):\n    def test_two(self): pass\n    def test_three(self): pass\n")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["test_sample.A", "test_sample.B"], sorted(done.stdout.split()))

    def test_a_file_that_cannot_load_or_holds_no_tests_fails(self) -> None:
        self.assertEqual(1, classes("import nowhere_such_module\n").returncode)
        self.assertEqual(1, classes("import unittest\nclass A(unittest.TestCase):\n    pass\n").returncode)

    def test_methods_of_one_class_are_printed_as_test_ids(self) -> None:
        done = classes("import unittest\n"
                       "class A(unittest.TestCase):\n    def test_two(self): pass\n    def test_three(self): pass\n"
                       "class B(unittest.TestCase):\n    def test_one(self): pass\n", "--methods", "test_sample.A")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["test_sample.A.test_three", "test_sample.A.test_two"], sorted(done.stdout.split()))
        self.assertEqual(1, classes("import unittest\nclass A(unittest.TestCase):\n    def test_x(self): pass\n",
                                    "--methods", "test_sample.Nope").returncode)

    def test_check_sh_selects_each_class_by_its_printed_name(self) -> None:
        self.assertIn('-p "$f" -k "$c."', CHECK.read_text(encoding="utf-8"))

    def test_every_by_class_file_exists_and_splits(self) -> None:
        text = CHECK.read_text(encoding="utf-8")
        # every BY_CLASS= and BY_CLASS+= line, each file found in one of the folders check.sh splits
        names = [n for x in text.splitlines() if x.startswith(("BY_CLASS=", "BY_CLASS+="))
                 for n in x.split('"')[1].split()]
        self.assertIn("test_deploy_gates.py", names)
        folders = [ROOT / d for d in ("tools/audit/tests", "tools/hosts/tests", "tools/schematic/tests")]
        for name in names:
            found = [d / name for d in folders if (d / name).is_file()]
            self.assertEqual(1, len(found), f"{name}: in one of {[str(d) for d in folders]}")
            path = found[0]
            done = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, timeout=60)
            self.assertEqual(0, done.returncode, done.stderr)
            printed = done.stdout.split()
            self.assertGreater(len(printed), 1, name)
            # check.sh's -k "$c." selects each class: together they hold every test of the file, each once
            everything = _ids(unittest.defaultTestLoader.discover(str(path.parent), pattern=name))
            picked = []
            for c in printed:
                loader = unittest.TestLoader()
                loader.testNamePatterns = [f"*{c}.*"]          # what unittest -k makes of a pattern with no *
                picked += _ids(loader.discover(str(path.parent), pattern=name))
            self.assertEqual(sorted(everything), sorted(picked))


if __name__ == "__main__":
    unittest.main()
