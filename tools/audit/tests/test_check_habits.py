"""check_habits counts each habit per file, and the ratchet refuses a rise and notes a fall for --update."""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("check_habits", ROOT / "tools/audit/check_habits.py")
assert spec is not None and spec.loader is not None
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)


def counts(text: str, rel: str = "tools/x.py", imported: bool = True) -> dict[str, int]:
    return H.count_file(rel, text, imported)


class HabitCounts(unittest.TestCase):
    def test_lost_cause_only_when_the_error_text_is_kept(self) -> None:
        text = ("try:\n    f()\nexcept OSError as err:\n    raise ValueError(str(err)) from None\n"
                "try:\n    f()\nexcept OSError as e:\n    raise ValueError(f'bad {e.strerror}') from None\n"
                "try:\n    f()\nexcept KeyError:\n    raise ValueError('no key') from None\n"
                "try:\n    f()\nexcept OSError as err:\n    raise ValueError(str(err)) from err\n")
        self.assertEqual(counts(text), {"lost-cause": 2})

    def test_dated_note_in_comments_and_docstrings_only(self) -> None:
        note = "(owner, " + "2026-11-25)"       # split, so this file holds no note of its own
        text = f'"""Kept {note}."""\nX = 1  # {note.title()}\nY = "{note}" + ""\n'
        self.assertEqual(counts(text)["dated-note"], 3)     # a plain string is a string token too
        self.assertEqual(counts("X = 1  # owner said so\n"), {})

    def test_a_raise_in_nested_handlers_counts_once(self) -> None:
        text = ("try:\n    f()\nexcept OSError as err:\n    try:\n        g()\n    except KeyError as key:\n"
                "        raise ValueError(f'{err} {key}') from None\n")
        self.assertEqual(counts(text), {"lost-cause": 1})

    def test_dated_note_without_brackets_or_with_more_text(self) -> None:
        year = "2026"                          # split, so this file holds no note of its own
        text = f"# kept, owner {year}-12-01\n# (owner, {year}-12-01: the reason)\n# owner said so in {year}\n"
        self.assertEqual(counts(text), {"dated-note": 2})

    def test_exit_outside_main_counts_only_in_imported_files(self) -> None:
        text = ("import sys\nif not sys.argv:\n    sys.exit(1)\n"
                "def helper():\n    raise SystemExit('no')\n"
                "def main():\n    sys.exit(2)\n"
                "if __name__ == '__main__':\n    raise SystemExit(main())\n")
        self.assertEqual(counts(text), {"import-exit": 2})
        self.assertEqual(counts(text, imported=False), {})

    def test_hartlib_bootstrap_line_is_not_an_exit(self) -> None:
        text = ("import sys\nsys.path[:0] = [p for p in ps][:1] or sys.exit('no tools/hartlib/src')\n"
                "x = [] or sys.exit('real')\n")
        self.assertEqual(counts(text), {"import-exit": 1})

    def test_exec_and_globals_update(self) -> None:
        self.assertEqual(counts("exec(open('a.py').read())\nglobals().update(vars(m))\nd.update(x)\n"),
                         {"exec-parts": 2})

    def test_python2_file_uses_line_patterns(self) -> None:
        text = "print 'x'\nexec code in ns\n# (owner, " + "2026-01-01)\n"
        self.assertEqual(counts(text), {"dated-note": 1, "exec-parts": 1})

    def test_imported_stems_from_imports_and_file_names(self) -> None:
        stems = H.imported_stems({"a.py": "import os, json as j\nfrom pkg.mod import x\nload('tools/b.py')\n"})
        self.assertTrue({"os", "json", "mod", "b"} <= stems)


class SourceAsserts(unittest.TestCase):
    def test_calibration_file(self) -> None:
        # the flagged calibration file (cats/scripts/tests/test_signal_coordinator.py) became behaviour tests on main;
        # the synthetic cases below cover the flagged side
        clean = ROOT / "tools/audit/tests/test_stamp_gate.py"
        self.assertEqual(H.source_asserts(ast.parse(clean.read_text(encoding="utf-8"))), 0)

    def test_mostly_text_checks_flags_each_one(self) -> None:
        text = ("SRC = ROOT / 'a.py'\n"
                "def test_a(self):\n    src = SRC.read_text()\n    self.assertIn('def f', src)\n"
                "    self.assertNotIn('x', src)\n    assert 'y' in src\n    self.assertEqual(f(), 1)\n")
        self.assertEqual(counts(text, rel="tests/test_a.py"), {"source-asserts": 3})

    def test_mostly_behaviour_is_not_flagged(self) -> None:
        text = ("def test_a(self):\n    src = open('a.py').read()\n    self.assertIn('def f', src)\n"
                "    self.assertEqual(f(), 1)\n    self.assertEqual(g(), 2)\n")
        self.assertEqual(counts(text, rel="tests/test_a.py"), {})


class Ratchet(unittest.TestCase):
    def run_main(self, now: dict, base: dict | None, *argv: str) -> tuple[int, str, Path]:
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        baseline = tmp / "baseline.json"
        if base is not None:
            baseline.write_text(json.dumps(base))
        out = io.StringIO()
        with mock.patch.object(H, "scan", return_value=now), contextlib.redirect_stdout(out):
            code = H.main(list(argv), root=tmp, baseline=baseline)
        return code, out.getvalue(), baseline

    def test_same_counts_pass(self) -> None:
        code, out, _ = self.run_main({"a.py": {"lost-cause": 1}}, {"a.py": {"lost-cause": 1}})
        self.assertEqual((code, out.startswith("OK")), (0, True))

    def test_rise_fails_and_update_refuses(self) -> None:
        for argv in ((), ("--update",)):
            code, out, baseline = self.run_main({"a.py": {"lost-cause": 2}, "b.py": {"exec-parts": 1}},
                                                {"a.py": {"lost-cause": 1}}, *argv)
            self.assertEqual(code, 1)
            self.assertIn("a.py: lost-cause 1 -> 2", out)
            self.assertIn("b.py: exec-parts 0 -> 1", out)
            self.assertEqual(json.loads(baseline.read_text()), {"a.py": {"lost-cause": 1}})

    def test_fall_passes_with_a_note_until_update_writes_it(self) -> None:
        code, out, baseline = self.run_main({"b.py": {"exec-parts": 1}},
                                            {"a.py": {"lost-cause": 1, "dated-note": 2}, "b.py": {"exec-parts": 2}})
        self.assertEqual(code, 0)
        self.assertIn("2 file(s) below the baseline; `--update` locks them in", out)
        self.assertNotIn("FAIL", out)
        self.assertEqual(json.loads(baseline.read_text()),
                         {"a.py": {"lost-cause": 1, "dated-note": 2}, "b.py": {"exec-parts": 2}})
        code, _, baseline = self.run_main({}, {"a.py": {"lost-cause": 1}}, "--update")
        self.assertEqual((code, json.loads(baseline.read_text())), (0, {}))

    def test_fall_beside_a_rise_still_fails(self) -> None:
        code, out, _ = self.run_main({"a.py": {"lost-cause": 2}}, {"a.py": {"lost-cause": 1}, "b.py": {"exec-parts": 1}})
        self.assertEqual(code, 1)
        self.assertIn("FAIL higher than the baseline: a.py: lost-cause 1 -> 2", out)

    def test_missing_baseline_fails_and_update_writes_the_first(self) -> None:
        self.assertEqual(self.run_main({"a.py": {"exec-parts": 1}}, None)[0], 1)
        code, _, baseline = self.run_main({"a.py": {"exec-parts": 1}}, None, "--update")
        self.assertEqual((code, json.loads(baseline.read_text())), (0, {"a.py": {"exec-parts": 1}}))

    def test_bad_baseline_is_one_fail_line(self) -> None:
        code, out, _ = self.run_main({}, {"a.py": {"no-such-habit": 1}})
        self.assertEqual(code, 1)
        self.assertRegex(out, r"^FAIL .*a\.py: each count must be a habit")

    def test_git_failure_is_a_habits_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(H.HabitsError) as caught:
            H.scan(Path(tmp))
        self.assertIsInstance(caught.exception.__cause__, H.GitError)

    def test_committed_baseline_has_no_rise(self) -> None:
        self.assertEqual(H.compare(H.scan(), H.read_baseline())[0], [])


if __name__ == "__main__":
    unittest.main()
