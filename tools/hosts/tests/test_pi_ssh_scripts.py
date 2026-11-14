"""The speed-match and CS-105 shell helpers take the Pi host from load_env.sh (environment,
hart.env, default "pi"), not from a private default.

A stub `ssh` on PATH fails at once and the script says which host it tried, so nothing here
touches the network."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = {
    "drop_job": ROOT / "jmri/layouts/hart/scripts/speedmatch/drop_job.sh",
    "cs105_reboot": ROOT / "tools/ops/cs105_reboot.sh",
    "cs105_roster_sync": ROOT / "tools/ops/cs105_roster_sync.sh",
    "loco_roster_import": ROOT / "tools/ops/loco_roster_import.sh",
}
CLEAR = ("HART_PI_SSH", "PI_HOST", "HART_ENV_FILE", "HART_REPO_ROOT", "_hart_env_loaded")


def run(name: str, env: dict[str, str], file_text: str | None):
    """Run the script with a failing ssh stub; return its stderr."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = tmp / "bin"
        stub.mkdir()
        (stub / "ssh").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (stub / "ssh").chmod(0o755)
        (stub / "scp").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (stub / "scp").chmod(0o755)
        env_file = tmp / "hart.env"
        if file_text is not None:
            env_file.write_text(file_text, encoding="utf-8")
        job = tmp / "job.py"
        job.write_text("pass\n", encoding="utf-8")
        base = {k: v for k, v in os.environ.items() if k not in CLEAR}
        base.update(env, HART_ENV_FILE=str(env_file), PATH=f"{stub}:/usr/bin:/bin")
        args = [str(job)] if name == "drop_job" else []
        done = subprocess.run(["bash", str(SCRIPTS[name]), *args], env=base, capture_output=True,
                              text=True, cwd=tmp)
        return done.returncode, done.stderr


class PiHost(unittest.TestCase):
    def check(self, name: str) -> None:
        for env, file_text, want in (
            ({}, None, "running on pi (JMRI up?)"),
            ({"HART_PI_SSH": "envpi.example.invalid"}, "HART_PI_SSH=filepi.example.invalid\n",
             "running on envpi.example.invalid ("),
            ({}, "HART_PI_SSH=filepi.example.invalid\n", "running on filepi.example.invalid ("),
        ):
            rc, err = run(name, env, file_text)
            if name == "cs105_roster_sync" and "git submodule update --init" in err:
                self.skipTest("external/jmri-cs105-roster-sync is not checked out here")
            self.assertEqual(rc, 1, err)  # reached the stub ssh
            self.assertIn(want, err)

    def test_drop_job(self) -> None:
        self.check("drop_job")

    def test_cs105_reboot(self) -> None:
        self.check("cs105_reboot")

    def test_cs105_roster_sync(self) -> None:
        self.check("cs105_roster_sync")

    def test_loco_roster_import(self) -> None:
        self.check("loco_roster_import")


if __name__ == "__main__":
    unittest.main()
