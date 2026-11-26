"""tools/pipeline/manifest.py: no file is an output of a step in checks.toml and of a step in panels.toml (writer_problems,
load_both), as #1187 found www/data/crew.json with two writers. SHARED_OUTPUTS lists the deliberate exceptions."""
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("pipeline_manifest_writers", ROOT / "tools/pipeline/manifest.py")
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M          # its dataclasses look their module up while the class is made
SPEC.loader.exec_module(M)

TRACKED = {"tools/a.py", "tools/b.py", "tools/p.py", "www/x.json", "www/y.json", "docs/maps/one.svg"}
GRAPH = {"domains": [{"id": "layout"}], "nodes": [], "edges": []}
REPO = M.repo_from(TRACKED, GRAPH)


def check_step(name: str, *outputs: str) -> str:
    outs = ", ".join(f'"{o}"' for o in outputs)
    return (f'[[step]]\nname = "{name}"\nrunner = "check"\ncmd = ["python3", "tools/a.py"]\ngit = []\n'
            f'domain = "layout"\nlabel = "a.py"\ndesc = "A check."\noutputs = [{outs}]\n')


def panel_step(name: str, *outputs: str, script: str = "tools/p.py") -> str:
    outs = ", ".join(f'"{o}"' for o in outputs)
    return (f'[[step]]\nname = "{name}"\nmode = "step"\ncmd = ["python3", "{script}"]\ncheck_args = ["--check"]\n'
            f'domain = "layout"\nlabel = "p.py"\ndesc = "A panels step."\noutputs = [{outs}]\n')


class WriterProblems(unittest.TestCase):
    def both(self, checks: str, panels: str, shared=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        c, p = Path(tmp.name, "checks.toml"), Path(tmp.name, "panels.toml")
        c.write_text(checks, encoding="utf-8")
        p.write_text(panels, encoding="utf-8")
        with mock.patch.dict(M.manifest_panels.SHARED_OUTPUTS, shared or {}, clear=True):
            return M.load_both(c, p, REPO)

    def test_separate_outputs_load(self) -> None:
        steps, panels = self.both(check_step("one", "www/x.json"), panel_step("build", "www/y.json"))
        self.assertEqual(([s.name for s in steps], [s.name for s in panels]), (["one"], ["build"]))

    def test_one_file_in_both_fails_naming_both_steps_and_the_fixes(self) -> None:
        with self.assertRaises(M.ManifestError) as caught:
            self.both(check_step("one", "www/x.json"), panel_step("build", "www/x.json"))
        msg = str(caught.exception)
        self.assertIn("www/x.json: an output of step 'one' in", msg)
        self.assertIn("checks.toml and of step 'build' in", msg)
        self.assertIn("drop it from one step, or", msg)
        self.assertIn("SHARED_OUTPUTS", msg)

    def test_a_glob_that_names_the_file_counts(self) -> None:
        with self.assertRaisesRegex(M.ManifestError, r"docs/maps/one.svg and docs/maps/\*: an output of step 'one'"):
            self.both(check_step("one", "docs/maps/one.svg"), panel_step("build", "docs/maps/*"))

    def test_every_double_writer_is_named(self) -> None:
        with self.assertRaises(M.ManifestError) as caught:
            self.both(check_step("one", "www/x.json", "www/y.json"), panel_step("build", "www/x.json", "www/y.json"))
        self.assertEqual(len(str(caught.exception).splitlines()), 2)

    def test_a_shared_output_passes_only_with_its_own_two_steps(self) -> None:
        shared = {"www/x.json": ("one", "build", "both write it whole the same way")}
        self.both(check_step("one", "www/x.json"), panel_step("build", "www/x.json"), shared)
        with self.assertRaisesRegex(M.ManifestError, "www/x.json: an output of step 'two'"):
            self.both(check_step("one", "www/x.json") + check_step("two", "www/x.json"),
                      panel_step("build", "www/x.json"), shared)

    def test_a_stale_or_unreasoned_shared_entry_fails(self) -> None:
        with self.assertRaisesRegex(M.ManifestError, "SHARED_OUTPUTS .*: www/x.json: step 'one' in .* and step "
                                                     "'build' in .* no longer both declare it; remove the entry"):
            self.both(check_step("one", "www/x.json"), panel_step("build", "www/y.json"),
                      {"www/x.json": ("one", "build", "why")})
        with self.assertRaisesRegex(M.ManifestError, "SHARED_OUTPUTS .*: www/x.json: give the reason"):
            self.both(check_step("one", "www/x.json"), panel_step("build", "www/x.json"),
                      {"www/x.json": ("one", "build", " ")})

    def test_check_command_reports_it_and_exits_1(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        c, p = Path(tmp.name, "checks.toml"), Path(tmp.name, "panels.toml")
        c.write_text(check_step("one", "www/x.json"), encoding="utf-8")
        p.write_text(panel_step("build", "www/x.json"), encoding="utf-8")
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(M, "repo", return_value=REPO), redirect_stderr(err), redirect_stdout(out):
            code = M.main(["--manifest", str(c), "--panels", str(p), "check"])
        self.assertEqual((code, out.getvalue()), (1, ""))
        self.assertIn("manifest.py: www/x.json: an output of step 'one'", err.getvalue())


class RepoManifests(unittest.TestCase):
    def test_the_repo_manifests_have_one_writer_per_file(self) -> None:
        """The current checks.toml and panels.toml pass; crew.json is their one listed shared output."""
        steps, panels = M.load_both()
        self.assertTrue(steps and panels)
        self.assertEqual(set(M.SHARED_OUTPUTS), {"www/data/crew.json"})


if __name__ == "__main__":
    unittest.main()
