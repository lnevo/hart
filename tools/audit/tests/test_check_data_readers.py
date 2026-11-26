"""tools/audit/check_data_readers.py: a script outside hartlib that names a layout data file fails unless it is
allowed with a reason, Jython is held to naming none, and an allowed pair no longer named fails (naming-layers
step 6)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("check_data_readers", ROOT / "tools/audit/check_data_readers.py")
CDR = importlib.util.module_from_spec(spec)
sys.modules["check_data_readers"] = CDR
spec.loader.exec_module(CDR)

NAMES = {"switches.csv", "masts.csv", "wiring.csv", "block_lengths.csv"}


class Scan(unittest.TestCase):
    def found(self, src: str) -> tuple[dict[str, int], bool]:
        return CDR.named_in(src, NAMES)

    def test_a_path_a_name_or_an_fstring_part_is_named(self):
        self.assertEqual(self.found('X = DATA / "switches.csv"\n'), ({"switches.csv": 1}, False))
        self.assertEqual(self.found('X = "jmri/layouts/hart/data/schematic/masts.csv"\n')[0], {"masts.csv": 1})
        self.assertEqual(self.found('X = f"{SCH}/masts.csv"\n')[0], {"masts.csv": 1})

    def test_a_sentence_another_file_or_a_longer_name_is_not(self):
        self.assertEqual(self.found('print("switches.csv has no row")\n')[0], {})
        self.assertEqual(self.found('X = "output/tables.xml"\nY = "old_switches.csv"\n')[0], {})

    def test_jython_is_told_apart(self):
        self.assertTrue(self.found('import jmri\nX = "wiring.csv"\n')[1])
        self.assertTrue(self.found('def f():\n    from java.io import File\n')[1])
        got, jython = self.found('print "x"\nX = "wiring.csv"\n')              # only Python 2 parses it
        self.assertEqual((got, jython), ({"wiring.csv": 2}, True))
        self.assertFalse(self.found('import json\n')[1])
        for src in ('import jarray\n', 'from org.python.core import PyList\n', 'import apps\n',
                    'import os, javax.swing\n', 'if x:\n    import jmri.jmrit\n'):
            with self.subTest(src=src):
                self.assertTrue(self.found(src)[1])

    def test_an_import_inside_a_string_is_not_jython(self):
        """The imports are the AST's Import nodes, not a text match."""
        self.assertFalse(self.found('HELP = """\nimport jmri\n"""\n')[1])
        self.assertFalse(self.found('import javascript_tools\n')[1])

    def test_python_2_marks_and_a_broken_script(self):
        for src in ('except Exception, e:\n', 'x = latch.await(30)\n', 'raise ValueError, "no"\n',
                    'exec "x = 1"\n'):
            with self.subTest(src=src):
                self.assertTrue(self.found(src)[1])
        with self.assertRaisesRegex(CDR.Unparseable, "line 1: .*no mark of Python 2"):
            self.found('def f(:\n    pass\n')

    def test_tests_and_hartlib_are_not_scanned(self):
        scanned = CDR.scripts()
        self.assertIn("tools/wiring/write_inventory.py", scanned)
        self.assertFalse([p for p in scanned if p.startswith(CDR.SKIP) or CDR.is_test(p)])
        self.assertTrue(CDR.is_test("tools/audit/tests/helpers.py"))
        self.assertTrue(CDR.is_test("jmri/scripts/test_x.py"))
        self.assertFalse(CDR.is_test("tools/wiring/write_inventory.py"))

    def test_the_data_files_are_every_tracked_file_there(self):
        names = CDR.data_names()
        self.assertTrue({"switches.csv", "block_overrides.csv", "main_lines.csv", "mast_cells.csv",
                         "wiring.csv", "plan_overrides.json"} <= names)
        self.assertNotIn("README.md", names)


class Problems(unittest.TestCase):
    def run_with(self, scripts: dict[str, tuple[dict[str, int], bool]], allowed=None, jython_allowed=None):
        with mock.patch.object(CDR, "scripts", return_value=list(scripts)), \
                mock.patch.object(CDR, "named", side_effect=lambda path, names: scripts[path]):
            return CDR.problems(allowed or {}, jython_allowed or {})

    def test_a_new_reader_fails_naming_its_line(self):
        bad = self.run_with({"tools/new.py": ({"switches.csv": 7}, False)})
        self.assertEqual(len(bad), 1)
        self.assertIn("tools/new.py:7: names switches.csv", bad[0])
        self.assertIn("read it through hartlib", bad[0])

    def test_an_allowed_pair_passes_and_a_stale_one_fails(self):
        allowed = {"tools/old.py": {"switches.csv": CDR.WRITES}}
        self.assertEqual(self.run_with({"tools/old.py": ({"switches.csv": 3}, False)}, allowed), [])
        bad = self.run_with({"tools/old.py": ({}, False)}, allowed)
        self.assertEqual(len(bad), 1)
        self.assertIn("ALLOWED lists tools/old.py naming switches.csv, which it no longer does", bad[0])

    def test_jython_needs_its_own_list(self):
        allowed = {"jmri/x.py": {"wiring.csv": CDR.WRITES}}       # the CPython list does not let Jython through
        bad = self.run_with({"jmri/x.py": ({"wiring.csv": 2}, True)}, allowed)
        self.assertTrue(any("Jython inside JMRI cannot import hartlib" in b for b in bad))
        self.assertEqual(self.run_with({"jmri/x.py": ({"wiring.csv": 2}, True)}, None,
                                       {"jmri/x.py": {"wiring.csv": "why"}}), [])

    def test_a_jython_script_in_the_cpython_table_gets_no_stale_line(self):
        bad = self.run_with({"jmri/x.py": ({"wiring.csv": 2}, True)}, {"jmri/x.py": {"wiring.csv": CDR.WRITES}})
        self.assertEqual(len(bad), 1)
        self.assertIn("Jython inside JMRI", bad[0])
        bad = self.run_with({"tools/y.py": ({"wiring.csv": 2}, False)}, None, {"tools/y.py": {"wiring.csv": "w"}})
        self.assertEqual(len(bad), 1)
        self.assertIn("read it through hartlib", bad[0])
        bad = self.run_with({"jmri/x.py": ({}, True)}, None, {"jmri/x.py": {"wiring.csv": "w"}})
        self.assertIn("JYTHON_ALLOWED lists jmri/x.py naming wiring.csv, which it no longer does", bad[0])

    def test_an_unparseable_script_fails_on_its_own(self):
        def named(path, names):
            raise CDR.Unparseable("line 3: invalid syntax; not Python 3, and no mark of Python 2 (Jython)")
        with mock.patch.object(CDR, "scripts", return_value=["tools/broken.py"]), \
                mock.patch.object(CDR, "named", side_effect=named):
            bad = CDR.problems({}, {})
        self.assertEqual(bad, ["tools/broken.py: cannot be read for data file names (line 3: invalid syntax; not "
                               "Python 3, and no mark of Python 2 (Jython))"])

    def test_every_allowed_pair_has_a_reason(self):
        for path, files in (*CDR.ALLOWED.items(), *CDR.JYTHON_ALLOWED.items()):
            for name, why in files.items():
                with self.subTest(path=path, name=name):
                    self.assertTrue(why.strip())

    def test_the_moved_readers_are_not_allowed(self):
        """naming-layers step 6 moved these onto hartlib; none may name a data file again."""
        for path in ("jmri/layouts/hart/scripts/layout_facts.py", "tools/wiring/write_inventory.py",
                     "jmri/scripts/check_hart_phase02.py", "tools/schematic/mast_rule.py"):
            with self.subTest(path):
                self.assertNotIn(path, CDR.ALLOWED)
        self.assertEqual(set(CDR.ALLOWED["jmri/layouts/hart/scripts/speedmatch/analyze.py"]), {"block_lengths.csv"})
        self.assertEqual(set(CDR.ALLOWED["tools/schematic/build_main_route.py"]), {"main.json", "staging.json"})


class Repo(unittest.TestCase):
    def test_the_repo_passes(self):
        self.assertEqual(CDR.problems(), [])


if __name__ == "__main__":
    unittest.main()
