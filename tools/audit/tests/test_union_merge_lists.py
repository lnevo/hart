"""The repo's .gitattributes merges tools/audit/hand_tables.csv and tools/audit/py_sizes.csv with git's union driver,
run on a scratch repo: rows two branches add merge clean and load, and a row both branches edit comes out twice and
the file's loader refuses it as listed twice (so union never hides a real conflict)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod     # dataclasses look their module up by name
    spec.loader.exec_module(mod)
    return mod


CPS = load("check_py_sizes", "tools/audit/check_py_sizes.py")
CHT = load("check_hand_tables", "tools/audit/check_hand_tables.py")
HAND = "tools/audit/hand_tables.csv"
SIZES = "tools/audit/py_sizes.csv"


def union_lines() -> str:
    """The repo's own .gitattributes lines for the two lists, so the test follows what is committed."""
    lines = [ln for ln in (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
             if ln.split()[:1] in ([HAND], [SIZES])]
    return "\n".join(lines) + "\n"


class UnionMerge(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git("init", "-q", "-b", "main")
        (self.root / ".gitattributes").write_text(union_lines(), encoding="utf-8")

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "core.hooksPath=/dev/null", *args], capture_output=True, text=True)

    def commit(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.assertEqual(self.git("commit", "-q", "-m", "x").returncode, 0)

    def merged(self, rel: str, base: str, ours: str, theirs: str) -> Path:
        """Commit base on main, theirs on a side branch and ours on main, merge the side branch, return the file."""
        self.commit(rel, base)
        self.git("checkout", "-q", "-b", "side")
        self.commit(rel, theirs)
        self.git("checkout", "-q", "main")
        self.commit(rel, ours)
        done = self.git("merge", "-q", "--no-edit", "side")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return self.root / rel

    def refused(self, read: Callable[[Path], object], error: type[Exception], path: Path, message: str) -> None:
        with self.assertRaises(error) as caught:
            read(path)
        self.assertIn(message, str(caught.exception))

    def test_both_lists_have_the_union_driver(self) -> None:
        self.assertEqual(union_lines(), f"{HAND} merge=union\n{SIZES} merge=union\n")

    def test_hand_tables_rows_added_on_both_sides_merge_and_load(self) -> None:
        head = "file,table,entries,status,reason\na.py,A,4,keep,r\n"
        path = self.merged(HAND, head, head + "b.py,B,4,keep,r\n", head + "c.py,C,4,keep,r\n")
        self.assertEqual(set(CHT.hand_tables.read_listed(path)), {("a.py", "A"), ("b.py", "B"), ("c.py", "C")})

    def test_a_hand_tables_row_edited_on_both_sides_is_listed_twice(self) -> None:
        head = "file,table,entries,status,reason\n"
        path = self.merged(HAND, head + "a.py,A,9,keep,r\n", head + "a.py,A,8,keep,r\n", head + "a.py,A,7,keep,r\n")
        self.assertEqual(path.read_text(encoding="utf-8").count("a.py,A,"), 2)
        self.refused(CHT.hand_tables.read_listed, CHT.HandTablesError, path, "a.py A is listed twice")

    def test_py_sizes_rows_added_on_both_sides_merge_and_load(self) -> None:
        head = "path,lines\na/big.py,900\n"
        path = self.merged(SIZES, head, head + "b/big.py,901\n", head + "c/big.py,902\n")
        self.assertEqual(CPS.read_sizes(path), {"a/big.py": 900, "b/big.py": 901, "c/big.py": 902})

    def test_a_py_sizes_row_edited_on_both_sides_is_listed_twice(self) -> None:
        path = self.merged(SIZES, "path,lines\na/big.py,900\n", "path,lines\na/big.py,880\n",
                           "path,lines\na/big.py,870\n")
        self.assertEqual(path.read_text(encoding="utf-8").count("a/big.py,"), 2)
        self.refused(CPS.read_sizes, CPS.SizeError, path, "a/big.py is listed twice")


if __name__ == "__main__":
    unittest.main()
