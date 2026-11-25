"""Since ADR-038 the status page is one file per entry under wiki/status/: two branches that each add an entry merge
without a conflict, two that edit the same entry conflict as a real conflict (no union merge keeps both), and the log
(wiki/STATUS_LOG.md) still merges with git's union driver (.gitattributes). status_counts.py --check stops on a
doubled entry in the built page. The schematic plugin must sit at the commit the branch pins before check.sh runs
(hart_plugin_pin_problem)."""
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

    def test_two_versions_of_an_unled_entry_are_found(self) -> None:
        """2026-11-25: a union merge kept two versions of one Future goals bullet that differed further in."""
        text = ("- Verify the stock bugs and send fixes upstream if they hold: the hosts run the overlay.\n"
                "- Other goal with its own words entirely here.\n"
                "- Verify the stock bugs and send fixes upstream if they hold: the hosts stay on stock.\n")
        self.assertEqual(["two entries opening: verify the stock bugs and send fixes upstream"],
                         status_counts.duplicates(text))

    def test_unled_entries_that_differ_early_or_are_short_pass(self) -> None:
        text = ("- Move the LCOS bridge from the Windows box to the Pi.\n"
                "- Move the speed matching runs to the second loop next week.\n"
                "- Short one.\n- Short one too.\n")
        self.assertEqual([], status_counts.duplicates(text))

    def test_a_bold_led_entry_is_judged_by_its_lead_not_its_words(self) -> None:
        text = ("- **A:** the same eight opening words come here and more\n"
                "- **B:** the same eight opening words come here and more\n")
        self.assertEqual([], status_counts.duplicates(text))

    def test_the_built_status_has_none(self) -> None:
        self.assertEqual([], status_counts.duplicates(status_counts.build()[0]))


class EntryMerge(unittest.TestCase):
    def repo(self, d: str) -> Path:
        repo = Path(d)
        git(repo, "init", "-q", "-b", "main")
        (repo / "wiki/status/current").mkdir(parents=True)
        (repo / ".gitattributes").write_text((ROOT / ".gitattributes").read_text(encoding="utf-8"), encoding="utf-8")
        (repo / "wiki/status/current/old.md").write_text("**Old:** kept\n", encoding="utf-8")
        (repo / "wiki/STATUS_LOG.md").write_text("# Status log\n\nUpdated: base\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "base")
        return repo

    def branch(self, repo: Path, name: str, files: dict[str, str]) -> None:
        git(repo, "checkout", "-q", "main")
        git(repo, "checkout", "-qb", name)
        for rel, body in files.items():
            (repo / rel).write_text(body, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", name)

    def test_two_added_entries_and_two_log_lines_merge_without_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = self.repo(d)
            self.branch(repo, "a", {"wiki/status/current/a.md": "**A:** from a\n",
                                    "wiki/STATUS_LOG.md": "# Status log\n\nUpdated: a\nUpdated: base\n"})
            self.branch(repo, "b", {"wiki/status/current/b.md": "**B:** from b\n",
                                    "wiki/STATUS_LOG.md": "# Status log\n\nUpdated: b\nUpdated: base\n"})
            git(repo, "merge", "-q", "--no-edit", "a")          # check=True: a conflict would raise
            names = sorted(p.name for p in (repo / "wiki/status/current").iterdir())
            self.assertEqual(["a.md", "b.md", "old.md"], names)
            log = (repo / "wiki/STATUS_LOG.md").read_text(encoding="utf-8")
            for line in ("Updated: a", "Updated: b", "Updated: base"):
                self.assertEqual(1, log.splitlines().count(line), log)

    def test_two_edits_of_one_entry_conflict_instead_of_keeping_both(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo = self.repo(d)
            self.branch(repo, "a", {"wiki/status/current/old.md": "**Old:** edited on a\n"})
            self.branch(repo, "b", {"wiki/status/current/old.md": "**Old:** edited on b\n"})
            done = subprocess.run(["git", "-c", "commit.gpgsign=false", "merge", "-q", "--no-edit", "a"], cwd=repo,
                                  env=git_env(), capture_output=True, text=True)
            self.assertNotEqual(0, done.returncode, done.stdout)
            self.assertIn("<<<<<<<", (repo / "wiki/status/current/old.md").read_text(encoding="utf-8"))


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
