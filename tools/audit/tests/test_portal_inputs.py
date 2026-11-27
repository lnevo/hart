"""tools/audit/portal_inputs.py: which changes make check.sh run the portal build check."""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/audit"))
import portal_inputs  # noqa: E402

# The site build (www/scripts/prepare_github_pages.py) keeps its mirror list with its other shared settings.
COMMON = ROOT / "www/scripts/portal_common.py"


def _constant(path: Path, name: str):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path}")


class SiteInputs(unittest.TestCase):
    def test_every_mirror_the_build_copies_from_is_a_site_input(self) -> None:
        # A new mirror folder in the site build must be added to SITE_PREFIXES, or check.sh would skip.
        for prefix in _constant(COMMON, "MIRROR_PREFIXES"):
            folder = prefix.removeprefix("../")
            self.assertTrue(folder.startswith(portal_inputs.SITE_PREFIXES), folder)

    def test_every_folder_the_site_scripts_import_from_is_a_site_input(self) -> None:
        # The build imports www/scripts modules, and they add repo folders to sys.path by literal path.
        found = set()
        for script in sorted((ROOT / "www/scripts").glob("*.py")):
            for line in script.read_text(encoding="utf-8").splitlines():
                if "sys.path" in line:
                    found |= set(re.findall(r'"([a-z][\w.-]*/[\w./-]+)"', line))
        self.assertIn("ops/hart-ops/card_pipeline", found)
        self.assertIn("tools/hartlib/src", found)
        for folder in sorted(found):
            self.assertTrue(f"{folder}/".startswith(portal_inputs.SITE_PREFIXES), folder)

    def test_manifest_sources_count_wherever_they_live(self) -> None:
        sources = portal_inputs.manifest_sources(ROOT)
        self.assertTrue(sources)
        outside = sorted(s for s in sources if not s.startswith(portal_inputs.SITE_PREFIXES))
        self.assertTrue(outside, "expected manifest sources outside the prefixes (jmri/)")
        self.assertEqual([outside[0]], portal_inputs.site_inputs([outside[0]], sources))

    def test_the_map_page_tools_are_site_inputs(self) -> None:
        # the build writes library/pipeline-map.html itself (ADR-036): a change to its builder runs the portal check
        for path in portal_inputs.SITE_TOOLS:
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertEqual([path], portal_inputs.site_inputs([path], set()))
        self.assertEqual([], portal_inputs.site_inputs(["tools/ops/pipeline_query.py"], set()))

    def test_every_renderer_part_is_a_site_input(self) -> None:
        # the schematic PNG on the site is drawn by render_le_layout.py and the parts it imports
        parts = ["jmri/layouts/hart/scripts/render_le_layout.py", "jmri/layouts/hart/scripts/render_le_geometry.py",
                 "jmri/layouts/hart/scripts/render_le_draw.py"]
        self.assertEqual(parts, portal_inputs.site_inputs(parts, set()))

    def test_a_tables_or_cats_change_is_not_a_site_input(self) -> None:
        paths = ["jmri/layouts/hart/output/tables.xml", "cats/scripts/digicon_trace.py", "tools/check.sh"]
        self.assertEqual([], portal_inputs.site_inputs(paths, set()))


class ChangedFiles(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    def init(self, repo: Path) -> None:
        self.git(repo, "init", "-q", "-b", "main")
        self.git(repo, "config", "user.email", "test@example.invalid")
        self.git(repo, "config", "user.name", "test")

    def commit(self, repo: Path, message: str) -> None:
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", message)

    def test_committed_unstaged_and_untracked_changes_all_count(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            self.init(repo)
            (repo / "a.txt").write_text("a")
            (repo / "b.txt").write_text("b")
            self.commit(repo, "base")
            self.git(repo, "branch", "base")
            (repo / "www").mkdir()
            (repo / "www/page.html").write_text("x")
            self.commit(repo, "site")
            (repo / "a.txt").write_text("changed")
            (repo / "new.txt").write_text("new")
            self.assertEqual(["a.txt", "new.txt", "www/page.html"], portal_inputs.changed_files(repo, "base"))

    def test_a_rename_counts_under_both_paths(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            self.init(repo)
            (repo / "www").mkdir()
            (repo / "www/data.json").write_text("{\"a\": 1}\n" * 20)
            self.commit(repo, "base")
            self.git(repo, "branch", "base")
            (repo / "tools").mkdir()
            self.git(repo, "mv", "www/data.json", "tools/data.json")
            self.commit(repo, "move")
            self.assertEqual(["tools/data.json", "www/data.json"], portal_inputs.changed_files(repo, "base"))

    def test_a_crash_runs_the_check_and_only_no_change_skips_it(self) -> None:
        text = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
        self.assertIn('"$portal_rc" -eq 3', text)
        self.assertEqual(3, portal_inputs.NO_CHANGE)

    def test_no_merge_base_means_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.git(Path(d), "init", "-q")
            with self.assertRaisesRegex(portal_inputs.ChangedFilesError, "no merge base with origin/main"):
                portal_inputs.changed_files(Path(d), "origin/main")

    def test_git_that_cannot_run_is_a_changed_files_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(portal_inputs.ChangedFilesError, "no merge base"):
                portal_inputs.changed_files(Path(d) / "nowhere", "origin/main")


if __name__ == "__main__":
    unittest.main()
