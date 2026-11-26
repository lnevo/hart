import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "ci"))
from changed_kind import kind  # noqa: E402


class ChangedKind(unittest.TestCase):
    def test_docs_only(self):
        self.assertEqual(kind(["wiki/STATUS.md", "docs/INDEX.md", "tools/README.md", "www/notes.md"]), "docs")

    def test_only_markdown_counts(self):
        # other file types under wiki/ or docs/ are read by full-run checks (tracked-policy, page builders)
        self.assertEqual(kind(["wiki/img/a.png"]), "full")
        self.assertEqual(kind(["docs/wiring/bench/x.csv"]), "full")
        self.assertEqual(kind(["docs/x.json", "wiki/a.md"]), "full")

    def test_mixed_is_full(self):
        self.assertEqual(kind(["wiki/STATUS.md", "tools/check.sh"]), "full")

    def test_agent_rules_are_full(self):
        for p in ("AGENTS.md", "CLAUDE.md", "cats/AGENTS.md", ".claude/skills/x/SKILL.md", ".claude/agents/a.md"):
            self.assertEqual(kind([p]), "full", p)

    def test_pipeline_map_is_full(self):
        self.assertEqual(kind(["docs/pipeline-map/pipeline_map.json"]), "full")
        self.assertEqual(kind(["docs/pipeline-map/x.md"]), "full")

    def test_python_is_full(self):
        self.assertEqual(kind(["tools/ci/changed_kind.py"]), "full")

    def test_empty_is_full(self):
        self.assertEqual(kind([]), "full")
        self.assertEqual(kind(["", "\n"]), "full")

    def test_not_a_prefix_trick(self):
        self.assertEqual(kind(["wikipedia/x.py"]), "full")
        self.assertEqual(kind(["docsx/a.py"]), "full")

    def test_git_quoted_path_is_full(self):
        self.assertEqual(kind(['"wiki/caf\\303\\251.md"']), "full")

    def test_cli(self):
        script = Path(__file__).resolve().parents[3] / "tools" / "ci" / "changed_kind.py"
        out = subprocess.run([sys.executable, str(script)], input="wiki/a.md\n", capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "docs")


if __name__ == "__main__":
    unittest.main()
