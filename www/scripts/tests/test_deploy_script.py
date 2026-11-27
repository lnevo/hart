"""deploy_hartrailroad.sh guards (ADR-040), run in a throwaway repo whose build step is a stub that exits 7.

Exit 7 means the guards let the deploy through to the build; exit 1 means a guard stopped it. gh, ssh and rsync are
stand-ins on PATH that log each call: gh answers the check.yml runs list from runs.json (the main red check,
tools/hosts/deploy/ci_pass.py --main-red, copied into the repo) and fails every other call, so nothing reaches GitHub
or the web server."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "deploy_hartrailroad.sh"
CI_PASS = Path(__file__).resolve().parents[3] / "tools/hosts/deploy/ci_pass.py"
URL = "https://github.com/owner/repo/actions/runs/999"
NOT_BLOCKING = "not blocking (owner ruling 2026-11-27)"


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
        (scripts / "prepare_github_pages.py").write_text(
            f"import sys\nopen({str(self.tmp / 'built')!r}, 'w').close()\nsys.exit(7)\n")
        (self.repo / "tools/hosts/deploy").mkdir(parents=True)
        shutil.copy(CI_PASS, self.repo / "tools/hosts/deploy/ci_pass.py")
        (self.repo / "ops" / "hart-ops" / "operator_logos").mkdir(parents=True)
        (self.repo / "www" / "index.html").write_text("a\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "one")
        _git(self.repo, "remote", "add", "origin", str(origin))
        _git(self.repo, "push", "-q", "origin", "main")
        self.sha = _git(self.repo, "rev-parse", "HEAD")
        self.lock = Path(_git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "hart-site-deploy.lock"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name in ("ssh", "rsync"):
            tool = self.bin / name
            tool.write_text(f'#!/bin/sh\necho "{name} $*" >>"{self.tmp}/network.log"\nexit 99\n')
            tool.chmod(0o755)
        gh = self.bin / "gh"
        gh.write_text(f"""#!/bin/bash
echo "gh $*" >>"{self.tmp}/gh.log"
for a in "$@"; do
  if [[ "$a" == repos/owner/repo/actions/workflows/check.yml/runs && -f "{self.tmp}/runs.json" ]]; then
    cat "{self.tmp}/runs.json"; exit 0
  fi
done
echo "HTTP 401: Bad credentials (stand-in)" >&2
exit 1
""")
        gh.chmod(0o755)

    def deploy(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "HART_WEB_HOST": "nowhere.invalid", "HART_WEB_DOCROOT": "/nowhere/",  # skips the openrsync check; rsync is never reached
               "HART_CI_REPO": "owner/repo", "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"}
        return subprocess.run(["bash", str(self.repo / "www" / "scripts" / SCRIPT.name), *args],
                              capture_output=True, text=True, env=env)

    def main_run(self, status: str = "completed", conclusion: str | None = "success") -> None:
        run = {"id": 999, "run_number": 9, "head_sha": self.sha, "head_branch": "main", "event": "push",
               "path": ".github/workflows/check.yml", "status": status, "conclusion": conclusion, "html_url": URL}
        (self.tmp / "runs.json").write_text(json.dumps({"total_count": 1, "workflow_runs": [run]}))

    def network(self) -> list[str]:
        log = self.tmp / "network.log"
        return log.read_text().splitlines() if log.exists() else []

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

    # ---- main red (ci_pass.py --main-red) ----

    def test_a_red_main_stops_before_the_build_and_any_upload(self):
        for conclusion in ("failure", "cancelled", "timed_out"):
            with self.subTest(conclusion=conclusion):
                self.main_run(conclusion=conclusion)
                done = self.deploy()
                self.assertEqual(done.returncode, 1, done.stderr)
                self.assertIn(f"STOP: main is red: the push run of .github/workflows/check.yml on main for "
                              f"{self.sha[:12]} ended {conclusion} ({URL}). Fix forward or revert first", done.stderr)
                self.assertFalse((self.tmp / "built").exists(), "the site was built after a red main")
                self.assertEqual([], self.network())
                self.assertFalse(self.lock.exists())

    def test_a_green_main_goes_on_to_the_build(self):
        self.main_run()
        done = self.deploy()
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertIn(f"main red check: main's push run for {self.sha[:12]} passed ({URL})", done.stdout)
        self.assertEqual([], self.network())

    def test_no_run_yet_does_not_block(self):
        (self.tmp / "runs.json").write_text(json.dumps({"total_count": 0, "workflow_runs": []}))
        done = self.deploy()
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertIn(f"main red check: no push run of check.yml on main for {self.sha[:12]} yet; {NOT_BLOCKING}",
                      done.stdout)

    def test_a_run_still_going_does_not_block(self):
        self.main_run(status="in_progress", conclusion=None)
        done = self.deploy()
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertIn(f"is in_progress ({URL}); not waiting for it, {NOT_BLOCKING}", done.stdout)

    def test_a_gh_error_does_not_block_and_is_named(self):
        done = self.deploy()   # no runs.json: gh fails as a logged-out gh does
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertIn("main red check: could not ask GitHub (gh api -X failed (exit 1): HTTP 401: Bad credentials "
                      f"(stand-in)); {NOT_BLOCKING}", done.stdout)
        self.assertIn("gh api -X GET repos/owner/repo/actions/workflows/check.yml/runs", (self.tmp / "gh.log").read_text())


if __name__ == "__main__":
    unittest.main()
