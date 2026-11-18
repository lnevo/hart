"""tools/audit/portal_inputs.py: which changes make check.sh run the portal build check."""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/audit"))
import portal_inputs  # noqa: E402

PREPARE = ROOT / "www/scripts/prepare_github_pages.py"


def _constant(path: Path, name: str):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path}")


class SiteInputs(unittest.TestCase):
    def test_every_mirror_the_build_copies_from_is_a_site_input(self) -> None:
        # A new mirror folder in prepare_github_pages.py must be added to SITE_PREFIXES, or check.sh would skip.
        for prefix in _constant(PREPARE, "MIRROR_PREFIXES"):
            folder = prefix.removeprefix("../")
            self.assertTrue(folder.startswith(portal_inputs.SITE_PREFIXES), folder)

    def test_the_card_pipeline_import_is_a_site_input(self) -> None:
        self.assertIn('"ops/hart-ops/card_pipeline"', PREPARE.read_text(encoding="utf-8"))
        self.assertTrue("ops/hart-ops/card_pipeline/private_name.py".startswith(portal_inputs.SITE_PREFIXES))

    def test_manifest_sources_count_wherever_they_live(self) -> None:
        sources = portal_inputs.manifest_sources(ROOT)
        self.assertTrue(sources)
        outside = sorted(s for s in sources if not s.startswith(portal_inputs.SITE_PREFIXES))
        self.assertTrue(outside, "expected manifest sources outside the prefixes (jmri/)")
        self.assertEqual([outside[0]], portal_inputs.site_inputs([outside[0]], sources))

    def test_a_tables_or_cats_change_is_not_a_site_input(self) -> None:
        paths = ["jmri/layouts/hart/output/tables.xml", "cats/scripts/validate_cats_panel.py", "tools/check.sh"]
        self.assertEqual([], portal_inputs.site_inputs(paths, set()))


class ChangedFiles(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    def test_committed_unstaged_and_untracked_changes_all_count(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            self.git(repo, "init", "-q", "-b", "main")
            self.git(repo, "config", "user.email", "test@example.invalid")
            self.git(repo, "config", "user.name", "test")
            (repo / "a.txt").write_text("a")
            (repo / "b.txt").write_text("b")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "base")
            self.git(repo, "branch", "base")
            (repo / "www").mkdir()
            (repo / "www/page.html").write_text("x")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-qm", "site")
            (repo / "a.txt").write_text("changed")
            (repo / "new.txt").write_text("new")
            self.assertEqual(["a.txt", "new.txt", "www/page.html"], portal_inputs.changed_files(repo, "base"))

    def test_no_merge_base_means_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.git(Path(d), "init", "-q")
            self.assertIsNone(portal_inputs.changed_files(Path(d), "origin/main"))


if __name__ == "__main__":
    unittest.main()
