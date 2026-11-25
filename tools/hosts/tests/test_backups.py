"""backup_pi_pull.sh and backup_win_push.sh, run against local folders (no host is reached): dated snapshots that
share unchanged files, retention, a stopped run never counted, replaced files kept, a missing folder reported and
the last-ok stamps written only after a full run (ADR-035)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PULL = ROOT / "tools/hosts/backup_pi_pull.sh"
PUSH = ROOT / "tools/hosts/backup_win_push.sh"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.backups = self.tmp / "Backups"

    def run_script(self, script: Path, **env: str) -> subprocess.CompletedProcess:
        full = dict(os.environ, HART_BACKUP_DIR=str(self.backups), HART_ENV_FILE=str(self.tmp / "none.env"), **env)
        full.pop("_hart_env_loaded", None)
        return subprocess.run(["bash", str(script)], cwd=ROOT, env=full, capture_output=True, text=True, timeout=120)


class PiPull(Base):
    def setUp(self) -> None:
        super().setUp()
        self.home = self.tmp / "pi"
        write(self.home / ".jmri/profile/prefs.xml", "prefs")
        write(self.home / "JMRI_UserFiles/roster/roster.xml", "roster")
        write(self.home / "speedmatch/ledger.csv", "ledger")
        for folder in ("Desktop", ".java", ".local/share/applications", "jmrihelp"):
            write(self.home / folder / "f", folder)

    def pull(self, **env: str) -> subprocess.CompletedProcess:
        return self.run_script(PULL, BACKUP_PI_HOST="", BACKUP_PI_SKIP_STS="1",
                               HART_PI_USERFILES=str(self.home / "JMRI_UserFiles"), **env)

    def snapshots(self) -> list[Path]:
        return sorted(p for p in (self.backups / "pi").iterdir() if p.is_dir())

    def test_a_snapshot_holds_all_three_folders_and_stamps_last_ok(self) -> None:
        r = self.pull()
        self.assertEqual(r.returncode, 0, r.stderr)
        [snap] = self.snapshots()
        self.assertEqual((snap / "jmri/profile/prefs.xml").read_text(), "prefs")
        self.assertEqual((snap / "JMRI_UserFiles/roster/roster.xml").read_text(), "roster")
        self.assertEqual((snap / "speedmatch/ledger.csv").read_text(), "ledger")
        for folder, name in ((".java", "java"), (".local/share/applications", "applications"), ("Desktop", "Desktop")):
            self.assertEqual((snap / name / "f").read_text(), folder)
        self.assertTrue((self.backups / "pi/last-ok").exists())

    def test_an_unchanged_file_is_a_hard_link_to_the_last_snapshot(self) -> None:
        self.assertEqual(self.pull().returncode, 0)
        write(self.home / "speedmatch/ledger.csv", "ledger 2")
        os.utime(self.home / "speedmatch/ledger.csv", (1, 1))  # a different time as well as content
        r = self.pull()
        self.assertEqual(r.returncode, 0, r.stderr)
        first, second = self.snapshots()  # two runs in one second still make two snapshots
        self.assertEqual((first / "jmri/profile/prefs.xml").stat().st_ino,
                         (second / "jmri/profile/prefs.xml").stat().st_ino)
        self.assertEqual((first / "speedmatch/ledger.csv").read_text(), "ledger")
        self.assertEqual((second / "speedmatch/ledger.csv").read_text(), "ledger 2")

    def test_only_the_newest_keep_snapshots_stay(self) -> None:
        for _ in range(3):  # within one second too: each run gets its own name
            self.assertEqual(self.pull(BACKUP_PI_KEEP="2").returncode, 0)
        self.assertEqual(len(self.snapshots()), 2)

    def test_a_missing_folder_fails_leaves_no_snapshot_and_no_last_ok(self) -> None:
        shutil.rmtree(self.home / "speedmatch")
        r = self.pull()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual([p.name for p in self.snapshots() if not p.name.endswith(".part")], [])
        self.assertFalse((self.backups / "pi/last-ok").exists())
        # the stopped run's .part folder is removed by the next run and never linked to
        write(self.home / "speedmatch/ledger.csv", "ledger")
        self.assertEqual(self.pull().returncode, 0)
        self.assertEqual([p.name.endswith(".part") for p in self.snapshots()], [False])

    def test_a_bad_keep_is_refused(self) -> None:
        r = self.pull(BACKUP_PI_KEEP="0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("BACKUP_PI_KEEP", r.stderr)


class WinPush(Base):
    def setUp(self) -> None:
        super().setUp()
        self.a = self.tmp / "mac/media"
        self.b = self.tmp / "mac/NMRA AP"  # a space in the name
        write(self.a / "photo.jpg", "one")
        write(self.b / "form.pdf", "form")
        self.target = self.tmp / "win"

    def push(self, *folders: Path, **env: str) -> subprocess.CompletedProcess:
        lines = "\n".join(f"{p.name}|{p}" for p in (folders or (self.a, self.b)))
        return self.run_script(PUSH, BACKUP_WIN_HOST="", BACKUP_WIN_DIR=str(self.target), BACKUP_WIN_FOLDERS=lines,
                               **env)

    def test_folders_are_mirrored_and_last_ok_is_stamped(self) -> None:
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.target / "media/photo.jpg").read_text(), "one")
        self.assertEqual((self.target / "NMRA AP/form.pdf").read_text(), "form")
        self.assertTrue((self.backups / "win-last-ok").exists())

    def test_a_changed_or_deleted_file_is_kept_under_replaced(self) -> None:
        self.assertEqual(self.push().returncode, 0)
        write(self.a / "photo.jpg", "two!")
        (self.b / "form.pdf").unlink()
        r = self.push()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.target / "media/photo.jpg").read_text(), "two!")
        self.assertFalse((self.target / "NMRA AP/form.pdf").exists())
        kept = {p.relative_to(self.target / "replaced").parts[1:] : p.read_text()
                for p in (self.target / "replaced").rglob("*") if p.is_file()}
        self.assertEqual(kept, {("media", "photo.jpg"): "one", ("NMRA AP", "form.pdf"): "form"})

    def test_a_missing_folder_is_reported_the_rest_copied_and_last_ok_not_stamped(self) -> None:
        r = self.push(self.tmp / "mac/gone", self.a)
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISSING", r.stderr)
        self.assertTrue((self.target / "media/photo.jpg").exists())
        self.assertFalse((self.target / "gone").exists())
        self.assertFalse((self.backups / "win-last-ok").exists())

    def test_a_relative_target_is_refused(self) -> None:
        r = self.run_script(PUSH, BACKUP_WIN_HOST="", BACKUP_WIN_DIR="backups/mac", BACKUP_WIN_FOLDERS=f"m|{self.a}")
        self.assertEqual(r.returncode, 2)
        self.assertIn("absolute", r.stderr)


if __name__ == "__main__":
    unittest.main()
