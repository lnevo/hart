"""make tables-pull and tables-pull-pi (tools/ops/pull_tables.sh, pull_tables_pi.sh) never copy a Store over the
generated tables.xml (ADR-029). A Store that differs from what was last deployed or pulled is kept in the gitignored
output/pulled/ and then recorded as taken on its host (.tables_deployed.sha256), so the next deploy is not stopped
by it and replaces the host's file with the generated one.

Each script runs from a copy in a temporary checkout, with a temporary HOME and, for the Pi, ssh and scp stand-ins
that run against a local folder and log every call: nothing reaches a host or the repo."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GENERATED = "<layout-config>\n  <sensors />\n</layout-config>\n"
STORE = "<layout-config>\n  <sensors />\n  <filehistory />\n</layout-config>\n"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class PullCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "checkout"
        for rel in ("tools/ops/pull_tables.sh", "tools/ops/pull_tables_pi.sh", "tools/env/load_env.sh",
                    "tools/env/defaults.env", "tools/hosts/pi/unpulled_changes.sh"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, self.root / rel)
        self.tables = self.root / "jmri/layouts/hart/output/tables.xml"
        self.tables.parent.mkdir(parents=True)
        self.tables.write_text(GENERATED, encoding="utf-8")
        self.home = self.tmp / "home"
        self.uf = self.home / "JMRI_UserFiles"
        self.uf.mkdir(parents=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.pi_uf = self.tmp / "pi/JMRI_UserFiles"
        self.pi_uf.mkdir(parents=True)
        # scp copies the Pi's local stand-in file; ssh runs its command here, as the Pi would
        (self.bin / "scp").write_text(f'#!/bin/bash\necho "scp $*" >>"{self.tmp}/network.log"\n'
                                      f'cp "{self.pi_uf}/tables.xml" "${{@: -1}}"\n', encoding="utf-8")
        (self.bin / "ssh").write_text(f'#!/bin/bash\necho "ssh $*" >>"{self.tmp}/network.log"\nshift\n'
                                      'exec bash -c "$*"\n', encoding="utf-8")
        for tool in ("scp", "ssh"):
            (self.bin / tool).chmod(0o755)

    def run_pull(self, script: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HART_", "_hart"))}
        env.update(HOME=str(self.home), PATH=f"{self.bin}{os.pathsep}{env['PATH']}",
                   HART_ENV_FILE=str(self.tmp / "none.env"), HART_PI_SSH="pi.example.invalid",
                   HART_PI_USERFILES=str(self.pi_uf))
        return subprocess.run(["bash", str(self.root / "tools/ops" / script)], env=env, cwd=self.tmp,
                              capture_output=True, text=True, timeout=60)

    def pulled(self) -> list[Path]:
        folder = self.root / "jmri/layouts/hart/output/pulled"
        return sorted(folder.iterdir()) if folder.exists() else []


class MacPull(PullCase):
    def test_a_store_is_kept_then_recorded_as_taken(self) -> None:
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        (self.uf / ".tables_deployed.sha256").write_text(sha(GENERATED) + "\n", encoding="utf-8")
        done = self.run_pull("pull_tables.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(GENERATED, self.tables.read_text(encoding="utf-8"))      # never replaced
        [saved] = self.pulled()
        self.assertTrue(saved.name.startswith("mac-") and saved.suffix == ".xml", saved)
        self.assertEqual(STORE, saved.read_text(encoding="utf-8"))
        self.assertEqual(sha(STORE), (self.uf / ".tables_deployed.sha256").read_text().strip())
        for words in ("recorded as taken", "devices.csv or the template", "R9d", "next deploy replaces"):
            self.assertIn(words, done.stdout)
        again = self.run_pull("pull_tables.sh")                                     # nothing left to take
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertIn("Nothing to pull", again.stdout)
        self.assertEqual(1, len(self.pulled()))

    def test_the_last_deployed_hash_decides_not_the_repo_file(self) -> None:
        """The profile holds what was last deployed, though the repo's generated file has moved on since: nothing
        to pull."""
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        (self.uf / ".tables_deployed.sha256").write_text(sha(STORE) + "\n", encoding="utf-8")
        done = self.run_pull("pull_tables.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing to pull", done.stdout)
        self.assertEqual([], self.pulled())


class PiPull(PullCase):
    def test_a_store_is_kept_then_recorded_as_taken_on_the_pi(self) -> None:
        (self.pi_uf / "tables.xml").write_text(STORE, encoding="utf-8")
        (self.pi_uf / ".tables_deployed.sha256").write_text(sha(GENERATED) + "\n", encoding="utf-8")
        done = self.run_pull("pull_tables_pi.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(GENERATED, self.tables.read_text(encoding="utf-8"))
        [saved] = self.pulled()
        self.assertTrue(saved.name.startswith("pi-"), saved)
        self.assertEqual(STORE, saved.read_text(encoding="utf-8"))
        self.assertEqual(sha(STORE), (self.pi_uf / ".tables_deployed.sha256").read_text().strip())
        self.assertIn("recorded as taken on the Pi", done.stdout)
        # the deploy's own check now finds nothing unpulled
        check = subprocess.run(["bash", str(ROOT / "tools/hosts/pi/unpulled_changes.sh"), str(self.pi_uf)],
                               capture_output=True, text=True)
        self.assertEqual("", check.stdout.strip())

    def test_nothing_unpulled_takes_nothing(self) -> None:
        (self.pi_uf / "tables.xml").write_text(STORE, encoding="utf-8")
        (self.pi_uf / ".tables_deployed.sha256").write_text(sha(STORE) + "\n", encoding="utf-8")
        done = self.run_pull("pull_tables_pi.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing to pull", done.stdout)
        self.assertEqual([], self.pulled())
        calls = (self.tmp / "network.log").read_text().splitlines()
        self.assertFalse([c for c in calls if c.startswith("scp ")], calls)


if __name__ == "__main__":
    unittest.main()
