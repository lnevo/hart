"""live_paths.txt, the deploy's list of shipped paths, and what deploy_status reports from it.

Git-only: temp repos, no ssh (a fake ssh stands in for the stamp read), no MQTT.
"""
from __future__ import annotations

import json
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

STEPS = ROOT / "tools/hosts/deploy"
SYNC = (ROOT / "tools/hosts/sync_hart_package.sh").read_text(encoding="utf-8")   # the entry point
GATE = (STEPS / "gate.sh").read_text(encoding="utf-8")                             # runs the live paths check
COMMON = (STEPS / "common.sh").read_text(encoding="utf-8")
STAGE = (STEPS / "stage.sh").read_text(encoding="utf-8")
MAC = (STEPS / "ship_mac.sh").read_text(encoding="utf-8")
# the jython the Mac and the Pi install, which common.sh reads (one "ROLE PATH" row each)
JYTHON_LIST = (ROOT / "tools/hosts/pi/jython_scripts.txt").read_text(encoding="utf-8")


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
        self.assertEqual(self.changed(self.base), {"ahead": (0, []), "behind": (0, [])})

    def test_same_commit(self) -> None:
        self.assertEqual(self.changed(self.base), {"ahead": (0, []), "behind": (0, [])})

    def test_live_change_counts_only_live_commits(self) -> None:
        commit_file(self.repo, "docs/note.md", "n2\n")
        commit_file(self.repo, "live/folder/b.txt", "b\n")
        commit_file(self.repo, "live/folder/b.txt", "b2\n")
        commit_file(self.repo, "live/tables.xml", "v2\n")
        commit_file(self.repo, "docs/other.md", "o\n")
        self.assertEqual(self.changed(self.base)["ahead"], (3, ["live/folder/b.txt", "live/tables.xml"]))

    def test_change_reverted_counts_commits_but_names_no_path(self) -> None:
        commit_file(self.repo, "live/tables.xml", "v2\n")
        commit_file(self.repo, "live/tables.xml", "v1\n")
        self.assertEqual(self.changed(self.base)["ahead"], (2, []))

    def test_deployed_commit_on_another_branch(self) -> None:
        """Not an ancestor of HEAD: ahead and behind both use the merge base, and nothing raises."""
        git(self.repo, "checkout", "-q", "-b", "side", self.base)
        side = commit_file(self.repo, "live/tables.xml", "side\n")
        git(self.repo, "checkout", "-q", "main")
        commit_file(self.repo, "live/folder/m.txt", "m\n")
        self.assertEqual(self.changed(side), {"ahead": (1, ["live/folder/m.txt"]),
                                              "behind": (1, ["live/tables.xml"])})

    def test_host_ahead_of_checkout_is_reported_behind(self) -> None:
        deployed = commit_file(self.repo, "live/tables.xml", "v2\n")
        git(self.repo, "reset", "-q", "--hard", self.base)
        self.assertEqual(self.changed(deployed), {"ahead": (0, []), "behind": (1, ["live/tables.xml"])})

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
        self.assertIn('live_paths.py" check', GATE)
        self.assertIn("gate.sh", SYNC)

    def test_sync_check_runs_after_argument_parsing(self) -> None:
        self.assertGreater(SYNC.index('bash "$DEPLOY_STEPS/gate.sh"'), SYNC.index("Unknown option"))  # the entry parses its flags first
        self.assertGreater(GATE.index('live_paths.py" check'), GATE.index("unknown option"))

    def test_sync_help_is_not_blocked_by_a_bad_list(self) -> None:
        done = self.sync_with_list("--help", "ghost/path\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Usage:", done.stdout)

    def test_sync_check_only_is_not_blocked_by_a_bad_list(self) -> None:
        done = self.sync_with_list("--check-only", "ghost/path\n")
        self.assertNotIn("missing from the checkout", done.stderr)

    def test_sync_staging_is_stopped_by_a_bad_list(self) -> None:
        done = self.sync_with_list("--stage-only", "ghost/path\n")
        self.assertEqual(done.returncode, 1)
        self.assertIn("missing from the checkout: ghost/path", done.stderr)

    def sync_with_list(self, flag: str, listing: str) -> subprocess.CompletedProcess:
        """sync_hart_package.sh copied beside a bad list in a scratch tree (it stops at the check or at --help)."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "tools").mkdir()
        for name in ("hartlib", "env"):
            (tmp / "tools" / name).symlink_to(ROOT / "tools" / name)
        hosts = tmp / "tools/hosts"
        hosts.mkdir()
        for f in ("sync_hart_package.sh", "live_paths.py", "profile_tables_guard.sh"):
            shutil.copy(ROOT / "tools/hosts" / f, hosts / f)
        shutil.copytree(STEPS, hosts / "deploy")
        (hosts / "pi").mkdir()
        for f in ("jython_list.sh", "jython_scripts.txt"):   # the jython list the steps' shared file reads
            shutil.copy(ROOT / "tools/hosts/pi" / f, hosts / "pi" / f)
        (hosts / "live_paths.txt").write_text(listing, encoding="utf-8")
        args = [flag] + ([str(tmp / "stage")] if flag == "--stage-only" else [])
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_") and k != "PI_HOST"}
        env["HART_ENV_FILE"] = str(tmp / "none.env")
        return subprocess.run(["bash", str(hosts / "sync_hart_package.sh"), *args], env=env, cwd=tmp,
                              capture_output=True, text=True, timeout=60)

    def run_builder(self, *argv: str) -> set[str]:
        """Run a deploy builder; return the repo files it opened or imported (paths relative to the repo)."""
        code = (
            "import sys, os, runpy, json\n"
            "root = os.path.realpath(sys.argv[1]); seen = set()\n"
            "def hook(ev, a):\n"
            "    if ev == 'open' and isinstance(a[0], str): seen.add(os.path.realpath(a[0]))\n"
            "sys.addaudithook(hook)\n"
            "script = sys.argv[2]; sys.argv = sys.argv[2:]\n"
            "try: runpy.run_path(script, run_name='__main__')\n"
            "except SystemExit as e:\n"
            "    if e.code not in (None, 0): raise\n"
            "seen |= {os.path.realpath(m.__file__) for m in sys.modules.values() if getattr(m, '__file__', None)}\n"
            "print(json.dumps(sorted(p[len(root) + 1:] for p in seen if p.startswith(root + os.sep))))\n")
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out)
        env = {k: v for k, v in os.environ.items() if k != "HART_TABLES"}
        done = subprocess.run([sys.executable, "-c", code, str(ROOT), *[a.replace("OUT", str(out)) for a in argv]],
                              capture_output=True, text=True, env=env, cwd=ROOT, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        # the check.sh hooks (the stamps' trace, the audit) load in every Python there: they are no builder input
        hooks = ("tools/audit/traced.py", "tools/audit/traced_read.py", "tools/audit/hook_chain.py",
                 "tools/audit/trace_hook/", "tools/audit/stamp_audit/")
        return {p for p in json.loads(done.stdout.strip().splitlines()[-1]) if not p.startswith(hooks)}

    def assert_inputs_listed(self, files: set[str]) -> None:
        listed = live_paths.read_list()
        own = {f for f in files if not f.endswith(".pyc") and "__pycache__" not in f}
        self.assertGreater(len(own), 5, own)
        unlisted = sorted(f for f in own if not any(f == p or f.startswith(p + "/") for p in listed))
        self.assertEqual(unlisted, [], "a deploy builder reads these but live_paths.txt does not cover them")

    def test_mimic_builder_inputs_are_listed(self) -> None:
        files = self.run_builder("tools/mqtt-mimic/build_mimic_web.py", "--out", "OUT")
        self.assertIn("jmri/layouts/hart/output/signal_head_plan.csv", files)
        # lcos_mqtt_mimic.py's parts: load_layout's module imports them, so a change to one is a deploy input
        for part in ("mimic_records.py", "mimic_bus.py", "mimic_http.py"):
            self.assertIn(f"tools/mqtt-mimic/{part}", files)
        from hartlib import devices         # the CATS bindings read the device master (hartlib.occupancy_bindings)
        for master in (devices.MASTER, devices.FIELD):
            self.assertIn(master.relative_to(ROOT).as_posix(), files)
        self.assert_inputs_listed(files)

    def test_speedmatch_page_builder_inputs_are_listed(self) -> None:
        files = self.run_builder("jmri/layouts/hart/scripts/speedmatch/dashboard/publish_live.py",
                                 "--build-page", "OUT")
        self.assertIn("jmri/layouts/hart/scripts/speedmatch/dashboard/static/index.html", files)
        self.assert_inputs_listed(files)

    def test_deploy_script_paths_are_all_listed(self) -> None:
        """Every repo path stage_package and the jython lists name is under a live_paths.txt entry."""
        listed = live_paths.read_list()
        text = (COMMON[COMMON.index("JYTHON_STARTUP_SCRIPTS=("):COMMON.index("# ---- the stamp")] + MAC + JYTHON_LIST
                + STAGE[STAGE.index("stage_package() {"):STAGE.index("# stage_host_finish")])
        region = "\n".join(line for line in text.splitlines()
                           if not line.strip().startswith("#") and "local sm=" not in line)
        sm = "jmri/layouts/hart/scripts/speedmatch"
        region = region.replace('"$sm', f'"$ROOT/{sm}')
        tokens = set(re.findall(r"(?:\$ROOT/|\s)((?:jmri|cats|tools|docs)/[A-Za-z0-9_./-]+)", region))
        tokens |= {"cats/panels/" + p for p in re.findall(r"^\s+(HART_[A-Z]+\.xml)$", region, re.M)}
        # bare-name patterns (lamp_*.png) end at the folder; the regex stops at "*"
        found = {t.rstrip("/") for t in tokens if not t.endswith("/") or t.count("/") > 2}
        self.assertGreater(len(found), 25, found)
        self.assertIn("jmri/scripts/sml_beans.py", found)   # the jython list's rows are read
        unlisted = sorted(t for t in found
                          if not any(t == p or t.startswith(p + "/") for p in listed))
        self.assertEqual(unlisted, [], "named by the deploy steps (tools/hosts/deploy) but absent from tools/hosts/live_paths.txt")


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
        self.assertIn("None of the commits ahead changes a live artifact: nothing to deploy.", done.stdout)

    def test_ahead_with_live_change(self) -> None:
        commit_file(self.repo, "docs/note.md", "n2\n")
        commit_file(self.repo, "live/tables.xml", "v2\n")
        done = self.status(self.base)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Of them, 1 touch live artifacts; a deploy would ship:", done.stdout)
        self.assertIn("    live/tables.xml", done.stdout)
        self.assertNotIn("docs/note.md", done.stdout)

    def test_changes_cancel_out(self) -> None:
        commit_file(self.repo, "live/tables.xml", "v2\n")
        commit_file(self.repo, "live/tables.xml", "v1\n")
        done = self.status(self.base)
        self.assertIn("Of them, 2 touch live artifacts, but the changes cancel out: a deploy would ship nothing new.",
                      done.stdout)

    def test_host_has_live_changes_checkout_lacks(self) -> None:
        deployed = commit_file(self.repo, "live/tables.xml", "v2\n")
        git(self.repo, "reset", "-q", "--hard", self.base)
        done = self.status(deployed)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("0 commit(s) ahead and 1 behind", done.stdout)
        self.assertIn("a deploy from here would roll back:", done.stdout)
        self.assertIn("    live/tables.xml", done.stdout)

    def test_deployed_commit_on_another_branch(self) -> None:
        git(self.repo, "checkout", "-q", "-b", "side", self.base)
        side = commit_file(self.repo, "live/tables.xml", "side\n")
        git(self.repo, "checkout", "-q", "main")
        commit_file(self.repo, "live/folder/m.txt", "m\n")
        done = self.status(side)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("    live/folder/m.txt", done.stdout)
        self.assertIn("would roll back", done.stdout)

    def test_unknown_deployed_commit(self) -> None:
        done = self.status("0" * 40)
        self.assertIn("The deployed commit is not in this checkout", done.stdout)
        self.assertNotIn("live artifact", done.stdout)


if __name__ == "__main__":
    unittest.main()
