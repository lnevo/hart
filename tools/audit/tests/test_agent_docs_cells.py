"""The cell-length rule of tools/audit/check_agent_docs.py: a table cell in wiki/ or AGENTS.md over 80 words fails."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("check_agent_docs", ROOT / "tools/audit/check_agent_docs.py")
DOCS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DOCS)

LONG = " ".join(["word"] * 81)
OK = " ".join(["word"] * 80)
HEAD = "| A | B |\n|---|---|\n"


def counts(text: str) -> list[tuple[int, int, int]]:
    return DOCS.cell_word_counts("wiki/x.md", text)


def problems(text: str, rel: str = "wiki/x.md") -> list[str]:
    return DOCS.long_cells(rel, text)


class SplitCellsTest(unittest.TestCase):
    def test_outer_pipes_make_no_empty_cells(self) -> None:
        self.assertEqual(DOCS.split_cells("| a | b |"), [" a ", " b "])
        self.assertEqual(DOCS.split_cells("a | b"), ["a ", " b"])

    def test_escaped_pipe_does_not_split(self) -> None:
        self.assertEqual(DOCS.split_cells(r"| a \| b | c |"), [r" a \| b ", " c "])

    def test_pipe_in_inline_code_does_not_split(self) -> None:
        self.assertEqual(DOCS.split_cells("| `a|b` | c |"), [" `a|b` ", " c "])
        self.assertEqual(DOCS.split_cells("| ``a|`b`` | c |"), [" ``a|`b`` ", " c "])

    def test_lone_backtick_is_text_and_a_pipe_after_it_splits(self) -> None:
        self.assertEqual(DOCS.split_cells("| it`s | c |"), [" it`s ", " c "])

    def test_trailing_escaped_pipe_is_not_the_closing_pipe(self) -> None:
        self.assertEqual(DOCS.split_cells(r"| a | b \|"), [" a ", r" b \|"])


class CountTest(unittest.TestCase):
    def test_exactly_80_passes_and_81_fails(self) -> None:
        self.assertEqual(problems(f"{HEAD}| {OK} | x |\n"), [])
        out = problems(f"{HEAD}| x | {LONG} |\n")
        self.assertEqual(len(out), 1)
        self.assertIn("wiki/x.md:3", out[0])
        self.assertIn("cell 2 has 81 words", out[0])

    def test_line_number_counts_lines_above_the_table(self) -> None:
        text = "# T\n\ntext\n\n" + HEAD + f"| a | b |\n| {LONG} | b |\n"
        self.assertIn("wiki/x.md:8:", problems(text)[0])

    def test_words_are_counted_per_cell_not_per_row(self) -> None:
        half = " ".join(["w"] * 50)
        self.assertEqual(problems(f"{HEAD}| {half} | {half} |\n"), [])

    def test_escaped_pipe_and_code_pipe_keep_one_cell(self) -> None:
        text = f"{HEAD}| {' '.join(['w'] * 45)} \\| {' '.join(['w'] * 45)} | x |\n"
        self.assertIn("cell 1 has 91 words", problems(text)[0])
        text = f"{HEAD}| `{' '.join(['w'] * 45)}|{' '.join(['w'] * 45)}` | x |\n"
        self.assertIn("cell 1 has", problems(text)[0])

    def test_br_counts_as_a_space(self) -> None:
        self.assertEqual(counts(HEAD + "| a<br>b | c |\n")[2][2], 2)

    def test_br_variants_are_spaces(self) -> None:
        for br in ("<br/>", "<br />", "<BR>"):
            self.assertEqual(counts(HEAD + f"| a{br}b | c |\n")[2][2], 2, br)

    def test_table_without_outer_pipes(self) -> None:
        self.assertEqual(len(problems(f"A | B\n--|--\nx | {LONG}\n")), 1)

    def test_text_outside_a_table_is_not_counted(self) -> None:
        self.assertEqual(problems(f"{LONG}\n\n| a | b |\n"), [])

    def test_pipe_line_without_delimiter_row_is_not_a_table(self) -> None:
        self.assertEqual(problems(f"| {LONG} | x |\n| y | z |\n"), [])

    def test_delimiter_with_another_column_count_is_not_a_table(self) -> None:
        self.assertEqual(problems(f"| a | b |\n|---|\n| {LONG} | x |\n"), [])

    def test_table_ends_at_the_blank_line(self) -> None:
        self.assertEqual(problems(f"{HEAD}| a | b |\n\n| {LONG} | c |\n"), [])

    def test_two_tables_in_one_file(self) -> None:
        text = f"{HEAD}| a | b |\n\ntext\n\n{HEAD}| a | {LONG} |\n"
        self.assertEqual(len(problems(text)), 1)

    def test_header_row_cell_is_counted_too(self) -> None:
        self.assertEqual(len(problems(f"| {LONG} | B |\n|---|---|\n| a | b |\n")), 1)


class SkipTest(unittest.TestCase):
    def test_code_fence_is_not_read(self) -> None:
        text = f"```\n{HEAD}| a | {LONG} |\n```\n"
        self.assertEqual(problems(text), [])
        text = f"~~~sh\n{HEAD}| a | {LONG} |\n~~~\n"
        self.assertEqual(problems(text), [])

    def test_longer_fence_is_not_closed_by_a_shorter_one(self) -> None:
        text = f"````\n```\n{HEAD}| a | {LONG} |\n````\n"
        self.assertEqual(problems(text), [])

    def test_table_after_a_closed_fence_is_read(self) -> None:
        text = f"```\ncode\n```\n{HEAD}| a | {LONG} |\n"
        self.assertIn("wiki/x.md:6:", problems(text)[0])

    def test_html_comment_is_not_read_across_lines(self) -> None:
        text = f"<!--\n{HEAD}| a | {LONG} |\n-->\n"
        self.assertEqual(problems(text), [])

    def test_inline_comment_words_are_not_counted(self) -> None:
        text = f"{HEAD}| a | ok <!-- {LONG} --> ok |\n"
        self.assertEqual(problems(text), [])

    def test_fence_inside_a_comment_does_not_open_one(self) -> None:
        text = f"<!--\n```\n-->\n{HEAD}| a | {LONG} |\n"
        self.assertEqual(len(problems(text)), 1)

    def test_comment_marker_inside_code_is_text(self) -> None:
        text = f"Use `<!--` to open.\n\n{HEAD}| a | {LONG} |\n"
        self.assertEqual(len(problems(text)), 1)


class ErrorTest(unittest.TestCase):
    def test_unclosed_fence_is_an_error_naming_its_line(self) -> None:
        with self.assertRaisesRegex(DOCS.AgentDocsError, r"wiki/x\.md:2: code fence never closed"):
            counts(f"text\n```\n{HEAD}| a | {LONG} |\n")

    def test_unclosed_comment_is_an_error_naming_its_line(self) -> None:
        with self.assertRaisesRegex(DOCS.AgentDocsError, r"wiki/x\.md:3: HTML comment never closed"):
            counts("a\n\n<!-- open\nmore\n")

    def test_long_cells_lists_an_unclosed_fence_as_a_problem(self) -> None:
        self.assertEqual(problems("a\n```\nb\n"), ["wiki/x.md:2: code fence never closed"])

    def test_inline_code_line_is_not_a_fence(self) -> None:
        self.assertEqual(counts("```foo``` bar\n"), [])

    def test_missing_file_is_a_domain_error(self) -> None:
        with self.assertRaisesRegex(DOCS.AgentDocsError, r"wiki/does-not-exist\.md: cannot read"):
            DOCS.long_cells("wiki/does-not-exist.md")

    def test_file_that_is_not_utf8_is_a_domain_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "wiki").mkdir()
            (Path(tmp) / "wiki/bad.md").write_bytes(b"\xff\xfe| a |\n")
            with mock.patch.object(DOCS, "ROOT", Path(tmp)):
                with self.assertRaisesRegex(DOCS.AgentDocsError, r"wiki/bad\.md: cannot read"):
                    DOCS.long_cells("wiki/bad.md")

    def test_main_reports_an_unreadable_file_as_fail(self) -> None:
        with mock.patch.object(DOCS, "agent_files", return_value=[]), \
                mock.patch.object(DOCS, "cell_files", return_value=["wiki/gone.md"]), \
                mock.patch("builtins.print") as out:
            self.assertEqual(DOCS.main(), 1)
        self.assertIn("FAIL wiki/gone.md: cannot read", out.call_args[0][0])


class ExemptTest(unittest.TestCase):
    def test_status_log_and_archive_are_exempt(self) -> None:
        text = f"{HEAD}| a | {LONG} |\n"
        self.assertEqual(problems(text, "wiki/STATUS_LOG.md"), [])
        self.assertEqual(problems(text, "wiki/archive/old.md"), [])
        self.assertEqual(problems(text, "wiki/archive/sub/old.md"), [])

    def test_exemption_survives_dot_segments(self) -> None:
        text = f"{HEAD}| a | {LONG} |\n"
        self.assertEqual(problems(text, "./wiki/archive/old.md"), [])
        self.assertEqual(problems(text, "wiki/pipelines/../archive/old.md"), [])
        self.assertEqual(problems(text, "wiki/./STATUS_LOG.md"), [])

    def test_exemption_keeps_forward_slashes_on_windows(self) -> None:
        import ntpath
        with mock.patch("os.path", ntpath):
            self.assertTrue(DOCS.is_cell_exempt("wiki/./STATUS_LOG.md"))
            self.assertTrue(DOCS.is_cell_exempt("wiki/archive/old.md"))

    def test_lookalike_names_are_not_exempt(self) -> None:
        text = f"{HEAD}| a | {LONG} |\n"
        self.assertEqual(len(problems(text, "wiki/archive-notes.md")), 1)
        self.assertEqual(len(problems(text, "wiki/pipelines/STATUS_LOG.md")), 1)
        self.assertEqual(len(problems(text, "wiki/STATUS.md")), 1)

    def test_agents_md_is_covered(self) -> None:
        self.assertEqual(len(problems(f"{HEAD}| a | {LONG} |\n", "AGENTS.md")), 1)


class RepoTest(unittest.TestCase):
    def test_file_list_has_wiki_pages_and_agents_md_but_not_history(self) -> None:
        files = DOCS.cell_files()
        self.assertIn("AGENTS.md", files)
        self.assertIn("wiki/home.md", files)
        self.assertNotIn("wiki/STATUS_LOG.md", files)
        self.assertFalse([f for f in files if f.startswith("wiki/archive/")])
        self.assertTrue(all(f.endswith(".md") for f in files))

    def test_tracked_file_missing_from_the_tree_is_skipped(self) -> None:
        with mock.patch.object(DOCS, "_git", return_value=["wiki/gone-for-good.md", "wiki/home.md"]):
            self.assertEqual(DOCS.cell_files(), ["wiki/home.md"])

    def test_tracked_files_have_no_long_cell(self) -> None:
        self.assertEqual([p for rel in DOCS.cell_files() for p in DOCS.long_cells(rel)], [])


if __name__ == "__main__":
    unittest.main()
