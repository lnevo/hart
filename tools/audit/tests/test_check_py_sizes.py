"""check_py_sizes.py: a Python file over 800 lines may not grow; the committed list is a ratchet that only an
--accept by name can raise. Run against scratch git repos, plus the real repo."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("check_py_sizes", ROOT / "tools/audit/check_py_sizes.py")
CPS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CPS)


def lines(n: int) -> str:
    return "".join(f"x{i} = {i}\n" for i in range(n))


class Scratch(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.sizes = self.root / "tools/audit/py_sizes.csv"
        self.sizes.parent.mkdir(parents=True)
        for patch in (mock.patch.object(CPS, "ROOT", self.root), mock.patch.object(CPS, "SIZES", self.sizes)):
            patch.start()
            self.addCleanup(patch.stop)

    def put(self, rel: str, n: int, track: bool = True) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(lines(n))
        if track:
            subprocess.run(["git", "add", rel], cwd=self.root, check=True)

    def listing(self, **rows: int) -> None:
        self.sizes.write_text("path,lines\n" + "".join(f"{k.replace('__', '/')},{v}\n" for k, v in rows.items()))

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = CPS.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    # the check

    def test_unchanged_sizes_pass(self) -> None:
        self.put("a/big.py", 900)
        self.put("a/small.py", 100)
        self.listing(a__big_py=900)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        self.assertEqual(self.run_main()[0], 0)

    def test_growth_fails_and_names_the_accept(self) -> None:
        self.put("a/big.py", 901)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("a/big.py: grew from 900 to 901 lines", out)
        self.assertIn("--update --accept a/big.py", out)

    def test_a_file_crossing_the_limit_without_a_row_fails(self) -> None:
        self.put("a/new.py", 801)
        self.sizes.write_text("path,lines\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("a/new.py: 801 lines, over 800 with no row", out)

    def test_exactly_the_limit_needs_no_row(self) -> None:
        self.put("a/edge.py", 800)
        self.sizes.write_text("path,lines\n")
        self.assertEqual(self.run_main()[0], 0)

    def test_shrinking_fails_until_the_list_is_tightened(self) -> None:
        self.put("a/big.py", 850)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("shrank from 900 to 850", out)
        self.assertEqual(self.run_main("--update")[0], 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,850\n")
        self.assertEqual(self.run_main()[0], 0)

    def test_a_file_under_the_limit_or_gone_must_lose_its_row(self) -> None:
        self.put("a/was_big.py", 700)
        self.sizes.write_text("path,lines\na/gone.py,900\na/was_big.py,900\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("a/gone.py: listed at 900 lines but gone", out)
        self.assertIn("a/was_big.py: now 700 lines, at or under 800", out)
        self.assertEqual(self.run_main("--update")[0], 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\n")

    def test_untracked_and_excluded_files_are_not_measured(self) -> None:
        self.put("a/scratch.py", 900, track=False)
        for rel in ("archive/old.py", "external/x/y.py", "docs/jmri/speedmatching/STRR_v1.py",
                    "jmri/layouts/hart/parked/p.py", "a/notes.txt"):
            self.put(rel, 900)
        self.sizes.write_text("path,lines\n")
        self.assertEqual(self.run_main()[0], 0)

    # --update and --accept

    def test_update_never_raises_a_size_or_adds_a_file_without_accept(self) -> None:
        self.put("a/big.py", 950)
        self.put("a/new.py", 820)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        rc, out, _ = self.run_main("--update")
        self.assertEqual(rc, 1)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,900\n")
        self.assertIn("grew from 900 to 950", out)

    def test_accept_by_name_takes_growth_and_a_new_file(self) -> None:
        self.put("a/big.py", 950)
        self.put("a/new.py", 820)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        rc, _, _ = self.run_main("--update", "--accept", "a/big.py", "--accept", "a/new.py")
        self.assertEqual(rc, 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,950\na/new.py,820\n")

    def test_accept_refuses_a_path_that_does_not_need_it(self) -> None:
        self.put("a/big.py", 900)
        self.put("a/small.py", 100)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        for path, why in (("a/typo.py", "no tracked .py file"), ("a/small.py", "not over 800"),
                          ("a/big.py", "did not grow")):
            rc, _, err = self.run_main("--update", "--accept", path)
            self.assertEqual(rc, 2, path)
            self.assertIn(why, err)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,900\n")

    def test_accept_needs_update(self) -> None:
        self.sizes.write_text("path,lines\n")
        rc, _, err = self.run_main("--accept", "a/big.py")
        self.assertEqual(rc, 2)
        self.assertIn("--accept needs --update", err)

    # the list itself

    def test_a_bad_list_stops_with_a_message(self) -> None:
        self.put("a/big.py", 900)
        cases = (("", "first row must be path,lines"),
                 ("path,lines\na/big.py\n", "want path,lines"),
                 ("path,lines\na/big.py,many\n", "want path,lines"),
                 ("path,lines\na/big.py,900\na/big.py,900\n", "listed twice"),
                 ("path,lines\narchive/old.py,900\n", "not a .py file this check covers"),
                 ("path,lines\na/big.py,800\n", "not over 800"))
        for text, why in cases:
            self.sizes.write_text(text)
            rc, out, err = self.run_main()
            self.assertEqual(rc, 2, text)
            self.assertIn(why, err)
            self.assertEqual(out, "")

    def test_a_missing_list_stops(self) -> None:
        rc, _, err = self.run_main()
        self.assertEqual(rc, 2)
        self.assertIn("is missing", err)

    def test_git_that_fails_is_a_message_not_a_traceback(self) -> None:
        self.sizes.write_text("path,lines\n")
        with mock.patch.object(CPS.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 128, "", "fatal: not a git repository")):
            rc, _, err = self.run_main()
        self.assertEqual(rc, 2)
        self.assertIn("git ls-files failed: fatal: not a git repository", err)


class RealRepo(unittest.TestCase):
    def test_the_committed_list_is_current(self) -> None:
        self.assertEqual(CPS.problems(CPS.measure(), CPS.read_sizes()), [])


if __name__ == "__main__":
    unittest.main()
