"""check_py_sizes.py: a file over its line limit has a row that caps it with 10 percent headroom; --update never
lowers a row and only an --accept by name raises one. Run against scratch git repos, plus the real repo."""
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


class ScratchRepo(unittest.TestCase):
    """A scratch git repo with its own SIZES, and the check run in it."""

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

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = CPS.main(list(argv))
        return rc, out.getvalue(), err.getvalue()


class Scratch(ScratchRepo):
    # the check

    def test_unchanged_sizes_pass(self) -> None:
        self.put("a/big.py", 900)
        self.put("a/small.py", 100)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        self.assertEqual(self.run_main()[0], 0)

    def test_growth_within_the_headroom_passes(self) -> None:
        self.assertEqual(CPS.HEADROOM, 0.10)
        self.assertEqual([CPS.allowed_size(n) for n in (900, 801, 509)], [990, 881, 559])
        for n in (901, 950, 990):
            with self.subTest(lines=n):
                self.put("a/big.py", n)
                self.sizes.write_text("path,lines\na/big.py,900\n")
                rc, out, _ = self.run_main()
                self.assertEqual(rc, 0, out)
                self.assertNotIn("listed file(s)", out)

    def test_growth_past_the_headroom_fails_and_names_the_allowed_size_and_the_accept(self) -> None:
        self.put("a/big.py", 991)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("a/big.py: grew from 900 to 991 lines, past the 990 its row allows (10 percent headroom)", out)
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

    def test_a_shrunk_file_keeps_its_row_through_update_and_may_grow_back(self) -> None:
        self.put("a/big.py", 850)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 0)
        self.assertNotIn("listed file(s)", out)
        rc, out, _ = self.run_main("--update")
        self.assertEqual(rc, 0)
        self.assertIn("already current", out)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,900\n")
        self.put("a/big.py", 990)               # grows back past its old size, within the headroom of its row
        self.assertEqual(self.run_main()[0], 0)

    def test_a_file_under_the_limit_or_gone_passes_with_a_note(self) -> None:
        self.put("a/was_big.py", 700)
        self.sizes.write_text("path,lines\na/gone.py,900\na/was_big.py,900\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 0)
        self.assertIn("2 listed file(s) gone or at or under their limit; `--update` drops their rows", out)
        self.assertEqual(self.run_main("--update")[0], 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\n")

    def test_update_drops_the_row_of_a_file_at_its_limit_and_keeps_the_others(self) -> None:
        self.put("a/edge.py", 800)
        self.put("a/big.py", 820)
        self.sizes.write_text("path,lines\na/big.py,900\na/edge.py,900\na/gone.py,900\n")
        rc, out, _ = self.run_main("--update")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,900\n")
        self.assertNotIn("listed file(s)", out)

    def test_a_shrink_beside_a_growth_still_fails(self) -> None:
        self.put("a/big.py", 850)
        self.put("a/other.py", 1000)
        self.sizes.write_text("path,lines\na/big.py,900\na/other.py,900\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("a/other.py: grew from 900 to 1000", out)

    def test_a_new_untracked_file_is_measured_but_an_ignored_one_is_not(self) -> None:
        self.put("a/new.py", 900, track=False)
        self.sizes.write_text("path,lines\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("a/new.py: 900 lines", out)
        (self.root / ".gitignore").write_text("a/new.py\n")
        self.assertEqual(self.run_main()[0], 0)

    def test_lines_are_counted_as_wc_l_does(self) -> None:
        p = self.root / "t.py"
        p.write_text("a\fb\n\u2028c\n")       # form feed and a line separator are not new lines
        self.assertEqual(CPS.count_lines(p), 2)
        p.write_text("a\nb")                   # a last line with no newline counts
        self.assertEqual(CPS.count_lines(p), 2)
        p.write_text("")
        self.assertEqual(CPS.count_lines(p), 0)

    def test_excluded_files_are_not_measured(self) -> None:
        for rel in ("archive/old.py", "external/x/y.py",
                    "jmri/layouts/hart/parked/p.py", "a/notes.txt"):
            self.put(rel, 900)
        self.sizes.write_text("path,lines\n")
        self.assertEqual(self.run_main()[0], 0)

    # --update and --accept

    def test_update_never_raises_a_size_or_adds_a_file_without_accept(self) -> None:
        self.put("a/big.py", 1000)
        self.put("a/new.py", 820)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        rc, out, _ = self.run_main("--update")
        self.assertEqual(rc, 1)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,900\n")
        self.assertIn("grew from 900 to 1000", out)
        self.assertIn("a/new.py: 820 lines, over 800 with no row", out)
        self.put("a/big.py", 950)               # within the headroom: passes, and --update still keeps the row
        self.put("a/new.py", 700)
        self.assertEqual(self.run_main("--update")[0], 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,900\n")

    def test_accept_by_name_takes_growth_and_a_new_file(self) -> None:
        self.put("a/big.py", 950)
        self.put("a/new.py", 820)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        rc, _, _ = self.run_main("--update", "--accept", "a/big.py", "--accept", "a/new.py")
        self.assertEqual(rc, 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,950\na/new.py,820\n")
        self.put("a/big.py", 1100)              # past the headroom of the old row, accepted by name
        self.assertEqual(self.run_main()[0], 1)
        self.assertEqual(self.run_main("--update", "--accept", "a/big.py")[0], 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\na/big.py,1100\na/new.py,820\n")

    def test_accept_refuses_a_path_that_does_not_need_it(self) -> None:
        self.put("a/big.py", 900)
        self.put("a/small.py", 100)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        for path, why in (("a/typo.py", "no .py, .js, .sh file"), ("a/small.py", "not over 800"),
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
                 ("path,lines\narchive/old.py,900\n", "not a .py, .js, .sh file this check covers"),
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


class OtherKinds(ScratchRepo):
    """.js files at 800 lines and .sh files at 500, under the same ratchet as .py; other suffixes are not measured."""

    def test_each_kind_has_its_limit_and_its_globs(self) -> None:
        self.assertEqual(CPS.LIMITS, {".py": 800, ".js": 800, ".sh": 500})
        self.assertEqual(CPS.SCAN_GLOBS, ("**/*.py", "**/*.js", "**/*.sh"))

    def test_a_file_crossing_its_limit_without_a_row_fails(self) -> None:
        self.put("www/a.js", 801)
        self.put("tools/a.sh", 501)
        self.put("tools/edge.sh", 500)
        self.put("www/edge.js", 800)
        self.sizes.write_text("path,lines\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("www/a.js: 801 lines, over 800 with no row", out)
        self.assertIn("tools/a.sh: 501 lines, over 500 with no row", out)
        self.assertNotIn("edge", out.split("problem(s)", 1)[1])

    def test_growth_past_the_headroom_fails_and_a_shrink_keeps_its_row(self) -> None:
        self.put("tools/a.sh", 562)
        self.put("www/a.js", 900)
        self.sizes.write_text("path,lines\ntools/a.sh,510\nwww/a.js,950\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("tools/a.sh: grew from 510 to 562 lines, past the 561 its row allows", out)
        self.assertNotIn("listed file(s)", out)
        self.assertEqual(self.run_main("--update")[0], 1)       # the growth stays a problem without --accept
        self.assertEqual(self.sizes.read_text(), "path,lines\ntools/a.sh,510\nwww/a.js,950\n")
        self.assertEqual(self.run_main("--update", "--accept", "tools/a.sh")[0], 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\ntools/a.sh,562\nwww/a.js,950\n")

    def test_a_file_at_or_under_its_limit_or_gone_is_a_note(self) -> None:
        self.put("tools/a.sh", 500)
        self.sizes.write_text("path,lines\ntools/a.sh,600\nwww/gone.js,900\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 0)
        self.assertIn("2 listed file(s) gone or at or under their limit; `--update` drops their rows", out)
        self.assertEqual(self.run_main("--update")[0], 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\n")

    def test_accept_takes_a_new_file_by_name_and_refuses_one_under_its_limit(self) -> None:
        self.put("tools/a.sh", 501)
        self.put("tools/b.sh", 499)
        self.sizes.write_text("path,lines\n")
        rc, _, err = self.run_main("--update", "--accept", "tools/b.sh")
        self.assertEqual(rc, 2)
        self.assertIn("--accept tools/b.sh: it is 499 lines, not over 500", err)
        self.assertEqual(self.run_main("--update", "--accept", "tools/a.sh")[0], 0)
        self.assertEqual(self.sizes.read_text(), "path,lines\ntools/a.sh,501\n")

    def test_a_row_must_be_over_its_own_kinds_limit(self) -> None:
        self.put("tools/a.sh", 600)
        for text, rc, why in (("path,lines\ntools/a.sh,500\n", 2, "at 500 lines is not over 500"),
                              ("path,lines\ntools/a.sh,600\n", 0, ""),
                              ("path,lines\nnotes.txt,900\n", 2, "not a .py, .js, .sh file this check covers")):
            with self.subTest(text=text):
                self.sizes.write_text(text)
                got, _, err = self.run_main()
                self.assertEqual(got, rc, err)
                self.assertIn(why, err)

    def test_excluded_folders_and_other_suffixes_are_not_measured(self) -> None:
        for rel in ("archive/old.js", "external/x/y.sh", "reference/r.js", "tools/cats/src-repo/c.sh",
                    "jmri/layouts/hart/parked/p.js", "www/a.mjs", "www/a.json", "tools/a.bash",
                    "www/node_modules/pkg/index.js", "node_modules/x/y.sh"):
            self.put(rel, 2000)
        self.sizes.write_text("path,lines\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("WARNING", out)


class Warnings(ScratchRepo):
    """A file at 90 percent of its limit or more, with no row, is named in a WARNING line; the check still passes."""

    def test_the_warning_lines_are_at_90_percent(self) -> None:
        self.assertEqual({s: CPS.warn_at(limit) for s, limit in CPS.LIMITS.items()},
                         {".py": 720, ".js": 720, ".sh": 450})

    def test_a_file_near_its_limit_warns_and_passes(self) -> None:
        for rel, n in (("a/near.py", 720), ("a/under.py", 719), ("www/near.js", 800), ("tools/near.sh", 450),
                       ("tools/under.sh", 449)):
            self.put(rel, n)
        self.sizes.write_text("path,lines\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 0, out)
        warned = [line for line in out.splitlines() if "WARNING" in line]
        self.assertEqual(warned, [
            "check_py_sizes: WARNING: a/near.py: 720 lines, at 90 percent of its 800-line limit; over 800 it fails "
            "without a row: split it first",
            "check_py_sizes: WARNING: tools/near.sh: 450 lines, at 90 percent of its 500-line limit; over 500 it "
            "fails without a row: split it first",
            "check_py_sizes: WARNING: www/near.js: 800 lines, at 100 percent of its 800-line limit; over 800 it "
            "fails without a row: split it first"])
        self.assertTrue(out.endswith("grew past its cap (0 listed)\n"), out)

    def test_a_file_over_its_limit_is_a_problem_not_a_warning(self) -> None:
        self.put("a/big.py", 900)
        self.sizes.write_text("path,lines\na/big.py,900\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 0)
        self.assertNotIn("WARNING", out)
        self.put("a/big.py", 991)
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertNotIn("WARNING", out)

    def test_update_and_a_failing_check_still_warn(self) -> None:
        self.put("a/near.py", 750)
        self.put("tools/a.sh", 600)
        self.sizes.write_text("path,lines\n")
        rc, out, _ = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("WARNING: a/near.py: 750 lines, at 93 percent", out)
        rc, out, _ = self.run_main("--update", "--accept", "tools/a.sh")
        self.assertEqual(rc, 0)
        self.assertIn("WARNING: a/near.py", out)


class RealRepo(unittest.TestCase):
    def test_the_committed_list_is_current(self) -> None:
        self.assertEqual(CPS.problems(CPS.measure(), CPS.read_sizes()), [])


if __name__ == "__main__":
    unittest.main()
