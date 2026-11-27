"""tools/cats/fetch_cats_3.2.sh checks the zip against its pinned sha256 and its contents before it replaces the
install folder: run on local zips, with a stub curl for the download path, no network."""
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
# The files install_into_jmri.sh copies out of the release folder.
NEEDED = ("cats.jar", "cats.csh", "designer.jar", "designer.csh")


def _zip(path: Path, names: tuple[str, ...] = NEEDED, extra: str = "") -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name in names:
            z.writestr(name, f"{name}{extra}\n")
    return path


class FetchCats(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.zip = _zip(self.tmp / "release3.2.zip")
        self.text = SCRIPT.read_text(encoding="utf-8")
        pinned = re.findall(r'^SHA256="([0-9a-f]{64})"$', self.text, re.M)
        self.assertEqual(len(pinned), 1, 'fetch_cats_3.2.sh pins one SHA256="<64 hex>"')
        self.script = self.pinned_to(self.zip)
        self.dest = self.tmp / "release3.2"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.tmpdir = self.tmp / "t"
        self.tmpdir.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def pinned_to(self, zip_path: Path) -> Path:
        """A copy of the script pinned to `zip_path`, so both paths run without the real CATS zip."""
        digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        script = self.tmp / "fetch.sh"
        script.write_text(re.sub(r'^SHA256=".*"$', f'SHA256="{digest}"', self.text, flags=re.M), encoding="utf-8")
        return script

    def curl(self, body: str) -> None:
        stub = self.bin / "curl"
        stub.write_text("#!/bin/bash\n" + body + "\n", encoding="utf-8")
        stub.chmod(0o755)

    def run_with(self, zip_path: Path | None) -> subprocess.CompletedProcess[str]:
        env = {"PATH": f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin", "CATS_DEST": str(self.dest),
               "TMPDIR": str(self.tmpdir)}
        if zip_path is not None:
            env["CATS_ZIP"] = str(zip_path)
        return subprocess.run(["bash", str(self.script)], env=env, capture_output=True, text=True, timeout=30)

    def leftovers(self) -> list[str]:
        """Temporary files and folders the script made and did not remove."""
        return sorted([p.name for p in self.tmpdir.iterdir()] + [p.name for p in self.tmp.glob(".cats32.*")])

    def test_a_matching_zip_is_installed(self) -> None:
        done = self.run_with(self.zip)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), sorted(NEEDED))
        self.assertTrue((self.dest / "cats.csh").stat().st_mode & 0o100)
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.leftovers(), [])

    def test_an_earlier_release_is_replaced(self) -> None:
        self.dest.mkdir()
        (self.dest / "cats.jar").write_text("old", encoding="utf-8")
        (self.dest / "stale.txt").write_text("old", encoding="utf-8")
        done = self.run_with(self.zip)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((self.dest / "stale.txt").exists())
        self.assertEqual((self.dest / "cats.jar").read_text(encoding="utf-8"), "cats.jar\n")

    def test_a_zip_that_does_not_match_stops_and_names_both_hashes(self) -> None:
        other = _zip(self.tmp / "other.zip", extra=" changed")
        done = self.run_with(other)
        self.assertEqual(done.returncode, 1)
        self.assertIn("does not match the pinned CATS 3.2 zip", done.stderr)
        self.assertIn("expected sha256", done.stderr)
        self.assertIn(hashlib.sha256(other.read_bytes()).hexdigest(), done.stderr)
        self.assertFalse(self.dest.exists(), "a mismatch must install nothing")

    def test_a_zip_without_a_needed_file_installs_nothing(self) -> None:
        short = _zip(self.tmp / "short.zip", names=("cats.jar", "cats.csh", "designer.jar"))
        self.script = self.pinned_to(short)
        self.dest.mkdir()
        (self.dest / "cats.jar").write_text("old", encoding="utf-8")
        done = self.run_with(short)
        self.assertEqual(done.returncode, 1)
        self.assertIn("has no designer.csh; nothing installed", done.stderr)
        self.assertEqual((self.dest / "cats.jar").read_text(encoding="utf-8"), "old")
        self.assertEqual(self.leftovers(), [])

    def test_a_folder_that_is_not_a_cats_release_is_not_replaced(self) -> None:
        self.dest.mkdir()
        (self.dest / "notes.txt").write_text("mine", encoding="utf-8")
        done = self.run_with(self.zip)
        self.assertEqual(done.returncode, 1)
        self.assertIn("holds no cats.jar; not replacing it", done.stderr)
        self.assertEqual([p.name for p in self.dest.iterdir()], ["notes.txt"])

    def test_the_download_is_checked_and_removed(self) -> None:
        self.curl(f'while [[ $# -gt 0 ]]; do [[ $1 == -o ]] && cp "{self.zip}" "$2"; shift; done; exit 0')
        done = self.run_with(None)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Fetching https://", done.stdout)
        self.assertTrue((self.dest / "cats.jar").is_file())
        self.assertEqual(self.leftovers(), [])

    def test_a_failed_download_installs_nothing_and_leaves_no_file(self) -> None:
        self.curl("echo 'curl: (6) Could not resolve host' >&2; exit 6")
        done = self.run_with(None)
        self.assertEqual(done.returncode, 6)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.leftovers(), [])


if __name__ == "__main__":
    unittest.main()
