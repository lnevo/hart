"""docs/INDEX.md links must survive file names with odd spaces (macOS screenshots use U+202F)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_docs_index", ROOT / "tools/ops/build_docs_index.py")
INDEX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INDEX)


class DocLinkTest(unittest.TestCase):
    def test_plain_path(self) -> None:
        self.assertEqual(INDEX.doc_link("docs/ctc/SIGNAL_FACING.md"), "ctc/SIGNAL_FACING.md")

    def test_ascii_space(self) -> None:
        self.assertEqual(INDEX.doc_link("docs/ops/STRR Speed Match.pdf"), "ops/STRR%20Speed%20Match.pdf")

    def test_narrow_no_break_space(self) -> None:
        link = INDEX.doc_link("docs/ctc/history/Screenshot 2026-08-19 at 5.44.55\u202fPM.png")
        self.assertEqual(link, "ctc/history/Screenshot%202026-08-19%20at%205.44.55%E2%80%AFPM.png")
        self.assertFalse(any(ch.isspace() for ch in link))


class Arguments(unittest.TestCase):
    """The script has no options: --help and any other argument stop before git is read, and write no index."""

    def run_main(self, argv):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "docs").mkdir()
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(INDEX, "ROOT", Path(tmp)), mock.patch.object(INDEX, "tracked") as tracked, \
                    mock.patch.object(INDEX, "last_changed") as last_changed, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = INDEX.main(argv)
            tracked.assert_not_called()
            last_changed.assert_not_called()
            self.assertEqual(list((Path(tmp) / "docs").iterdir()), [])
        return status, out.getvalue(), err.getvalue()

    def test_unknown_argument_is_refused(self) -> None:
        for argv in (["--chek"], ["--check", "docs"], ["docs"]):
            status, out, err = self.run_main(argv)
            self.assertEqual(status, 2, argv)
            self.assertIn(repr(argv[-1] if argv[0] == "--check" else argv[0]), err)
            self.assertEqual(out, "")

    def test_help_prints_the_usage(self) -> None:
        for argv in (["--help"], ["-h"], ["--check", "--help"], ["-h", "docs"]):
            status, out, err = self.run_main(argv)
            self.assertEqual(status, 0, argv)
            self.assertIn("build_docs_index.py", out)
            self.assertEqual(err, "")

    def test_help_without_a_docstring(self) -> None:
        """python -OO strips the docstring; --help still prints the usage line, not 'None'."""
        with mock.patch.object(INDEX, "__doc__", None):
            status, out, err = self.run_main(["--help"])
        self.assertEqual((status, out, err), (0, "build_docs_index.py [--check]\n", ""))

    def test_no_argument_writes_the_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "docs").mkdir()
            with mock.patch.object(INDEX, "ROOT", Path(tmp)), \
                    mock.patch.object(INDEX, "tracked", return_value=["docs/ctc/A B.md"]), \
                    mock.patch.object(INDEX, "last_changed", return_value={"docs/ctc/A B.md": "2026-11-01"}), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(INDEX.main([]), 0)
            self.assertIn("| 2026-11-01 | [A B.md](ctc/A%20B.md) | md |", (Path(tmp) / "docs/INDEX.md").read_text())


class Check(unittest.TestCase):
    """--check compares the documents the index lists with the tracked ones, never their dates."""

    PATHS = ["docs/ctc/A B.md", "docs/wiring/x.csv"]

    def run_check(self, index_text, paths=None):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "docs").mkdir()
            if index_text is not None:
                (Path(tmp) / "docs/INDEX.md").write_text(index_text)
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(INDEX, "ROOT", Path(tmp)), \
                    mock.patch.object(INDEX, "tracked", return_value=paths or self.PATHS), \
                    mock.patch.object(INDEX, "last_changed") as last_changed, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = INDEX.main(["--check"])
            last_changed.assert_not_called()          # CI's shallow clone has no history to date from
            wrote = sorted(f.name for f in (Path(tmp) / "docs").iterdir())
            self.assertEqual(wrote, ["INDEX.md"] if index_text is not None else [])     # --check writes nothing
        return status, out.getvalue(), err.getvalue()

    def test_current_index_passes_whatever_its_dates(self) -> None:
        text = INDEX.render(self.PATHS, {"docs/ctc/A B.md": "2026-11-01", "docs/wiring/x.csv": "2026-10-01"})
        status, out, err = self.run_check(text)
        self.assertEqual((status, err), (0, ""))
        self.assertIn("lists all 2 documents", out)

    def test_new_document_fails(self) -> None:
        status, _, err = self.run_check(INDEX.render(self.PATHS[:1], {}))
        self.assertEqual(status, 1)
        self.assertIn("out of date", err)
        self.assertIn("missing: wiring: [x.csv](wiring/x.csv) | csv", err)

    def test_removed_document_fails(self) -> None:
        status, _, err = self.run_check(INDEX.render(self.PATHS, {}), self.PATHS[:1])
        self.assertEqual(status, 1)
        self.assertIn("not tracked: wiring: [x.csv](wiring/x.csv) | csv", err)

    def test_moved_to_another_area_fails(self) -> None:
        status, _, err = self.run_check(INDEX.render(["docs/ctc/A B.md", "docs/ops/x.csv"], {}))
        self.assertEqual(status, 1)

    def test_missing_index_fails(self) -> None:
        status, _, err = self.run_check(None)
        self.assertEqual(status, 1)
        self.assertIn("out of date", err)


if __name__ == "__main__":
    unittest.main()
