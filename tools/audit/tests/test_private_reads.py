"""tools/ci/changed_kind.py's private-reads rule (make ready's gate) and its NUL-separated stdin, on stand-ins."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "ci"))
sys.path.insert(0, str(ROOT / "tools" / "pipeline"))
import changed_kind  # noqa: E402
import manifest  # noqa: E402


def decl() -> changed_kind.Declarations:
    """Two check steps: plan.py reads a private box, lint.py does not; a cache box and an in-repo box feed both."""
    return changed_kind.Declarations(
        jobs={"plan": changed_kind.JobDecl(("data/overrides.json",), True, "tools/plan.py"),
              "panels-lengths": changed_kind.JobDecl(("data/lengths.csv",), True, "tools/lengths.py"),
              "lint": changed_kind.JobDecl(("data/a.csv",), True, "tools/lint.py")},
        static=("plan", "lint"), units={}, live=(),
        nodes=[{"id": "ext:plan", "kind": "unstructured", "path": ""},
               {"id": "ext:cache", "kind": "output", "path": ""},
               {"id": "ext:lib", "kind": "generator", "path": "lib"},
               {"id": "tools/plan.py", "path": "tools/plan.py", "kind": "generator"},
               {"id": "tools/lengths.py", "path": "tools/lengths.py", "kind": "generator"},
               {"id": "tools/lint.py", "path": "tools/lint.py", "kind": "generator"},
               {"id": "tools/helper.py", "path": "tools/helper.py", "kind": "generator"}],
        edges=[{"from": "ext:plan", "to": "tools/plan.py", "label": "reads"},
               {"from": "ext:plan", "to": "tools/lengths.py", "label": "reads lengths"},
               {"from": "ext:cache", "to": "tools/lint.py"},
               {"from": "ext:lib", "to": "tools/lengths.py", "label": "imports"},
               {"from": "tools/helper.py", "to": "tools/plan.py", "label": "imports"},
               {"from": "ext:plan", "to": "tools/lint.py", "side": "pointer"}],
        covers=manifest.covers)


def line(paths: list[str]) -> str:
    return changed_kind.private_line(paths, load=lambda _root: decl())


class PrivateReads(unittest.TestCase):
    def test_a_path_that_feeds_a_plan_reading_step_goes_to_the_remote(self) -> None:
        for path, want in (
            ("tools/plan.py", "remote: tools/plan.py reads ext:plan (check plan)"),
            ("data/overrides.json", "remote: data/overrides.json feeds tools/plan.py, which reads ext:plan"),
            ("tools/helper.py", "remote: tools/helper.py feeds tools/plan.py, which reads ext:plan"),
            ("lib/devices.py", "remote: lib/devices.py feeds tools/lengths.py, which reads ext:plan "
                               "(check panels-lengths)"),
        ):
            with self.subTest(path):
                self.assertTrue(line([path]).startswith(want), line([path]))

    def test_every_hit_is_counted_in_the_line(self) -> None:
        self.assertIn("; 1 more)", line(["tools/plan.py", "data/lengths.csv"]))

    def test_a_cache_a_pointer_and_an_unrelated_path_leave_github_as_the_gate(self) -> None:
        # lint.py reads only an output box (a cache) and has a pointer link from the private box
        self.assertEqual("github: no changed path feeds a check step that reads private files (ext:plan)",
                         line(["tools/lint.py", "data/a.csv", "wiki/x.md"]))

    def test_declarations_that_cannot_be_read_go_to_the_remote(self) -> None:
        def broken(_root: Path) -> changed_kind.Declarations:
            raise ValueError("no manifest")
        self.assertEqual("remote: the declarations cannot be read (ValueError: no manifest)",
                         changed_kind.private_line(["a.py"], load=broken))


class NulSeparatedStdin(unittest.TestCase):
    SCRIPT = ROOT / "tools" / "ci" / "changed_kind.py"

    def run_cli(self, *args: str, stdin: str) -> str:
        return subprocess.run([sys.executable, str(self.SCRIPT), *args], input=stdin, capture_output=True,
                              text=True, encoding="utf-8", check=True).stdout.strip()

    def test_a_name_with_u202f_is_a_plain_path_with_z(self) -> None:
        # git diff -z prints the name as it is; without -z git would quote it and the verdict would be full
        name = "docs/Screenshot 12.52.19 AM.md"
        self.assertEqual("docs: 2 changed paths, all Markdown docs",
                         self.run_cli("-z", "--why", stdin=f"{name}\0wiki/a.md\0"))
        self.assertEqual("full", self.run_cli(stdin='"docs/Screenshot 12.52.19\\342\\200\\257AM.md"\n'))

    def test_z_goes_without_git(self) -> None:
        done = subprocess.run([sys.executable, str(self.SCRIPT), "--git", "-z"], capture_output=True, text=True)
        self.assertEqual(2, done.returncode)
        self.assertIn("go without --git", done.stderr)


if __name__ == "__main__":
    unittest.main()
