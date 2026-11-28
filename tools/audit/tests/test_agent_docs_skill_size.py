"""The skill word cap of tools/audit/check_agent_docs.py: any Markdown file under .claude/skills/ or .claude/agents/
over MAX_SKILL_WORDS fails."""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("check_agent_docs", ROOT / "tools/audit/check_agent_docs.py")
assert _spec is not None and _spec.loader is not None
DOCS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DOCS)

REL = ".claude/skills/demo/SKILL.md"


def _skill(words: int) -> str:
    """A skill file of exactly `words` words, four of them in the frontmatter (`---`, `name:`, `demo`, `---`)."""
    return "---\nname: demo\n---\n" + " ".join(["w"] * (words - 4)) + "\n"


class SkillSizeTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = mock.patch.object(DOCS, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write(self, text: str) -> None:
        path = self.root / REL
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")

    def test_at_the_cap_passes(self) -> None:
        self._write(_skill(DOCS.MAX_SKILL_WORDS))
        self.assertEqual(DOCS.skill_size(REL), [])

    def test_one_word_over_fails_with_file_count_and_hint(self) -> None:
        self._write(_skill(DOCS.MAX_SKILL_WORDS + 1))
        problems = DOCS.skill_size(REL)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith(f"{REL}: {DOCS.MAX_SKILL_WORDS + 1} words"))
        self.assertIn("a reference file beside the skill or under docs/", problems[0])

    def test_frontmatter_words_count(self) -> None:
        body_only = " ".join(["w"] * DOCS.MAX_SKILL_WORDS)
        self._write("---\nname: demo\n---\n" + body_only)
        self.assertEqual(len(DOCS.skill_size(REL)), 1)

    def test_unreadable_file_is_an_error(self) -> None:
        with self.assertRaises(DOCS.AgentDocsError):
            DOCS.skill_size(REL)


class SkillFilesTest(unittest.TestCase):
    """skill_files() on a temp git repo: every tracked .md under .claude/skills/ and .claude/agents/, nothing else."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = mock.patch.object(DOCS, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _repo(self, tracked: list[str], untracked: tuple[str, ...] = ()) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        for rel in [*tracked, *untracked]:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", *tracked], cwd=self.root, check=True)

    def test_covers_skills_reference_files_and_agents(self) -> None:
        self._repo([
            ".claude/skills/demo/SKILL.md",
            ".claude/skills/demo/reference.md",
            ".claude/skills/demo/deep/more.md",
            ".claude/skills/demo/index.html",
            ".claude/agents/helper.md",
            ".claude/commands/done.md",
            "docs/note.md",
        ], untracked=(".claude/skills/demo/draft.md",))
        self.assertEqual(sorted(DOCS.skill_files()), [
            ".claude/agents/helper.md",
            ".claude/skills/demo/SKILL.md",
            ".claude/skills/demo/deep/more.md",
            ".claude/skills/demo/reference.md",
        ])

    def test_a_long_reference_file_fails(self) -> None:
        rel = ".claude/skills/demo/reference.md"
        self._repo([rel])
        (self.root / rel).write_text(" ".join(["w"] * (DOCS.MAX_SKILL_WORDS + 1)), encoding="utf-8")
        problems = [p for f in DOCS.skill_files() for p in DOCS.skill_size(f)]
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith(rel))


if __name__ == "__main__":
    unittest.main()
