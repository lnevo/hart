"""tools/hosts/profile_tables_guard.sh: profile_tables_unpulled (the Mac deploy's unpulled-Store guard) and
hart_pulled_dir (where taken Stores are kept, in the main checkout's gitignored media/) and the main-checkout and cache helpers."""
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

    def test_a_store_split_into_the_checkout_is_taken(self) -> None:
        """R9d: a Store whose hash store_splits.csv (of the checkout the guard is in) names is in the sources, so
        installing the generated file over it loses nothing."""
        root = self.tmp / "checkout"
        guard = root / "tools/hosts/profile_tables_guard.sh"
        guard.parent.mkdir(parents=True)
        shutil.copy2(GUARD, guard)
        (self.uf / "tables.xml").write_text("<stored/>")
        (self.uf / ".tables_deployed.sha256").write_text(hashlib.sha256(b"<deployed/>").hexdigest() + "\n")

        def unpulled() -> bool:
            return subprocess.run(["bash", "-c", f'source "{guard}"; profile_tables_unpulled "{self.src}" "{self.uf}"'],
                                  capture_output=True, text=True, timeout=30).returncode == 0

        self.assertTrue(unpulled())
        splits = root / "jmri/layouts/hart/data/store_splits.csv"
        splits.parent.mkdir(parents=True)
        splits.write_text("store_sha256,host,store_file,base,plan,split_date\n"
                          f"{hashlib.sha256(b'<stored/>').hexdigest()},mac,mac-1.xml,none,abc,2026-11-20\n")
        self.assertFalse(unpulled())
        listed = subprocess.run(["bash", "-c", f'source "{guard}"; hart_split_shas "{root}"'], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual([hashlib.sha256(b"<stored/>").hexdigest()], listed.stdout.split())


class PulledDir(unittest.TestCase):
    def test_the_default_is_media_in_the_main_checkout_and_made_on_demand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp).resolve() / "main"
            subprocess.run(["git", "init", "-q", str(main)], check=True)
            (main / ".gitignore").write_text("/media\n")
            (main / "tools/hosts").mkdir(parents=True)
            guard = main / "tools/hosts/profile_tables_guard.sh"
            shutil.copy2(GUARD, guard)
            # a worktree of main finds the same folder
            subprocess.run(["git", "-C", str(main), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                            "commit", "-q", "--allow-empty", "-m", "x"], check=True)
            work = Path(tmp).resolve() / "work"
            subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(work), "-b", "t"], check=True)
            (work / "tools/hosts").mkdir(parents=True)
            shutil.copy2(GUARD, work / "tools/hosts/profile_tables_guard.sh")
            env = {k: v for k, v in os.environ.items() if k != "HART_PULLED_DIR"}
            for g in (guard, work / "tools/hosts/profile_tables_guard.sh"):
                done = subprocess.run(["bash", "-c", f'source "{g}"; hart_pulled_dir'], capture_output=True, text=True,
                                      env=env, timeout=30)
                self.assertEqual(0, done.returncode, done.stderr)
                self.assertEqual(main / "media/pulled-stores", Path(done.stdout.strip()).resolve())
            self.assertTrue((main / "media/pulled-stores").is_dir())
            ignored = subprocess.run(["git", "-C", str(main), "check-ignore", "-q", "media/pulled-stores"])
            self.assertEqual(0, ignored.returncode, "the default pulled folder must be git-ignored")

    def test_the_cache_default_is_in_the_main_checkout_and_the_override_wins(self) -> None:
        done = bash(f'hart_cache_dir "{ROOT}" schematic', {"HART_CACHE_DIR": ""})
        main = Path(bash(f'hart_main_checkout "{ROOT}"').stdout.strip())
        self.assertEqual(main / ".cache/hart/schematic", Path(done.stdout.strip()))
        self.assertEqual(0, subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", ".cache/hart/schematic"]).returncode)
        self.assertEqual("/x/web", bash(f'hart_cache_dir "{ROOT}" web', {"HART_CACHE_DIR": "/x"}).stdout.strip())

    def test_a_folder_inside_a_checkout_is_refused(self) -> None:
        inside = ROOT / "jmri/layouts/hart/output/pulled-test/kept"
        done = bash("hart_pulled_dir", {"HART_PULLED_DIR": str(inside)})
        self.assertEqual(1, done.returncode)
        self.assertIn("inside a git checkout", done.stderr)
        self.assertFalse(inside.parent.exists())          # refused before anything was made


if __name__ == "__main__":
    unittest.main()
