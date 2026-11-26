"""redeploy_commit.sh in --stage-only mode, with fake hosts and no ssh.

A redeploy of HEAD must stage the same package a normal --stage-only of HEAD does; only
the stamp differs. The refusals (unknown, unmerged or too old a commit, an
unpulled PanelPro Store, no host named) must stop before any worktree is made or any host
is reached. HEAD is usually this branch's unmerged commit, hence --allow-unmerged.
"""
from __future__ import annotations

import filecmp
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_stage import read_stamp, stage_env, tree  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
REDEPLOY = ROOT / "tools/hosts/redeploy_commit.sh"
SYNC_REL = "tools/hosts/sync_hart_package.sh"
# Taken per run, or naming how the package was built rather than what is in it.
STAMP_RUN_KEYS = {"date", "branch", "dirty", "dirty_paths", "source", "redeploy_from", "deployed_from"}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=check)


def has_commit(ref: str) -> bool:
    return git("cat-file", "-e", f"{ref}^{{commit}}", check=False).returncode == 0


def own_tmpdir(env: dict[str, str], tmp: Path) -> Path:
    """Point the redeploy's temporary worktrees at this test's own folder (TMPDIR), so other sessions'
    hart-redeploy.* worktrees in the shared worktree list are never counted as this run's."""
    folder = tmp / "tmpdir"
    folder.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(folder)
    return folder


def redeploy_trees(under: Path) -> list[str]:
    """The hart-redeploy.* worktrees still registered under `under` (this test's TMPDIR)."""
    roots = {under, under.resolve()}
    return [line for line in git("worktree", "list", "--porcelain").stdout.splitlines()
            if line.startswith("worktree ") and "hart-redeploy." in line
            and any(Path(line[len("worktree "):]).is_relative_to(r) for r in roots)]


def run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(REDEPLOY), *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=600)


def differing(a: Path, b: Path) -> list[str]:
    def walk(d: filecmp.dircmp, prefix: str = "") -> list[str]:
        found = [prefix + n for n in d.diff_files + d.left_only + d.right_only + d.funny_files]
        for name, sub in d.subdirs.items():
            found += walk(sub, f"{prefix}{name}/")
        return found
    return walk(filecmp.dircmp(a, b))


class RedeployHead(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp())
        cls.head = git("rev-parse", "HEAD").stdout.strip()
        env = stage_env(cls.tmp)
        cls.network_log = cls.tmp / "network.log"
        # A root exported by the caller's shell must not point the old worktree's tools here.
        redeploy_env = dict(env, HART_REPO_ROOT=str(cls.tmp / "not-the-repo"))
        cls.tmpdir = own_tmpdir(redeploy_env, cls.tmp)
        cls.done = run(redeploy_env, "HEAD", "--allow-unmerged", "--stage-only", str(cls.tmp / "redeploy"))
        # The normal stage of HEAD: this checkout if it is clean, else a clean copy of HEAD.
        src = ROOT
        normal_env = env
        if git("status", "--porcelain").stdout.strip():
            src = cls.tmp / "head"
            git("worktree", "add", "-q", "--detach", str(src), "HEAD")
            # The copy has no submodule checked out: hand it this checkout's plugin, as redeploy_commit.sh does.
            plugin = Path(env.get("SCHEMATIC_PLUGIN") or ROOT / "external/model-railroad-skills/plugins/schematic-maps")
            if not (plugin / "schematic" / "slots.py").is_file():
                raise unittest.SkipTest("the schematic-maps plugin is not checked out: "
                                        "git submodule update --init external/model-railroad-skills")
            normal_env = dict(env, SCHEMATIC_PLUGIN=str(plugin))
        try:
            cls.normal = subprocess.run(["bash", str(src / SYNC_REL), "--stage-only", str(cls.tmp / "normal")],
                                        cwd=src, env=normal_env, capture_output=True, text=True, timeout=600)
        finally:
            if src != ROOT:
                git("worktree", "remove", "--force", str(src), check=False)

    @classmethod
    def tearDownClass(cls) -> None:
        for line in redeploy_trees(cls.tmpdir):      # a run killed before its trap: unregister what it left
            git("worktree", "remove", "--force", line[len("worktree "):], check=False)
        shutil.rmtree(cls.tmp, ignore_errors=True)
        git("worktree", "prune", check=False)

    def test_runs_without_the_network(self) -> None:
        self.assertEqual(self.done.returncode, 0, self.done.stderr[-3000:])
        self.assertEqual(self.normal.returncode, 0, self.normal.stderr[-3000:])
        self.assertIn("DONE (stage only)", self.done.stdout)
        made = re.search(r"temporary worktree (\S+)", self.done.stdout)
        self.assertIsNotNone(made, "the redeploy did not name its temporary worktree")
        self.assertTrue(Path(made.group(1)).resolve().is_relative_to(self.tmpdir.resolve()),
                        "the redeploy did not make its worktree under TMPDIR, so the leak check cannot see it")
        self.assertFalse(self.network_log.exists(), "a stage-only redeploy called ssh or scp")

    def test_same_package_as_a_normal_stage(self) -> None:
        for host in ("pi", "win"):
            got, want = self.tmp / "redeploy" / host, self.tmp / "normal" / host
            self.assertEqual(tree(got), tree(want), host)
            self.assertEqual(differing(got, want), ["cats/deploy_stamp.txt"], host)

    def test_stamp_names_the_redeploy(self) -> None:
        marks = "redeploy_from=" in git("show", f"HEAD:{SYNC_REL}").stdout
        for host in ("pi", "win"):
            got = read_stamp(self.tmp / "redeploy" / host / "cats/deploy_stamp.txt")
            want = read_stamp(self.tmp / "normal" / host / "cats/deploy_stamp.txt")
            self.assertEqual(got["commit"], self.head)
            self.assertEqual(got["branch"], "HEAD", "a detached worktree, no branch of its own")
            self.assertEqual(got["dirty"], "no")
            if marks:
                self.assertEqual(got["source"], "redeploy")
                self.assertEqual(got["redeploy_from"], self.head)
            self.assertEqual({k: v for k, v in got.items() if k not in STAMP_RUN_KEYS},
                             {k: v for k, v in want.items() if k not in STAMP_RUN_KEYS}, host)

    def test_worktree_is_removed(self) -> None:
        self.assertEqual(redeploy_trees(self.tmpdir), [])
        self.assertEqual(git("branch", "--list", "redeploy/*").stdout.strip(), "")


def has_stamp(commit: str) -> bool:
    """Whether the commit's deploy writes the stamp: in the entry point (older commits) or in deploy/common.sh."""
    return any("write_deploy_stamp" in git("show", f"{commit}:{rel}", check=False).stdout
               for rel in (SYNC_REL, "tools/hosts/deploy/common.sh"))


class Refusals(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = stage_env(self.tmp)
        self.env.update(HOME=str(self.tmp / "home"))
        self.tmpdir = own_tmpdir(self.env, self.tmp)

    def assert_refused(self, done: subprocess.CompletedProcess, text: str) -> None:
        self.assertNotEqual(done.returncode, 0)
        self.assertIn(text, done.stderr)
        self.assertFalse((self.tmp / "network.log").exists(), "a refusal reached for the network")
        self.assertEqual(redeploy_trees(self.tmpdir), [])
        self.assertEqual(list(self.tmpdir.iterdir()), [], "a refusal made a temporary folder (so it got past the checks)")

    def test_unknown_commit(self) -> None:
        self.assert_refused(run(self.env, "0" * 40, "--stage-only", str(self.tmp / "s")), "is not a commit")

    def test_unmerged_commit(self) -> None:
        main = git("rev-parse", "--verify", "--quiet", "origin/main", check=False)
        if main.returncode != 0:
            done = run(self.env, "HEAD", "--stage-only", str(self.tmp / "s"))
            self.assert_refused(done, "git fetch first")
            return
        if git("merge-base", "--is-ancestor", "HEAD", "origin/main", check=False).returncode == 0:
            self.skipTest("HEAD is already on origin/main")
        self.assert_refused(run(self.env, "HEAD", "--stage-only", str(self.tmp / "s")), "is not on origin/main")

    def test_mac_dry_run_alone_is_refused(self) -> None:
        done = run(self.env, "HEAD", "--allow-unmerged", "--mac", "--dry-run")
        self.assertEqual(done.returncode, 2)
        self.assertIn("no dry run for the Mac", done.stderr)

    def test_needs_hosts(self) -> None:
        done = run(self.env, "HEAD")
        self.assertEqual(done.returncode, 2)
        self.assertIn("Name the hosts", done.stderr)

    def test_one_commit_only(self) -> None:
        self.assert_refused(run(self.env, "HEAD", "HEAD~0", "--pi"), "One commit only")

    def first_with_script(self) -> str | None:
        found = git("log", "--diff-filter=A", "--format=%H", "--", SYNC_REL, check=False).stdout.split()
        return found[-1] if found else None

    def test_commit_before_the_move(self) -> None:
        first = self.first_with_script()
        if not first or not has_commit(f"{first}^"):
            self.skipTest("history before the ADR-007 move is not in this clone")
        self.assert_refused(run(self.env, f"{first}^", "--allow-unmerged", "--stage-only", str(self.tmp / "s")),
                            "predates the deploy's move to tools/hosts/")

    def test_the_stamp_is_found_in_either_file(self) -> None:
        """redeploy_commit.sh accepts write_deploy_stamp in the entry point (older commits) or in deploy/common.sh
        (since the split into steps); a commit with neither is refused (test_commit_before_the_stamp)."""
        self.assertIn("write_deploy_stamp", git("show", "HEAD:tools/hosts/deploy/common.sh").stdout)
        self.assertNotIn("write_deploy_stamp", git("show", f"HEAD:{SYNC_REL}").stdout)
        script = (ROOT / "tools/hosts/redeploy_commit.sh").read_text(encoding="utf-8")
        self.assertIn('"$SHA:$SYNC_REL"', script)
        self.assertIn('"$SHA:tools/hosts/deploy/common.sh"', script)

    def test_commit_before_the_stamp(self) -> None:
        first = self.first_with_script()
        if not first or has_stamp(first):
            self.skipTest("no commit with the script but without the stamp in this clone")
        self.assert_refused(run(self.env, first, "--allow-unmerged", "--stage-only", str(self.tmp / "s")),
                            "predates the deploy stamp")

    def test_unpulled_store_stops_a_real_redeploy(self) -> None:
        uf = self.tmp / "home/JMRI_UserFiles"
        uf.mkdir(parents=True)
        (uf / "tables.xml").write_text("<stored-by-panelpro/>\n", encoding="utf-8")
        (uf / ".tables_deployed.sha256").write_text("0" * 64 + "\n", encoding="utf-8")
        self.assert_refused(run(self.env, "HEAD", "--allow-unmerged", "--pi"), "Run make tables-pull")
        self.assertEqual((uf / "tables.xml").read_text(encoding="utf-8"), "<stored-by-panelpro/>\n")

    def test_full_stage_folder_is_refused_and_cleaned_up(self) -> None:
        out = self.tmp / "s"
        out.mkdir()
        (out / "keep.txt").write_text("x", encoding="utf-8")
        self.assert_refused(run(self.env, "HEAD", "--allow-unmerged", "--stage-only", str(out)), "is not empty")
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["keep.txt"])


class Source(unittest.TestCase):
    def test_ops_guards_stay_on_unless_asked(self) -> None:
        source = REDEPLOY.read_text(encoding="utf-8")
        self.assertIn('HART_OVERWRITE_OPS="${HART_OVERWRITE_OPS:-0}"', source)

    def test_store_test_is_shared_with_the_deploy(self) -> None:
        for path in (REDEPLOY, ROOT / "tools/hosts/deploy/common.sh"):   # common.sh: the steps' shared file
            text = path.read_text(encoding="utf-8")
            self.assertIn("profile_tables_guard.sh", text, path.name)
            self.assertIn("profile_tables_unpulled", text, path.name)
            self.assertNotIn(".tables_deployed.sha256)", text, path.name)

    def test_old_commit_gets_a_clean_environment(self) -> None:
        self.assertIn('env -i "${CHILD_ENV[@]}"', REDEPLOY.read_text(encoding="utf-8"))

    def test_make_target(self) -> None:
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("tools/hosts/redeploy_commit.sh $(COMMIT) $(HOSTS)", text)


if __name__ == "__main__":
    unittest.main()
