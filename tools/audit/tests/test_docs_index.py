"""docs/INDEX.md: link encoding, the summary rule, grouping, asset filtering and --check / --strict."""
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
        link = INDEX.doc_link("docs/ctc/history/Screenshot 2026-08-19 at 5.44.55 PM.png")
        self.assertEqual(link, "ctc/history/Screenshot%202026-08-19%20at%205.44.55%E2%80%AFPM.png")
        self.assertFalse(any(ch.isspace() for ch in link))


class Summary(unittest.TestCase):
    """summarize(): the first plain prose line after the first '# ' heading, or a summary: line."""

    def test_plain_line_after_heading(self) -> None:
        self.assertEqual(INDEX.summarize("# T\n\nHello there.\nmore"), "Hello there")

    def test_each_skipped_prefix(self) -> None:
        for skipped in ("| a | b |", "- item", "* item", "> quote", "`code`", "<div>", "## sub", "![img](x.png)", "1. step", "12. step"):
            self.assertEqual(INDEX.summarize(f"# T\n{skipped}\nReal text."), "Real text", skipped)

    def test_digit_without_dot_is_prose(self) -> None:
        self.assertEqual(INDEX.summarize("# T\n2026 was the year."), "2026 was the year")

    def test_cut_at_first_sentence_end(self) -> None:
        self.assertEqual(INDEX.summarize("# T\nOne. Two. Three."), "One")

    def test_line_without_sentence_end_is_whole_line(self) -> None:
        self.assertEqual(INDEX.summarize("# T\nNo full stop here"), "No full stop here")

    def test_long_summary_is_capped(self) -> None:
        out = INDEX.summarize("# T\n" + "word " * 100)
        self.assertLessEqual(len(out), INDEX.MAX_SUMMARY)
        self.assertTrue(out.endswith("..."))

    def test_summary_line_wins(self) -> None:
        self.assertEqual(INDEX.summarize("# T\nProse line.\nsummary: Chosen. Both sentences."), "Chosen. Both sentences.")

    def test_summary_line_works_without_heading(self) -> None:
        self.assertEqual(INDEX.summarize("summary: Only this"), "Only this")

    def test_summary_line_after_ten_lines_is_ignored(self) -> None:
        self.assertEqual(INDEX.summarize("\n".join(["x"] * 10 + ["summary: late"])), "")

    def test_no_heading_no_summary(self) -> None:
        self.assertEqual(INDEX.summarize("Plain text without a heading."), "")

    def test_text_before_heading_is_ignored(self) -> None:
        self.assertEqual(INDEX.summarize("Before.\n# T\nAfter."), "After")

    def test_heading_only(self) -> None:
        self.assertEqual(INDEX.summarize("# T\n\n- only a list"), "")


class Tree(unittest.TestCase):
    """A fake docs tree in a temporary ROOT, with `tracked` patched to its files."""

    FILES = {
        "docs/AI.md": "# AI\nTop level doc.\n",
        "docs/ops/README.md": "# Ops\nThe ops folder.\n",
        "docs/ops/A B.md": "# A\nSpaced name.\n",
        "docs/ops/sheet.docx": "x",
        "docs/ops/pic.jpg": "x",
        "docs/ops/site.css": "x",
        "docs/ops/old.PNG": "x",
        "docs/wiring/bare.md": "# Bare\n- list only\n",
        "docs/wiring/x.csv": "a,b",
    }

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, body in self.FILES.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(body)
        for patch in (mock.patch.object(INDEX, "ROOT", self.root),
                      mock.patch.object(INDEX, "tracked", return_value=sorted(self.FILES))):
            patch.start()
            self.addCleanup(patch.stop)

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = INDEX.main(argv)
        return status, out.getvalue(), err.getvalue()

    def write_index(self) -> None:
        (self.root / "docs/INDEX.md").write_text(INDEX.render(sorted(self.FILES)))

    def test_grouping_and_rows(self) -> None:
        text = INDEX.render(sorted(self.FILES))
        self.assertLess(text.index("## general"), text.index("## ops"))
        self.assertLess(text.index("## ops"), text.index("## wiring"))
        ops = text.split("## ops")[1].split("## wiring")[0]
        self.assertIn("The ops folder\n", ops)          # folder README summary opens the group
        self.assertIn("- [A B.md](ops/A%20B.md): Spaced name", ops)
        self.assertIn("- [AI.md](AI.md): Top level doc", text.split("## general")[1].split("## ops")[0])

    def test_assets_are_counted_not_listed(self) -> None:
        text = INDEX.render(sorted(self.FILES))
        for asset in ("pic.jpg", "site.css", "old.PNG"):
            self.assertNotIn(asset, text)
        self.assertIn("- Plus 3 image, css or script files", text)
        self.assertNotIn("- Plus", text.split("## wiring")[1])

    def test_other_documents_are_listed_compactly(self) -> None:
        text = INDEX.render(sorted(self.FILES))
        self.assertIn("- Other files: [sheet.docx](ops/sheet.docx)", text)
        self.assertIn("- Other files: [x.csv](wiring/x.csv)", text)

    def test_row_without_summary_has_no_colon(self) -> None:
        self.assertIn("- [bare.md](wiring/bare.md)\n", INDEX.render(sorted(self.FILES)))

    def test_check_warns_about_missing_summary_but_passes(self) -> None:
        self.write_index()
        status, out, err = self.run_main(["--check"])
        self.assertEqual(status, 0)
        self.assertIn("WARNING: 1 Markdown documents have no summary", err)
        self.assertIn("docs/wiring/bare.md", err)
        self.assertIn("lists all", out)

    def test_strict_fails_on_missing_summary(self) -> None:
        self.write_index()
        status, out, err = self.run_main(["--check", "--strict"])
        self.assertEqual(status, 1)
        self.assertIn("ERROR: 1 Markdown documents have no summary", err)
        self.assertIn("docs/wiring/bare.md", err)

    def test_strict_passes_when_all_have_summaries(self) -> None:
        (self.root / "docs/wiring/bare.md").write_text("# Bare\nNow it has one.\n")
        self.write_index()
        self.assertEqual(self.run_main(["--check", "--strict"])[0], 0)

    def test_check_ignores_summary_edits_but_not_new_files(self) -> None:
        self.write_index()
        (self.root / "docs/ops/A B.md").write_text("# A\nChanged words.\n")
        self.assertEqual(self.run_main(["--check"])[0], 0)
        (self.root / "docs/ops/new.md").write_text("# N\nNew doc.\n")
        with mock.patch.object(INDEX, "tracked", return_value=sorted(self.FILES) + ["docs/ops/new.md"]):
            status, _, err = self.run_main(["--check"])
        self.assertEqual(status, 1)
        self.assertIn("missing: ops: ops/new.md", err)

    def test_new_asset_changes_the_count_and_fails(self) -> None:
        self.write_index()
        with mock.patch.object(INDEX, "tracked", return_value=sorted(self.FILES) + ["docs/ops/more.png"]):
            status, _, err = self.run_main(["--check"])
        self.assertEqual(status, 1)
        self.assertIn("Plus 4 image", err)

    def test_removed_document_fails(self) -> None:
        self.write_index()
        kept = [f for f in sorted(self.FILES) if f != "docs/wiring/x.csv"]
        with mock.patch.object(INDEX, "tracked", return_value=kept):
            status, _, err = self.run_main(["--check"])
        self.assertEqual(status, 1)
        self.assertIn("not tracked: wiring: wiring/x.csv", err)

    def test_missing_index_fails(self) -> None:
        status, _, err = self.run_main(["--check"])
        self.assertEqual(status, 1)
        self.assertIn("out of date", err)

    def test_no_argument_writes_the_index(self) -> None:
        status, _, _ = self.run_main([])
        self.assertEqual(status, 0)
        self.assertIn("- [A B.md](ops/A%20B.md): Spaced name", (self.root / "docs/INDEX.md").read_text())

    def test_check_writes_nothing(self) -> None:
        self.run_main(["--check"])
        self.assertFalse((self.root / "docs/INDEX.md").exists())


class Arguments(unittest.TestCase):
    """--help and any bad argument stop before git is read, and write no index."""

    def run_main(self, argv):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "docs").mkdir()
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(INDEX, "ROOT", Path(tmp)), mock.patch.object(INDEX, "tracked") as tracked, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = INDEX.main(argv)
            tracked.assert_not_called()
            self.assertEqual(list((Path(tmp) / "docs").iterdir()), [])
        return status, out.getvalue(), err.getvalue()

    def test_unknown_argument_is_refused(self) -> None:
        cases = ((["--chek"], "--chek"), (["--check", "docs"], "docs"), (["docs"], "docs"), (["--check", "--strict", "x"], "x"))
        for argv, bad in cases:
            status, out, err = self.run_main(argv)
            self.assertEqual(status, 2, argv)
            self.assertIn(repr(bad), err)
            self.assertEqual(out, "")

    def test_strict_alone_is_refused(self) -> None:
        status, _, err = self.run_main(["--strict"])
        self.assertEqual(status, 2)
        self.assertIn("not a valid combination", err)

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
        self.assertEqual((status, out, err), (0, INDEX.USAGE + "\n", ""))


if __name__ == "__main__":
    unittest.main()
