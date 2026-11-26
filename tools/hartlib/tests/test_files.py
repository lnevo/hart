"""hartlib.files: the atomic write and the tracked-file list."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "src"))

from hartlib import files, tables  # noqa: E402


class WriteAtomicTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.dir)], check=False))

    def leftovers(self):
        return sorted(p.name for p in self.dir.iterdir() if p.name.startswith("."))

    def test_text_and_bytes(self):
        target = self.dir / "a.txt"
        files.write_atomic(target, "é\n")
        self.assertEqual(target.read_bytes(), "é\n".encode())
        files.write_atomic(target, b"raw")
        self.assertEqual(target.read_bytes(), b"raw")
        self.assertEqual(self.leftovers(), [])

    def test_new_file_is_0644_and_old_mode_is_kept(self):
        new = self.dir / "new"
        files.write_atomic(new, "x")
        self.assertEqual(new.stat().st_mode & 0o777, 0o644)
        old = self.dir / "old"
        old.write_text("x")
        old.chmod(0o755)
        files.write_atomic(old, "y")
        self.assertEqual(old.stat().st_mode & 0o777, 0o755)

    def test_symlink_stays_a_link(self):
        real = self.dir / "real"
        real.write_text("old")
        link = self.dir / "link"
        link.symlink_to(real)
        files.write_atomic(link, "new")
        self.assertTrue(link.is_symlink())
        self.assertEqual(real.read_text(), "new")

    def test_hard_link_sees_the_new_bytes(self):
        a = self.dir / "a"
        a.write_text("old")
        b = self.dir / "b"
        os.link(a, b)
        files.write_atomic(a, "new")
        self.assertEqual(b.read_text(), "new")

    def test_without_follow_links_the_path_itself_is_replaced(self):
        real = self.dir / "real"
        real.write_text("old")
        link = self.dir / "link"
        link.symlink_to(real)
        files.write_atomic(link, "new", follow_links=False)
        self.assertFalse(link.is_symlink())
        self.assertEqual((link.read_text(), real.read_text()), ("new", "old"))
        other = self.dir / "other"
        os.link(real, other)
        files.write_atomic(real, "fresh", follow_links=False)
        self.assertEqual((real.read_text(), other.read_text()), ("fresh", "old"))

    def test_failed_write_keeps_the_old_file_and_no_temp(self):
        target = self.dir / "t"
        target.write_text("old")
        with mock.patch("hartlib.files.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                files.write_atomic(target, "new")
        self.assertEqual(target.read_text(), "old")
        self.assertEqual(self.leftovers(), [])

    def test_tables_uses_it(self):
        self.assertIs(tables._atomic_write, files.write_atomic)


class TrackedFilesTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.repo)], check=False))
        git = ["git", "-C", str(self.repo)]
        subprocess.run([*git, "init", "-q"], check=True)
        (self.repo / "a.py").write_text("")
        (self.repo / "d").mkdir()
        (self.repo / "d" / "b with space.txt").write_text("")
        (self.repo / "untracked.py").write_text("")
        subprocess.run([*git, "add", "a.py", "d"], check=True)
        # a submodule entry (mode 160000) without cloning one
        subprocess.run([*git, "update-index", "--add", "--cacheinfo",
                        "160000,1111111111111111111111111111111111111111,sub"], check=True)

    def test_lists_tracked_only(self):
        self.assertEqual(files.tracked_files(self.repo), ["a.py", "d/b with space.txt", "sub"])

    def test_pathspecs(self):
        self.assertEqual(files.tracked_files(self.repo, ":(glob)**/*.py"), ["a.py"])

    def test_submodules_left_out(self):
        self.assertEqual(files.tracked_files(self.repo, submodules=False), ["a.py", "d/b with space.txt"])

    def test_not_a_checkout_is_a_git_error(self):
        with self.assertRaises(files.GitError) as caught:
            files.tracked_files(tempfile.gettempdir() + "/no-such-checkout")
        self.assertIn("git ls-files failed", str(caught.exception))

    def test_no_git_is_a_git_error(self):
        with mock.patch("hartlib.files.subprocess.run", side_effect=FileNotFoundError("git")):
            with self.assertRaises(files.GitError):
                files.tracked_files(self.repo)


if __name__ == "__main__":
    unittest.main()
