"""tools/cats/fetch_cats_3.2.sh checks the zip against its pinned sha256 before installing: run on local zips, no network."""
from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/cats/fetch_cats_3.2.sh"


class FetchCats(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.zip = self.tmp / "release3.2.zip"
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr("cats.csh", "#!/bin/sh\n")
        digest = hashlib.sha256(self.zip.read_bytes()).hexdigest()
        text = SCRIPT.read_text(encoding="utf-8")
        self.pinned = re.search(r'^SHA256="([0-9a-f]{64})"$', text, re.M)
        # a copy of the script pinned to the test zip, so both paths run without the real CATS zip
        self.script = self.tmp / "fetch.sh"
        self.script.write_text(re.sub(r'^SHA256=".*"$', f'SHA256="{digest}"', text, flags=re.M), encoding="utf-8")
        self.dest = self.tmp / "release3.2"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_with(self, zip_path: Path) -> subprocess.CompletedProcess[str]:
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "CATS_ZIP": str(zip_path), "CATS_DEST": str(self.dest)}
        return subprocess.run(["bash", str(self.script)], env=env, capture_output=True, text=True, timeout=30)

    def test_the_script_pins_a_sha256(self) -> None:
        self.assertIsNotNone(self.pinned, "fetch_cats_3.2.sh has no SHA256=\"<64 hex>\" line")

    def test_a_matching_zip_is_installed(self) -> None:
        done = self.run_with(self.zip)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.dest / "cats.csh").is_file())

    def test_a_zip_that_does_not_match_stops_and_names_both_hashes(self) -> None:
        other = self.tmp / "other.zip"
        with zipfile.ZipFile(other, "w") as z:
            z.writestr("cats.csh", "#!/bin/sh\necho changed\n")
        done = self.run_with(other)
        self.assertEqual(done.returncode, 1)
        self.assertIn("does not match the pinned CATS 3.2 zip", done.stderr)
        self.assertIn("expected sha256", done.stderr)
        self.assertIn(hashlib.sha256(other.read_bytes()).hexdigest(), done.stderr)
        self.assertFalse(self.dest.exists(), "a mismatch must install nothing")


if __name__ == "__main__":
    unittest.main()
