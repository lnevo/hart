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
        for argv in (["--chek"], ["--check"], ["docs"]):
            status, out, err = self.run_main(argv)
            self.assertEqual(status, 2, argv)
            self.assertIn(repr(argv[0]), err)
            self.assertEqual(out, "")

    def test_help_prints_the_usage(self) -> None:
        for argv in (["--help"], ["-h"]):
            status, out, err = self.run_main(argv)
            self.assertEqual(status, 0, argv)
            self.assertIn("build_docs_index.py", out)
            self.assertEqual(err, "")

    def test_no_argument_writes_the_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "docs").mkdir()
            with mock.patch.object(INDEX, "ROOT", Path(tmp)), \
                    mock.patch.object(INDEX, "tracked", return_value=["docs/ctc/A B.md"]), \
                    mock.patch.object(INDEX, "last_changed", return_value={"docs/ctc/A B.md": "2026-11-01"}), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(INDEX.main([]), 0)
            self.assertIn("| 2026-11-01 | [A B.md](ctc/A%20B.md) | md |", (Path(tmp) / "docs/INDEX.md").read_text())


if __name__ == "__main__":
    unittest.main()
