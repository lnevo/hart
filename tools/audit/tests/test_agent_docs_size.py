"""The root-size rule of tools/audit/check_agent_docs.py: the root AGENTS.md over its line or word cap fails."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("check_agent_docs", ROOT / "tools/audit/check_agent_docs.py")
DOCS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DOCS)


class RootSizeTest(unittest.TestCase):
    def test_at_the_caps_passes(self) -> None:
        lines = ["w"] * DOCS.MAX_ROOT_LINES
        self.assertEqual(DOCS.root_size("\n".join(lines) + "\n"), [])
        self.assertEqual(DOCS.root_size(" ".join(["w"] * DOCS.MAX_ROOT_WORDS)), [])

    def test_one_line_over_fails(self) -> None:
        problems = DOCS.root_size("w\n" * (DOCS.MAX_ROOT_LINES + 1))
        self.assertEqual(len(problems), 1)
        self.assertIn("lines", problems[0])

    def test_one_word_over_fails(self) -> None:
        problems = DOCS.root_size(" ".join(["w"] * (DOCS.MAX_ROOT_WORDS + 1)))
        self.assertEqual(len(problems), 1)
        self.assertIn("words", problems[0])

    def test_both_over_gives_two_lines(self) -> None:
        self.assertEqual(len(DOCS.root_size(("w " * 20 + "\n") * (DOCS.MAX_ROOT_LINES + 1))), 2)

    def test_repo_agents_md_fits(self) -> None:
        self.assertEqual(DOCS.root_size(), [])


if __name__ == "__main__":
    unittest.main()
