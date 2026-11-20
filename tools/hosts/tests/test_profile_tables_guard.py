"""tools/hosts/profile_tables_guard.sh: profile_tables_unpulled (the Mac deploy's unpulled-Store guard) and
hart_pulled_dir (where taken Stores are kept, outside every checkout)."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / "tools/hosts/profile_tables_guard.sh"


def bash(script: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", f'source "{GUARD}"; {script}'], capture_output=True, text=True,
                          env={**os.environ, **(env or {})}, timeout=30)


class Unpulled(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src = self.tmp / "generated.xml"
        self.src.write_text("<generated/>")
        self.uf = self.tmp / "uf"
        self.uf.mkdir()

    def unpulled(self, **env: str) -> bool:
        return bash(f'profile_tables_unpulled "{self.src}" "{self.uf}"', env).returncode == 0

    def test_a_store_since_the_stamp_counts(self) -> None:
        (self.uf / "tables.xml").write_text("<deployed/>")
        (self.uf / ".tables_deployed.sha256").write_text(hashlib.sha256(b"<deployed/>").hexdigest() + "\n")
        self.assertFalse(self.unpulled())
        (self.uf / "tables.xml").write_text("<stored/>")
        self.assertTrue(self.unpulled())
        self.assertFalse(self.unpulled(HART_OVERWRITE_PROFILE_TABLES="1"))

    def test_with_no_stamp_a_file_unlike_the_generated_one_counts(self) -> None:
        (self.uf / "tables.xml").write_text("<stored/>")
        self.assertTrue(self.unpulled())
        (self.uf / "tables.xml").write_text("<generated/>")
        self.assertFalse(self.unpulled())

    def test_no_file_is_nothing_to_lose(self) -> None:
        self.assertFalse(self.unpulled())


class PulledDir(unittest.TestCase):
    def test_the_default_is_beside_the_user_files_and_made_on_demand(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            done = bash("hart_pulled_dir", {"HOME": home, "HART_PULLED_DIR": ""})
            self.assertEqual(0, done.returncode, done.stderr)
            want = Path(home).resolve() / "JMRI_UserFiles-pulled"
            self.assertEqual(want, Path(done.stdout.strip()).resolve())
            self.assertTrue(want.is_dir())

    def test_a_folder_inside_a_checkout_is_refused(self) -> None:
        inside = ROOT / "jmri/layouts/hart/output/pulled-test/kept"
        done = bash("hart_pulled_dir", {"HART_PULLED_DIR": str(inside)})
        self.assertEqual(1, done.returncode)
        self.assertIn("inside a git checkout", done.stderr)
        self.assertFalse(inside.parent.exists())          # refused before anything was made


if __name__ == "__main__":
    unittest.main()
