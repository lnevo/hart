"""make tables-pull and tables-pull-pi (tools/ops/pull_tables.sh, pull_tables_pi.sh) never copy a Store over the
generated tables.xml (ADR-029): until R9d splits a Store into the sources, each keeps it in the gitignored
output/pulled/ and stops. The Pi pull leaves the Pi's deployed hash alone, so the deploy guard keeps blocking.

Each script runs from a copy in a temporary checkout, with a temporary HOME and, for the Pi, ssh and scp
stand-ins that serve a local file and log every call: nothing reaches a host or the repo."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GENERATED = "<layout-config>\n  <sensors />\n</layout-config>\n"
STORE = "<layout-config>\n  <sensors />\n  <filehistory />\n</layout-config>\n"


class PullCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "checkout"
        for rel in ("tools/ops/pull_tables.sh", "tools/ops/pull_tables_pi.sh", "tools/env/load_env.sh",
                    "tools/env/defaults.env"):
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
        (self.bin / "scp").write_text(f'#!/bin/bash\necho "scp $*" >>"{self.tmp}/network.log"\n'
                                      f'cp "{self.pi_uf}/tables.xml" "${{@: -1}}"\n', encoding="utf-8")
        (self.bin / "ssh").write_text(f'#!/bin/bash\necho "ssh $*" >>"{self.tmp}/network.log"\nexit 99\n',
                                      encoding="utf-8")
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
    def test_a_store_is_kept_and_the_pull_stops(self) -> None:
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        done = self.run_pull("pull_tables.sh")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertEqual(GENERATED, self.tables.read_text(encoding="utf-8"))      # never replaced
        [saved] = self.pulled()
        self.assertTrue(saved.name.startswith("mac-") and saved.suffix == ".xml", saved)
        self.assertEqual(STORE, saved.read_text(encoding="utf-8"))
        self.assertIn("R9d", done.stderr)
        self.assertIn("PanelPro edits are kept in that file", done.stderr)
        self.assertFalse((self.uf / ".tables_deployed.sha256").exists())            # still counts as unpulled

    def test_the_same_bytes_pass_and_keep_nothing(self) -> None:
        (self.uf / "tables.xml").write_text(GENERATED, encoding="utf-8")
        done = self.run_pull("pull_tables.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.pulled())


class PiPull(PullCase):
    def test_a_store_is_kept_and_the_deployed_hash_left_alone(self) -> None:
        (self.pi_uf / "tables.xml").write_text(STORE, encoding="utf-8")
        done = self.run_pull("pull_tables_pi.sh")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertEqual(GENERATED, self.tables.read_text(encoding="utf-8"))
        [saved] = self.pulled()
        self.assertTrue(saved.name.startswith("pi-"), saved)
        self.assertEqual(STORE, saved.read_text(encoding="utf-8"))
        self.assertIn("deployed hash is unchanged", done.stderr)
        calls = (self.tmp / "network.log").read_text().splitlines()
        self.assertFalse([c for c in calls if c.startswith("ssh ")], calls)          # no hash written on the Pi

    def test_the_same_bytes_pass_and_keep_nothing(self) -> None:
        (self.pi_uf / "tables.xml").write_text(GENERATED, encoding="utf-8")
        done = self.run_pull("pull_tables_pi.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.pulled())


if __name__ == "__main__":
    unittest.main()
