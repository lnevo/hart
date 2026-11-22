"""STATUS.md is merged with git's union driver (.gitattributes), so two branches that each add an entry no longer
conflict; status_counts.py --check stops on the duplicate a union merge can leave. The schematic plugin must sit at the
commit the branch pins before check.sh runs (hart_plugin_pin_problem)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/ops"))
import status_counts  # noqa: E402

GUARD = ROOT / "tools/hosts/profile_tables_guard.sh"


def git_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return env


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always", *args], cwd=cwd,
                          env=git_env(), capture_output=True, text=True, check=True).stdout


class Duplicates(unittest.TestCase):
    def test_a_clean_list_has_none(self) -> None:
        self.assertEqual([], status_counts.duplicates("- **A:** one\n- **B:** two\nprose\n"))

    def test_a_repeated_line_and_a_repeated_lead_are_found(self) -> None:
        found = status_counts.duplicates("- **A:** one\n- **B:** two\n- **A:** other\n- **B:** two\n")
        self.assertEqual(["two entries for: A:", "repeated line: - **B:** two"], found)

    def test_the_committed_status_has_none(self) -> None:
        self.assertEqual([], status_counts.duplicates((ROOT / "wiki/STATUS.md").read_text(encoding="utf-8")))


class UnionMerge(unittest.TestCase):
    def test_two_added_entries_merge_without_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            git(repo, "init", "-q", "-b", "main")
            (repo / "wiki").mkdir()
            (repo / ".gitattributes").write_text((ROOT / ".gitattributes").read_text(encoding="utf-8"), encoding="utf-8")
            status = repo / "wiki/STATUS.md"
            status.write_text("# Live status\n\n- **Old:** kept\n", encoding="utf-8")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "base")
            git(repo, "checkout", "-qb", "a")
            status.write_text("# Live status\n\n- **A:** from a\n- **Old:** kept\n", encoding="utf-8")
            git(repo, "commit", "-qam", "a")
            git(repo, "checkout", "-q", "main")
            git(repo, "checkout", "-qb", "b")
            status.write_text("# Live status\n\n- **B:** from b\n- **Old:** kept\n", encoding="utf-8")
            git(repo, "commit", "-qam", "b")
            git(repo, "merge", "-q", "--no-edit", "a")          # check=True: a conflict would raise
            text = status.read_text(encoding="utf-8")
            for entry in ("- **A:** from a", "- **B:** from b", "- **Old:** kept"):
                self.assertEqual(1, text.count(entry), text)
            self.assertNotIn("<<<<<<<", text)


class PluginPin(unittest.TestCase):
    def problem(self, root: Path, **env: str) -> str:
        e = dict(git_env(), **env)
        e.pop("SCHEMATIC_PLUGIN", None) if "SCHEMATIC_PLUGIN" not in env else None
        return subprocess.run(["bash", "-c", f'source "{GUARD}"; hart_plugin_pin_problem "$1"', "_", str(root)], env=e,
                              capture_output=True, text=True, check=True).stdout.strip()

    def test_a_plugin_off_its_pin_is_named_and_one_at_its_pin_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            plugin, repo = Path(d) / "plugin", Path(d) / "repo"
            for p in (plugin, repo):
                p.mkdir()
                git(p, "init", "-q", "-b", "main")
            (plugin / "a.txt").write_text("1", encoding="utf-8")
            git(plugin, "add", "-A")
            git(plugin, "commit", "-qm", "one")
            git(repo, "submodule", "add", "-q", str(plugin), "external/model-railroad-skills")
            git(repo, "commit", "-qm", "pin")
            self.assertEqual("", self.problem(repo))
            sub = repo / "external/model-railroad-skills"
            (sub / "a.txt").write_text("2", encoding="utf-8")
            git(sub, "commit", "-qam", "two")                  # the checkout moves off the pinned commit
            self.assertIn("not the commit this branch pins", self.problem(repo))
            self.assertEqual("", self.problem(repo, SCHEMATIC_PLUGIN=str(plugin)))


if __name__ == "__main__":
    unittest.main()
