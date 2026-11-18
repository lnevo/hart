"""A Pi deploy stops when the owner changed Operations Pro files or stored tables.xml on the Pi.

unpulled_changes.sh runs here against a fake JMRI_UserFiles. The deploy and the redeploy are run
with an ssh stand-in that runs the piped script locally against that folder, so the check is
real while nothing reaches a host: a stop must come before any rsync, scp or Mac install.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_stage import stage_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CHECK = ROOT / "tools/hosts/pi/unpulled_changes.sh"
SYNC = ROOT / "tools/hosts/sync_hart_package.sh"
REDEPLOY = ROOT / "tools/hosts/redeploy_commit.sh"
APPLY = ROOT / "tools/hosts/pi/apply_hart_package_local.sh"
FILES = ("Operations.xml", "OperationsCarRoster.xml", "OperationsEngineRoster.xml",
         "OperationsLocationRoster.xml", "OperationsRouteRoster.xml", "OperationsTrainRoster.xml")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.uf = self.tmp / "uf"
        ops = self.uf / "operations"
        ops.mkdir(parents=True)
        for name in FILES:
            (ops / name).write_text(f"deployed {name}")
        (ops / ".deployed.sha256").write_text(sha(b"".join((ops / n).read_bytes() for n in FILES)) + "\n")
        (self.uf / "tables.xml").write_text("<layout-config/>")
        (self.uf / "cats").mkdir()
        (self.uf / "cats/deploy_stamp.txt").write_text(f"commit=abc\ntables_sha256={sha(b'<layout-config/>')}\n")

    def check(self) -> list[str]:
        done = subprocess.run(["bash", str(CHECK), str(self.uf)], capture_output=True, text=True, check=True)
        return done.stdout.split()

    def session(self) -> None:
        (self.uf / "operations/OperationsCarRoster.xml").write_text("moved cars")

    def store(self) -> None:
        (self.uf / "tables.xml").write_text("<layout-config><stored/></layout-config>")


class CheckTest(Fixture):
    def test_clean_after_a_deploy(self) -> None:
        self.assertEqual([], self.check())

    def test_ops_session_and_store_are_named(self) -> None:
        self.session()
        self.assertEqual(["ops"], self.check())
        self.store()
        self.assertEqual(["ops", "tables"], self.check())

    def test_missing_stamps_count_as_clean(self) -> None:
        self.session()
        self.store()
        (self.uf / "operations/.deployed.sha256").unlink()
        (self.uf / "cats/deploy_stamp.txt").unlink()
        self.assertEqual([], self.check())

    def test_a_pull_newer_than_the_deploy_counts(self) -> None:
        self.store()
        pulled = self.uf / ".tables_deployed.sha256"
        pulled.write_text(sha((self.uf / "tables.xml").read_bytes()) + "\n")
        stamp = self.uf / "cats/deploy_stamp.txt"
        os.utime(stamp, (time.time() - 60, time.time() - 60))
        self.assertEqual([], self.check())
        # A later deploy, a rollback too, names its own tables: the older pull no longer counts.
        os.utime(pulled, (time.time() - 120, time.time() - 120))
        self.assertEqual(["tables"], self.check())

    def test_pi_apply_drops_the_pull_stamp(self) -> None:
        src = APPLY.read_text(encoding="utf-8")
        mv = src.index('mv -f "$HART/tables.xml" "$UF/tables.xml"')
        self.assertIn('rm -f "$UF/.tables_deployed.sha256"', src[mv:mv + 300])


class DeployStopsTest(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.env = stage_env(self.tmp)
        self.env.update(HOME=str(self.tmp / "home"), HART_PI_USERFILES=str(self.uf))
        # ssh HOST "bash -s -- 'DIR'" runs here; any other ssh or scp is logged and fails.
        bin_dir = self.tmp / "bin"
        (bin_dir / "ssh").write_text(
            "#!/bin/bash\n"
            f'echo "ssh $*" >>"{self.tmp}/network.log"\n'
            'cmd="${@: -1}"\n'
            "if [[ \"$cmd\" == \"bash -s -- '\"*\"'\" ]]; then d=\"${cmd#bash -s -- \\'}\"; exec bash -s -- \"${d%\\'}\"; fi\n"
            "exit 99\n", encoding="utf-8")

    def calls(self) -> list[str]:
        log = self.tmp / "network.log"
        return log.read_text().splitlines() if log.exists() else []

    def deploy(self, *extra: str, discard: bool = False) -> subprocess.CompletedProcess:
        env = dict(self.env, **({"HART_DISCARD_PI_CHANGES": "1"} if discard else {}))
        return subprocess.run(["bash", str(SYNC), "--pi", *extra], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=600)

    def test_ops_session_stops_the_deploy_before_anything_is_sent(self) -> None:
        self.session()
        done = self.deploy()
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("make ops-pull", done.stderr)
        # Only the check, then the PanelPro restart check (a PanelPro quit for this deploy comes back).
        self.assertEqual(2, len(self.calls()), self.calls())
        self.assertTrue(self.calls()[0].endswith(f"bash -s -- '{self.uf}'"), self.calls())
        self.assertTrue(self.calls()[1].endswith(" bash -s"), self.calls())

    def test_store_stops_the_deploy(self) -> None:
        self.store()
        done = self.deploy()
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("make tables-pull-pi", done.stderr)
        self.assertNotIn("make ops-pull", done.stderr)

    def test_discard_skips_the_check(self) -> None:
        self.session()
        done = self.deploy(discard=True)
        self.assertNotIn("STOP: the Pi", done.stderr)
        self.assertFalse(any("bash -s -- " in c for c in self.calls()), self.calls())

    def test_dry_run_and_stage_only_do_not_check(self) -> None:
        self.session()
        self.deploy("--stage-only", str(self.tmp / "s"))
        self.assertEqual([], self.calls())
        done = self.deploy("--dry-run")
        self.assertNotIn("STOP: the Pi", done.stderr)
        self.assertFalse(any("bash -s -- " in c for c in self.calls()), self.calls())

    def test_check_only_stops_on_changes_and_passes_clean(self) -> None:
        done = self.deploy("--check-pi-only")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("nothing unpulled", done.stdout)
        self.session()
        self.assertEqual(1, self.deploy("--check-pi-only").returncode)

    def test_redeploy_stops_too(self) -> None:
        self.store()
        done = subprocess.run(["bash", str(REDEPLOY), "HEAD", "--allow-unmerged", "--pi"], cwd=ROOT,
                              env=self.env, capture_output=True, text=True, timeout=600)
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("make tables-pull-pi", done.stderr)
        self.assertNotIn("temporary worktree", done.stdout)


if __name__ == "__main__":
    unittest.main()
