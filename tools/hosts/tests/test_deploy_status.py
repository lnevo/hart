"""deploy_status.sh reads the stamp back through a fake ssh: no network."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATUS = ROOT / "tools/hosts/deploy_status.sh"


def head() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


class DeployStatus(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / "bin").mkdir()
        self.calls = self.tmp / "calls.log"

    def fake_ssh(self, stamp: str | None) -> None:
        body = f'printf "%s\\n" "$*" >>"{self.calls}"\n'
        if stamp is None:
            body += "exit 1\n"
        else:
            (self.tmp / "stamp.txt").write_text(stamp, encoding="utf-8")
            body += f'cat "{self.tmp}/stamp.txt"\n'
        tool = self.tmp / "bin/ssh"
        tool.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        tool.chmod(0o755)

    def run_status(self, *flags: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_") and k != "PI_HOST"}
        env.update(PATH=f"{self.tmp / 'bin'}{os.pathsep}{env['PATH']}",
                   HART_ENV_FILE=str(self.tmp / "none.env"), HART_PI_SSH="pi.example.invalid",
                   HART_PI_USERFILES="/srv/pi/JMRI_UserFiles", HART_WIN_SSH="me@win.example.invalid",
                   HART_WIN_SSH_PORT="2299", HART_WIN_USERFILES="X:/w/JMRI_UserFiles", HOME=str(self.tmp))
        return subprocess.run(["bash", str(STATUS), *flags], env=env, capture_output=True, text=True,
                              timeout=30)

    def stamp(self, commit: str, dirty: str = "no", target: str = "pi") -> str:
        return (f"# Layout deploy stamp\ncommit={commit}\nbranch=main\ndirty={dirty}\ndirty_paths=0\n"
                f"date=2026-11-12T10:00:00-0500\ndeployed_from=mac\ntarget={target}\n")

    def test_pi_same_commit(self) -> None:
        self.fake_ssh(self.stamp(head()))
        done = self.run_status()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"commit={head()}", done.stdout)
        self.assertIn("Same commit as this checkout.", done.stdout)
        call = self.calls.read_text(encoding="utf-8")
        self.assertIn("pi.example.invalid", call)
        self.assertIn("/srv/pi/JMRI_UserFiles/cats/deploy_stamp.txt", call)

    def test_dirty_and_unknown_commit(self) -> None:
        self.fake_ssh(self.stamp("0" * 40, dirty="yes"))
        done = self.run_status("--pi")
        self.assertIn("WARNING: shipped from a checkout with uncommitted changes.", done.stdout)
        self.assertIn("not in this checkout", done.stdout)

    def test_tables_modified_warns(self) -> None:
        self.fake_ssh(self.stamp(head()) + "tables_modified_by_deploy=yes\n")
        done = self.run_status("--pi")
        self.assertIn("tables_modified_by_deploy=yes", done.stdout)
        self.assertIn("WARNING: the tables.xml shipped is not the committed one", done.stdout)

    def test_redeploy_is_named(self) -> None:
        self.fake_ssh(self.stamp(head()).replace("branch=main", "branch=redeploy/0123456789ab")
                      + "source=redeploy\nredeploy_from=" + head() + "\n")
        done = self.run_status("--pi")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("source=redeploy", done.stdout)
        self.assertIn("NOTE: a redeploy of an older commit", done.stdout)

    def test_plain_deploy_has_no_redeploy_note(self) -> None:
        self.fake_ssh(self.stamp(head()))
        self.assertNotIn("redeploy", self.run_status("--pi").stdout)

    def test_help_lists_all(self) -> None:
        done = self.run_status("--help")
        self.assertIn("--all", done.stdout)

    def test_windows_path_and_port(self) -> None:
        self.fake_ssh(self.stamp(head(), target="win"))
        done = self.run_status("--win")
        self.assertEqual(done.returncode, 0, done.stderr)
        call = self.calls.read_text(encoding="utf-8")
        self.assertIn("-p 2299 me@win.example.invalid", call)
        self.assertIn("X:\\w\\JMRI_UserFiles\\cats\\deploy_stamp.txt", call)

    def test_mac_reads_local_file(self) -> None:
        self.fake_ssh(None)
        cats = self.tmp / "JMRI_UserFiles/cats"
        cats.mkdir(parents=True)
        (cats / "deploy_stamp.txt").write_text(self.stamp(head(), target="mac"), encoding="utf-8")
        done = self.run_status("--mac")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("target=mac", done.stdout)
        self.assertFalse(self.calls.exists(), "--mac must not ssh")

    def test_missing_stamp_fails(self) -> None:
        self.fake_ssh(None)
        done = self.run_status("--pi")
        self.assertEqual(done.returncode, 1)
        self.assertIn("No deploy stamp", done.stdout)


if __name__ == "__main__":
    unittest.main()
