"""deploy_hartrailroad.sh guards (ADR-040), run in a throwaway repo whose build step is a stub that exits 7.

Exit 7 means the guards let the deploy through to the build; exit 1 means a guard stopped it."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "deploy_hartrailroad.sh"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class DeployScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        origin, self.repo = self.tmp / "origin.git", self.tmp / "repo"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        for key, value in (("user.name", "t"), ("user.email", "t@example.invalid"), ("commit.gpgsign", "false")):
            _git(self.repo, "config", key, value)
        scripts = self.repo / "www" / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy(SCRIPT, scripts / SCRIPT.name)
        (scripts / "prepare_github_pages.py").write_text("import sys\nsys.exit(7)\n")
        (self.repo / "ops" / "hart-ops" / "operator_logos").mkdir(parents=True)
        (self.repo / "www" / "index.html").write_text("a\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "one")
        _git(self.repo, "remote", "add", "origin", str(origin))
        _git(self.repo, "push", "-q", "origin", "main")
        self.lock = Path(_git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "hart-site-deploy.lock"

    def deploy(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "HART_WEB_HOST": "nowhere.invalid"}  # skips the openrsync check; rsync is never reached
        return subprocess.run(["bash", str(self.repo / "www" / "scripts" / SCRIPT.name), *args],
                              capture_output=True, text=True, env=env)

    def push_from_elsewhere(self):
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", str(self.tmp / "origin.git"), str(other)], check=True)
        (other / "www" / "new.html").write_text("b\n")
        _git(other, "add", ".")
        _git(other, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "two")
        _git(other, "push", "-q", "origin", "main")

    def test_a_current_checkout_reaches_the_build_and_frees_the_lock(self):
        done = self.deploy()
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertFalse(self.lock.exists())

    def test_a_checkout_behind_origin_main_stops(self):
        self.push_from_elsewhere()
        done = self.deploy()
        self.assertEqual(done.returncode, 1)
        self.assertIn("HEAD lacks 1 commit(s) on origin/main, 1 of them under www/", done.stderr)
        self.assertFalse(self.lock.exists())

    def test_allow_behind_deploys_anyway(self):
        self.push_from_elsewhere()
        done = self.deploy("--allow-behind")
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertIn("deploying anyway", done.stderr)

    def test_a_running_deploy_holds_the_lock(self):
        self.lock.mkdir()
        (self.lock / "pid").write_text(f"{os.getpid()}\n")
        done = self.deploy()
        self.assertEqual(done.returncode, 1)
        self.assertIn("another site deploy is running", done.stderr)
        self.assertTrue(self.lock.exists())  # the other run's lock is left alone

    def test_a_stale_lock_is_taken_over(self):
        dead = subprocess.Popen(["true"])
        dead.wait()
        self.lock.mkdir()
        (self.lock / "pid").write_text(f"{dead.pid}\n")
        done = self.deploy()
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertIn("Took over a stale deploy lock", done.stderr)
        self.assertFalse(self.lock.exists())

    def test_status_prints_the_record(self):
        done = self.deploy("--status")
        self.assertEqual(done.returncode, 0)
        self.assertIn("No deploy record", done.stdout)


if __name__ == "__main__":
    unittest.main()
