"""check_tracked_policy reports ignored, symlinked and forbidden tracked files, and a git failure as FAIL."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("check_tracked_policy", ROOT / "tools/audit/check_tracked_policy.py")
assert spec is not None and spec.loader is not None
POLICY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(POLICY)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class PolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _git(self.repo, "init", "-q")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def add(self, *rels: str) -> None:
        _git(self.repo, "add", "-f", "--", *rels)

    def test_clean_repo_passes(self) -> None:
        (self.repo / "README.md").write_text("x\n")
        (self.repo / ".env.example").write_text("A=1\n")
        self.add("README.md", ".env.example")
        self.assertEqual(POLICY.problems(self.repo), [])

    def test_each_kind_of_problem_is_reported(self) -> None:
        (self.repo / ".gitignore").write_text("*.tmp\n")
        (self.repo / "a.tmp").write_text("x\n")
        (self.repo / ".env").write_text("SECRET=1\n")
        (self.repo / "media").mkdir()
        (self.repo / "media/p.jpg").write_text("x\n")
        os.symlink("README.md", self.repo / "link.md")
        self.add(".gitignore", "a.tmp", ".env", "media/p.jpg", "link.md")
        self.assertEqual(POLICY.problems(self.repo), [
            "tracked but ignored: a.tmp",
            "tracked symlink: link.md",
            "forbidden file: .env",
            "belongs outside git: media/p.jpg",
        ])

    def test_git_failure_is_one_fail_line(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(POLICY.main(Path(plain)), 1)
        self.assertRegex(out.getvalue(), r"^FAIL git ls-files -ci --exclude-standard failed in .*not a git repository")


if __name__ == "__main__":
    unittest.main()
