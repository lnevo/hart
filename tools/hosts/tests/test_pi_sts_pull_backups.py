"""pi_sts_pull_backups.sh keeps the newest STS_PI_KEEP_DUMPS dumps and refuses a count below 1.

Stub `ssh` and `rsync` on PATH stand in for the Pi; the dumps go to a temp folder."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/hosts/pi_sts_pull_backups.sh"
OLD_DUMPS = ("sts_db3_20200101-000000.sql.gz", "sts_db3_20200102-000000.sql.gz",
             "sts_db3_20200103-000000.sql.gz")


def run(tmp: Path, keep: str) -> subprocess.CompletedProcess[str]:
    """Run the script against stubs with STS_PI_KEEP_DUMPS=keep; dumps land in tmp/dest/db."""
    stub = tmp / "bin"
    stub.mkdir(exist_ok=True)
    (stub / "ssh").write_text("#!/bin/sh\nprintf 'CREATE TABLE t;\\n-- Dump completed\\n'\n",
                              encoding="utf-8")
    (stub / "rsync").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for name in ("ssh", "rsync"):
        (stub / name).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "_hart_env_loaded"}
    env.update(PATH=f"{stub}:/usr/bin:/bin", STS_PI_COPY=str(tmp / "dest"),
               STS_PI_KEEP_DUMPS=keep, HART_PI_SSH="pi.example.invalid",
               HART_ENV_FILE=str(tmp / "hart.env"))
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, cwd=tmp)


def seed(tmp: Path) -> Path:
    """Write three old dumps; return the db folder."""
    db = tmp / "dest/db"
    db.mkdir(parents=True)
    for name in OLD_DUMPS:
        (db / name).write_bytes(b"old")
    return db


class KeepDumps(unittest.TestCase):
    def test_prune_keeps_the_new_dump(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            db = seed(tmp)
            done = run(tmp, "2")
            self.assertEqual(done.returncode, 0, done.stderr)
            left = sorted(p.name for p in db.iterdir())
            self.assertEqual(len(left), 2, left)
            self.assertEqual(left[0], OLD_DUMPS[-1])
            self.assertNotIn(left[1], OLD_DUMPS)  # the dump this run wrote

    def test_empty_count_takes_the_default(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            db = seed(tmp)
            done = run(tmp, "")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(len(list(db.iterdir())), 4)

    def test_bad_counts_stop_before_any_copy(self) -> None:
        for keep in ("0", "00", "-1", "abc"):
            with self.subTest(keep=keep), tempfile.TemporaryDirectory() as t:
                tmp = Path(t)
                db = seed(tmp)
                done = run(tmp, keep)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn("STS_PI_KEEP_DUMPS must be a whole number above 0", done.stderr)
                self.assertEqual(sorted(p.name for p in db.iterdir()), list(OLD_DUMPS))
                self.assertFalse((tmp / "dest/backups").exists())


if __name__ == "__main__":
    unittest.main()
