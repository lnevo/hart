"""live_paths.txt, the deploy's list of shipped paths, and what deploy_status reports from it.

Git-only: temp repos, no ssh (a fake ssh stands in for the stamp read), no MQTT.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
sys.path.insert(0, str(ROOT / "tools/hosts"))
import live_paths  # noqa: E402

SYNC = (ROOT / "tools/hosts/sync_hart_package.sh").read_text(encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          env=env).stdout.strip()


def commit_file(repo: Path, rel: str, text: str) -> str:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git(repo, "add", rel)
    git(repo, "commit", "-q", "-m", f"edit {rel}")
    return git(repo, "rev-parse", "HEAD")


class TempRepo(unittest.TestCase):
    LIST = "# test list\nlive/tables.xml\nlive/folder\n"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        self.list_file = self.tmp / "live_paths.txt"
        self.list_file.write_text(self.LIST, encoding="utf-8")
        self.base = commit_file(self.repo, "live/tables.xml", "v1\n")
        commit_file(self.repo, "live/folder/a.txt", "a\n")
        self.base = commit_file(self.repo, "docs/note.md", "n1\n")

    def changed(self, commit: str, rev: str = "HEAD"):
        return live_paths.changed(commit, rev, root=self.repo, list_file=self.list_file)


class Changed(TempRepo):
    def test_no_live_change(self) -> None:
        commit_file(self.repo, "docs/note.md", "n2\n")
        commit_file(self.repo, "tools/x.py", "x\n")
        self.assertEqual(self.changed(self.base), (0, []))

    def test_same_commit(self) -> None:
        self.assertEqual(self.changed(self.base), (0, []))

    def test_live_change_counts_only_live_commits(self) -> None:
        commit_file(self.repo, "docs/note.md", "n2\n")
        commit_file(self.repo, "live/folder/b.txt", "b\n")
        commit_file(self.repo, "live/folder/b.txt", "b2\n")
        commit_file(self.repo, "live/tables.xml", "v2\n")
        commit_file(self.repo, "docs/other.md", "o\n")
        self.assertEqual(self.changed(self.base), (3, ["live/folder/b.txt", "live/tables.xml"]))

    def test_change_reverted_counts_commits_but_names_no_path(self) -> None:
        commit_file(self.repo, "live/tables.xml", "v2\n")
        commit_file(self.repo, "live/tables.xml", "v1\n")
        self.assertEqual(self.changed(self.base), (2, []))

    def test_unknown_deployed_commit(self) -> None:
        with self.assertRaisesRegex(live_paths.LivePathsError, "is not a commit in this checkout"):
            self.changed("0" * 40)

    def test_unknown_rev(self) -> None:
        with self.assertRaisesRegex(live_paths.LivePathsError, "nope is not a commit"):
            self.changed(self.base, "nope")

    def test_option_looking_commit_refused(self) -> None:
        with self.assertRaisesRegex(live_paths.LivePathsError, "not a commit name"):
            self.changed("--all")

    def test_empty_commit_refused(self) -> None:
        with self.assertRaisesRegex(live_paths.LivePathsError, "not a commit name"):
            self.changed("")

    def test_not_a_repo(self) -> None:
        with self.assertRaisesRegex(live_paths.LivePathsError, "is not a commit"):
            live_paths.changed("abc", root=self.tmp, list_file=self.list_file)


class ListFile(TempRepo):
    def write(self, text: str) -> None:
        self.list_file.write_text(text, encoding="utf-8")

    def test_comments_and_blanks_skipped(self) -> None:
        self.assertEqual(live_paths.read_list(self.list_file), ["live/tables.xml", "live/folder"])

    def test_missing_list(self) -> None:
        with self.assertRaisesRegex(live_paths.LivePathsError, "cannot read the live path list"):
            live_paths.read_list(self.tmp / "absent.txt")

    def test_empty_list(self) -> None:
        self.write("# nothing\n\n")
        with self.assertRaisesRegex(live_paths.LivePathsError, "lists no paths"):
            live_paths.read_list(self.list_file)

    def test_bad_entries(self) -> None:
        for bad in ("/abs/path", "../up", "a/*.png", "folder/", ":(exclude)x", "a[1]"):
            with self.subTest(bad=bad):
                self.write(f"{bad}\n")
                with self.assertRaisesRegex(live_paths.LivePathsError, "not a plain repo-relative path"):
                    live_paths.read_list(self.list_file)

    def test_duplicate(self) -> None:
        self.write("a/b\na/b\n")
        with self.assertRaisesRegex(live_paths.LivePathsError, "listed twice"):
            live_paths.read_list(self.list_file)

    def test_check_names_missing_paths(self) -> None:
        self.write("live/tables.xml\nlive/gone\nlive/gone2\n")
        with self.assertRaisesRegex(live_paths.LivePathsError, "live/gone, live/gone2"):
            live_paths.check(self.repo, self.list_file)

    def test_check_ok(self) -> None:
        self.assertEqual(live_paths.check(self.repo, self.list_file), ["live/tables.xml", "live/folder"])

    def test_parked_paths_left_out(self) -> None:
        self.write("live/tables.xml\njmri/layouts/hart/dispatcher\njmri/layouts/hart/dispatcher/x.xml\n"
                   "jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py\njmri/layouts/hart/ctc\n")
        self.assertEqual(live_paths.shipped(self.list_file), ["live/tables.xml"])


class RealList(unittest.TestCase):
    def test_every_listed_path_exists(self) -> None:
        live_paths.check()

    def test_cli_error_is_one_clear_line(self) -> None:
        done = subprocess.run([sys.executable, str(ROOT / "tools/hosts/live_paths.py"), "changed", "0" * 40],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stdout, "")
        self.assertRegex(done.stderr, r"^live_paths: .* is not a commit in this checkout.*\n$")
        self.assertNotIn("Traceback", done.stderr)

    def test_sync_runs_the_check(self) -> None:
        self.assertIn('live_paths.py" check', SYNC)

    def test_deploy_script_paths_are_all_listed(self) -> None:
        """Every repo path stage_package and the jython lists name is under a live_paths.txt entry."""
        listed = live_paths.read_list()
        start = SYNC.index("JYTHON_STARTUP_SCRIPTS=(")
        end = SYNC.index("# stage_hosts DIR")
        region = "\n".join(line for line in SYNC[start:end].splitlines()
                           if not line.strip().startswith("#") and "local sm=" not in line)
        sm = "jmri/layouts/hart/scripts/speedmatch"
        region = region.replace('"$sm', f'"$ROOT/{sm}')
        tokens = set(re.findall(r"(?:\$ROOT/|\s)((?:jmri|cats|tools|docs)/[A-Za-z0-9_./-]+)", region))
        tokens |= {"cats/panels/" + p for p in re.findall(r"^\s+(HART_[A-Z]+\.xml)$", region, re.M)}
        # bare-name patterns (lamp_*.png) end at the folder; the regex stops at "*"
        found = {t.rstrip("/") for t in tokens if not t.endswith("/") or t.count("/") > 2}
        self.assertGreater(len(found), 25, found)
        unlisted = sorted(t for t in found
                          if not any(t == p or t.startswith(p + "/") for p in listed))
        self.assertEqual(unlisted, [], "named by sync_hart_package.sh but absent from tools/hosts/live_paths.txt")


class DeployStatusReport(TempRepo):
    """deploy_status.sh run from a copy inside a temp repo, with a fake ssh for the stamp."""

    def setUp(self) -> None:
        super().setUp()
        hosts = self.repo / "tools/hosts"
        hosts.mkdir(parents=True)
        for name in ("deploy_status.sh", "live_paths.py"):
            shutil.copy(ROOT / "tools/hosts" / name, hosts / name)
        shutil.copy(self.list_file, hosts / "live_paths.txt")
        (self.repo / "tools/env").symlink_to(ROOT / "tools/env")
        (self.repo / "tools/hartlib").symlink_to(ROOT / "tools/hartlib")
        (self.tmp / "bin").mkdir()
        self.base = git(self.repo, "rev-parse", "HEAD")

    def status(self, deployed: str) -> subprocess.CompletedProcess:
        stamp = self.tmp / "stamp.txt"
        stamp.write_text(f"# stamp\ncommit={deployed}\nbranch=main\ndirty=no\n", encoding="utf-8")
        ssh = self.tmp / "bin/ssh"
        ssh.write_text(f'#!/bin/sh\ncat "{stamp}"\n', encoding="utf-8")
        ssh.chmod(0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_") and k != "PI_HOST"}
        env.update(PATH=f"{self.tmp / 'bin'}{os.pathsep}{env['PATH']}", HART_ENV_FILE=str(self.tmp / "none.env"),
                   HART_PI_SSH="pi.example.invalid", HART_PI_USERFILES="/srv/pi/JMRI_UserFiles",
                   HOME=str(self.tmp))
        return subprocess.run(["bash", str(self.repo / "tools/hosts/deploy_status.sh"), "--pi"], env=env,
                              capture_output=True, text=True, timeout=60)

    def test_ahead_with_no_live_change(self) -> None:
        commit_file(self.repo, "docs/note.md", "n2\n")
        commit_file(self.repo, "docs/more.md", "m\n")
        done = self.status(self.base)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("2 commit(s) ahead", done.stdout)
        self.assertIn("None of them changes a live artifact: nothing to deploy.", done.stdout)

    def test_ahead_with_live_change(self) -> None:
        commit_file(self.repo, "docs/note.md", "n2\n")
        commit_file(self.repo, "live/tables.xml", "v2\n")
        done = self.status(self.base)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Of them, 1 touch live artifacts; a deploy would ship:", done.stdout)
        self.assertIn("    live/tables.xml", done.stdout)
        self.assertNotIn("docs/note.md", done.stdout)

    def test_unknown_deployed_commit(self) -> None:
        done = self.status("0" * 40)
        self.assertIn("The deployed commit is not in this checkout", done.stdout)
        self.assertNotIn("live artifact", done.stdout)


if __name__ == "__main__":
    unittest.main()
