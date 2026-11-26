"""tools/ops/move_path.py: move a tracked file or folder and rewrite what names it, in a throwaway git repo."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/ops/move_path.py"

FILES = {
    "tools/a/x.py": '"""Usage: python3 tools/a/x.py OUT"""\nfrom pathlib import Path\n'
                    'REPO = Path(__file__).resolve().parents[2]\nHERE = Path(__file__).resolve().parents[0]\n',
    "tools/a/helper.py": "VALUE = 1\n",
    "tools/a/README.md": "# a\n\nSee [the guide](../../docs/guide.md).\n",
    "tools/run.sh": 'python3 "$ROOT/tools/a/x.py"\nbash ${ROOT}/tools/a/x.py\ncp y "$OUT/tools/a/x.py"\n',
    "tools/deep/c/z.py": "from pathlib import Path\nTOOLS = Path(__file__).resolve().parents[2]\n"
                         "REPO = Path(__file__).resolve().parents[3]\n",
    "docs/README.md": "Read the docs here. See docs/guide.md and `docs`.\n",
    "docs/Mixed.md": "# Mixed\n",
    "tools/use.py": "import helper\nfrom helper import VALUE\n",
    "docs/guide.md": "# Guide\n\nRun `./tools/a/x.py` or tools/a/x.py.\n[x](../tools/a/x.py) [a](../tools/a/) "
                     "[web](https://example.com/tools/a/x.py) [anchor](#top)\n"
                     "Not these: mytools/a/x.py, tools/a/x.pyc, tools/a/x.py_old.\n",
    "docs/page.html": '<a href="../tools/a/x.py">x</a> <img src="../tools/a/pic.png">\n'
                      '<img src="../tools/a/pic.png?v=2"> [t](../tools/a/x.py "The script")\n',
    "docs/notes.md": "x.py is the script; helper.py too.\n",
    "docs/other.md": "index.py is another script.\n",
    "Makefile": "x:\n\tpython3 tools/a/x.py\n",
    "wiki/STATUS_LOG.md": "Updated: tools/a/x.py was added.\n",
    "archive/old.md": "tools/a/x.py, [x](../tools/a/x.py)\n",
}


class MovePathTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        for rel, text in FILES.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.repo / "tools/a/pic.png").write_bytes(b"\x89PNG\0\0binary tools/a/x.py")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
            subprocess.run(["git", *cmd], cwd=self.repo, env=env, check=True, capture_output=True)

    def run_it(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args, "--no-rebuild"], cwd=self.repo,
                              capture_output=True, text=True, timeout=60)

    def read(self, rel: str) -> str:
        return (self.repo / rel).read_text(encoding="utf-8")

    def test_the_plan_changes_nothing(self) -> None:
        done = self.run_it("tools/a/x.py", "tools/b/y.py")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("nothing changed", done.stdout)
        self.assertTrue((self.repo / "tools/a/x.py").exists())
        self.assertEqual(FILES["docs/guide.md"], self.read("docs/guide.md"))
        status = subprocess.run(["git", "status", "--short"], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertEqual("", status)

    def test_a_file_move_rewrites_every_whole_path_and_leaves_lookalikes(self) -> None:
        done = self.run_it("tools/a/x.py", "tools/b/y.py", "--apply")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse((self.repo / "tools/a/x.py").exists())
        self.assertTrue((self.repo / "tools/b/y.py").exists())
        guide = self.read("docs/guide.md")
        self.assertIn("Run `./tools/b/y.py` or tools/b/y.py.", guide)
        self.assertIn("[x](../tools/b/y.py)", guide)
        self.assertIn("[web](https://example.com/tools/a/x.py)", guide)
        self.assertIn("Not these: mytools/a/x.py, tools/a/x.pyc, tools/a/x.py_old.", guide)
        page = self.read("docs/page.html")
        self.assertIn('<a href="../tools/b/y.py">x</a> <img src="../tools/a/pic.png">', page)
        self.assertIn('[t](../tools/b/y.py "The script")', page)
        self.assertEqual('python3 "$ROOT/tools/b/y.py"\nbash ${ROOT}/tools/b/y.py\ncp y "$OUT/tools/a/x.py"\n',
                         self.read("tools/run.sh"))
        self.assertIn("tools/a/x.py after $OUT, not the repo root", done.stdout)
        self.assertIn("python3 tools/b/y.py", self.read("Makefile"))
        self.assertIn('"""Usage: python3 tools/b/y.py OUT"""', self.read("tools/b/y.py"))

    def test_history_keeps_the_old_name_unless_asked(self) -> None:
        self.run_it("tools/a/x.py", "tools/b/y.py", "--apply")
        self.assertEqual(FILES["wiki/STATUS_LOG.md"], self.read("wiki/STATUS_LOG.md"))
        self.assertEqual(FILES["archive/old.md"], self.read("archive/old.md"))

    def test_history_is_rewritten_when_asked(self) -> None:
        self.run_it("tools/a/x.py", "tools/b/y.py", "--apply", "--include-history")
        self.assertEqual("Updated: tools/b/y.py was added.\n", self.read("wiki/STATUS_LOG.md"))
        self.assertEqual("tools/b/y.py, [x](../tools/b/y.py)\n", self.read("archive/old.md"))

    def test_the_repo_root_lookup_follows_the_depth_and_others_are_reported(self) -> None:
        done = self.run_it("tools/a/x.py", "tools/b/c/y.py", "--apply")
        text = self.read("tools/b/c/y.py")
        self.assertIn("REPO = Path(__file__).resolve().parents[3]", text)
        self.assertIn("HERE = Path(__file__).resolve().parents[0]", text)
        self.assertIn("tools/b/c/y.py:4: a __file__ lookup", done.stdout)

    def test_a_folder_move_rewrites_paths_under_it_and_its_own_links(self) -> None:
        done = self.run_it("tools/a", "archive/tools-a", "--apply")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue((self.repo / "archive/tools-a/x.py").exists())
        self.assertTrue((self.repo / "archive/tools-a/pic.png").exists())
        guide = self.read("docs/guide.md")
        self.assertIn("[x](../archive/tools-a/x.py) [a](../archive/tools-a/)", guide)
        self.assertIn('src="../archive/tools-a/pic.png"', self.read("docs/page.html"))
        self.assertIn('src="../archive/tools-a/pic.png?v=2"', self.read("docs/page.html"))
        self.assertIn("[the guide](../../docs/guide.md)", self.read("archive/tools-a/README.md"))
        self.assertIn("REPO = Path(__file__).resolve().parents[2]", self.read("archive/tools-a/x.py"))
        self.assertIn("imports helper, which moved to archive/tools-a/", done.stdout)

    def test_a_moved_page_relinks_from_its_new_folder(self) -> None:
        self.run_it("docs/guide.md", "wiki/guides/guide.md", "--apply")
        self.assertIn("[x](../../tools/a/x.py) [a](../../tools/a/)", self.read("wiki/guides/guide.md"))
        self.assertIn("[the guide](../../wiki/guides/guide.md)", self.read("tools/a/README.md"))

    def test_a_name_alone_is_reported_not_changed(self) -> None:
        done = self.run_it("tools/a/x.py", "tools/b/y.py", "--apply")
        self.assertIn("docs/notes.md:1: names x.py without its path", done.stdout)
        self.assertNotIn("docs/other.md", done.stdout)
        self.assertEqual(FILES["docs/notes.md"], self.read("docs/notes.md"))

    def test_a_one_word_folder_is_rewritten_as_a_path_only(self) -> None:
        self.run_it("docs", "documentation", "--apply")
        self.assertEqual("Read the docs here. See documentation/guide.md and `documentation`.\n",
                         self.read("documentation/README.md"))

    def test_a_lookup_the_move_did_not_change_is_reported(self) -> None:
        done = self.run_it("tools/deep/c/z.py", "tools/z.py", "--apply")
        text = self.read("tools/z.py")
        self.assertIn("REPO = Path(__file__).resolve().parents[1]", text)
        self.assertIn("TOOLS = Path(__file__).resolve().parents[2]", text)
        self.assertIn("tools/z.py:2: a __file__ lookup", done.stdout)
        self.assertNotIn("tools/z.py:3:", done.stdout)

    def test_a_case_only_rename(self) -> None:
        done = self.run_it("docs/Mixed.md", "docs/mixed.md", "--apply")
        self.assertEqual(0, done.returncode, done.stderr)
        listed = subprocess.run(["git", "ls-files", "docs"], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertIn("docs/mixed.md", listed.split())
        self.assertNotIn("docs/Mixed.md", listed.split())

    def test_line_endings_are_kept(self) -> None:
        (self.repo / "docs/crlf.md").write_bytes(b"see tools/a/x.py\r\nend\r\n")
        subprocess.run(["git", "add", "docs/crlf.md"], cwd=self.repo, check=True)
        self.run_it("tools/a/x.py", "tools/b/y.py", "--apply")
        self.assertEqual(b"see tools/b/y.py\r\nend\r\n", (self.repo / "docs/crlf.md").read_bytes())

    def test_refusals(self) -> None:
        for args, says in ((("tools/nope.py", "tools/b.py"), "not a tracked file"),
                           (("tools/a/x.py", "docs/guide.md"), "already exists"),
                           (("tools/a", "tools/a/inner"), "into itself"),
                           (("../x", "tools/b.py"), "from the repo root")):
            with self.subTest(args=args):
                done = self.run_it(*args, "--apply")
                self.assertEqual(2, done.returncode, done.stdout)
                self.assertIn(says, done.stderr)


if __name__ == "__main__":
    unittest.main()
