"""tools/check.sh's docs-only path: a checkout that changes only Markdown docs (tools/ci/changed_kind.py --git) runs
the quick docs checks (tools/ci/docs_checks.sh, CI's list) and stops; anything else, or no merge base, runs in full."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "ci"))
sys.path.insert(0, str(ROOT / "tools" / "audit"))
import changed_kind  # noqa: E402
import check_stamps  # noqa: E402
import docs_unit_tests  # noqa: E402
import portal_inputs  # noqa: E402

manifest = check_stamps.pm      # tools/pipeline/manifest.py, as the stamps load it

# check.sh's variables that pick a path; the tests start each run without them.
PATH_VARS = ("CI", "FULL", "CHECK_ONLY", "CHECK_AUDIT", "HART_TABLES", "PORTAL_CHECK", "CHECK_RECORD_TO",
             "CHECK_SKIP_FROM", "CHECK_SKIP_NOTE", "CHECK_STAMPS_DIR", "PYTHONPATH")
# Stand-ins for what check.sh calls before and on the docs path: the plugin pin guard (STUB_PIN stops the run there,
# before any job, so a full-path run ends at once) and the docs checks (they print what they were given).
GUARD_STUB = 'hart_plugin_pin_problem() { echo "${STUB_PIN:-}"; }\n'
DOCS_STUB = '#!/usr/bin/env bash\necho "STUB DOCS CHECKS HOPS_PY=$HOPS_PY"\nexit "${STUB_DOCS_RC:-0}"\n'


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


class Scratch:
    """A repo with main as origin/main, the branch `work` checked out, and wiki/a.md, tools/x.py, AGENTS.md."""

    def __init__(self, base: Path, with_check_sh: bool = False):
        self.repo = base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "test")
        self.write("wiki/a.md", "# A\n")
        self.write("tools/x.py", "x = 1\n")
        self.write("AGENTS.md", "# Agents\n")
        self.write(".gitignore", "/media\n__pycache__/\n")   # as the repo's
        if with_check_sh:
            for rel in ("tools/check.sh", "tools/ci/changed_kind.py", "tools/audit/portal_inputs.py"):
                self.write(rel, (ROOT / rel).read_text(encoding="utf-8"))
            self.write("tools/hosts/profile_tables_guard.sh", GUARD_STUB)
            self.write("tools/ci/docs_checks.sh", DOCS_STUB)
        self.commit("base")
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.repo, "checkout", "-q", "-b", "work")

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", message)

    def verdict(self) -> str:
        return changed_kind.checkout_verdict(self.repo, "origin/main")

    def check_sh(self, **env: str) -> subprocess.CompletedProcess:
        base = {k: v for k, v in os.environ.items() if k not in PATH_VARS}
        return subprocess.run(["bash", str(self.repo / "tools/check.sh")], cwd=self.repo,
                              env={**base, "SCHEMATIC_CACHE": "", "STUB_PIN": "stub: stopped before any job", **env},
                              capture_output=True, text=True, timeout=60)


class Verdict(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s = Scratch(Path(self.tmp.name))

    def test_a_docs_only_branch_is_docs(self) -> None:
        self.s.write("wiki/a.md", "# A\n\nmore\n")
        self.s.write("docs/decisions/ADR-1.md", "# ADR\n")
        self.s.commit("docs")
        self.assertEqual("docs: 2 changed paths, all Markdown docs", self.s.verdict())

    def test_uncommitted_and_untracked_markdown_count(self) -> None:
        self.s.write("wiki/a.md", "# A, edited\n")
        self.assertEqual("docs: 1 changed path, all Markdown docs", self.s.verdict())
        self.s.write("wiki/new.md", "# New\n")
        self.assertEqual("docs: 2 changed paths, all Markdown docs", self.s.verdict())
        # an untracked file that is not docs makes it full, just as a committed one would
        self.s.write("wiki/new.png", "png")
        self.assertEqual("full: wiki/new.png is not docs", self.s.verdict())

    def test_one_non_docs_path_makes_it_full(self) -> None:
        for rel, text in (("tools/x.py", "x = 2\n"), (".claude/skills/s/SKILL.md", "# S\n"), ("AGENTS.md", "# A2\n"),
                          ("docs/pipeline-map/notes.md", "# Map\n")):
            with self.subTest(rel):
                git(self.s.repo, "reset", "-q", "--hard", "origin/main")
                git(self.s.repo, "clean", "-qfd")
                self.s.write("wiki/a.md", "# A, edited\n")
                self.s.write(rel, text)
                self.s.commit(f"change {rel}")
                self.assertEqual(f"full: {rel} is not docs", self.s.verdict())

    def test_no_changed_paths_is_full(self) -> None:
        self.assertEqual("full: no changed paths", self.s.verdict())

    def test_an_ignored_mirror_link_does_not_count(self) -> None:
        # a worktree links media/ to the main checkout's (gitignored): not a change of this branch
        (self.s.repo / "media").symlink_to(self.tmp.name)
        self.s.write("wiki/a.md", "# A, edited\n")
        self.assertEqual("docs: 1 changed path, all Markdown docs", self.s.verdict())

    def test_no_merge_base_is_unknown_with_the_reason(self) -> None:
        git(self.s.repo, "update-ref", "-d", "refs/remotes/origin/main")
        self.s.write("wiki/a.md", "# A, edited\n")
        verdict = self.s.verdict()
        self.assertTrue(verdict.startswith("unknown: no merge base with origin/main"), verdict)

    def test_git_that_cannot_run_is_unknown_and_not_blamed_on_the_merge_base(self) -> None:
        for err in (FileNotFoundError("git"), subprocess.TimeoutExpired(["git"], 60)):
            with self.subTest(err=type(err).__name__):
                with mock.patch.object(portal_inputs.subprocess, "run", side_effect=err):
                    verdict = changed_kind.checkout_verdict(self.s.repo, "origin/main")
                self.assertTrue(verdict.startswith("unknown: git merge-base could not run"), verdict)
                self.assertNotIn("no merge base", verdict)

    def test_a_staged_submodule_move_is_a_change(self) -> None:
        # a gitlink staged at a new commit: the working diff leaves submodules out, the staged one must not
        sha = git(self.s.repo, "rev-parse", "HEAD").strip()
        git(self.s.repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},external/plugin")
        self.s.write("wiki/a.md", "# A, edited\n")
        self.assertEqual("full: external/plugin is not docs", self.s.verdict())


class Paths(unittest.TestCase):
    def test_dot_segments_are_not_docs(self) -> None:
        for p in ("wiki/../tools/x.md", "docs/./a.md", "../a.md", "wiki//a.md", "docs/pipeline-map/../a.md"):
            self.assertEqual("full", changed_kind.kind([p]), p)
        self.assertEqual("docs", changed_kind.kind(["./wiki/a.md"]))

    def test_describe_names_the_first_non_docs_path_and_counts_the_rest(self) -> None:
        self.assertEqual("full: tools/x.py is not docs and 1 more",
                         changed_kind.describe(["wiki/a.md", "tools/x.py", "AGENTS.md"]))


class Cli(unittest.TestCase):
    SCRIPT = ROOT / "tools/ci/changed_kind.py"

    def cli(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.SCRIPT), *args], input=stdin, capture_output=True, text=True,
                              timeout=60)

    def test_bad_calls_are_usage_errors(self) -> None:
        for args in (("--base", "origin/main"), ("--git", "--base", ""), ("--git", "--base=-x")):
            with self.subTest(args):
                done = self.cli(*args)
                self.assertEqual(2, done.returncode)
                self.assertIn("--base", done.stderr)
                self.assertNotIn("Traceback", done.stderr)

    def test_git_mode_prints_one_verdict_line(self) -> None:
        done = self.cli("--git")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertRegex(done.stdout, r"\A(docs|full|unknown): [^\n]+\n\Z")


class CheckSh(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s = Scratch(Path(self.tmp.name), with_check_sh=True)

    def test_a_docs_only_branch_takes_the_quick_path_and_says_so_first(self) -> None:
        self.s.write("wiki/decisions/ADR-1.md", "# ADR\n")
        done = self.s.check_sh(STUB_PIN="")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertTrue(lines[0].startswith("Docs-only change (1 changed path, all Markdown docs)"), lines[0])
        self.assertIn("STUB DOCS CHECKS HOPS_PY=python3", lines)
        # not a pass of check.sh (owner, 2026-11-24): no "ALL PASSED", and no stamp written
        self.assertNotIn("ALL PASSED", done.stdout)
        self.assertEqual("DOCS CHECKS PASSED (the docs-only path; FULL=1 runs check.sh in full)", lines[-1])

    def test_a_failed_docs_check_fails_the_run(self) -> None:
        self.s.write("wiki/a.md", "# A, edited\n")
        done = self.s.check_sh(STUB_PIN="", STUB_DOCS_RC="1")
        self.assertEqual(1, done.returncode)
        self.assertEqual("FAILED", done.stdout.splitlines()[-1])

    def test_the_docs_path_still_stops_on_a_wrong_plugin_pin(self) -> None:
        self.s.write("wiki/a.md", "# A, edited\n")
        done = self.s.check_sh()
        self.assertEqual(2, done.returncode)
        self.assertIn("STOP: stub: stopped before any job", done.stderr)
        self.assertNotIn("STUB DOCS CHECKS", done.stdout)

    def test_a_code_change_or_an_explicit_request_takes_the_full_path(self) -> None:
        self.s.write("tools/x.py", "x = 2\n")
        done = self.s.check_sh()
        self.assertEqual(2, done.returncode, done.stdout)   # the stub pin guard stops the full path before any job
        self.assertEqual("", done.stdout)
        self.s.write("tools/x.py", "x = 1\n")
        self.s.write("wiki/a.md", "# A, edited\n")
        for env in ({"FULL": "1"}, {"CI": "true"}, {"CHECK_ONLY": "phase02"}, {"PORTAL_CHECK": "1"}):
            with self.subTest(env):
                done = self.s.check_sh(**env)
                self.assertNotIn("Docs-only", done.stdout)
                self.assertNotIn("STUB DOCS CHECKS", done.stdout)
                self.assertIn("STOP: stub", done.stderr)

    def test_no_merge_base_takes_the_full_path_with_the_reason(self) -> None:
        git(self.s.repo, "update-ref", "-d", "refs/remotes/origin/main")
        self.s.write("wiki/a.md", "# A, edited\n")
        done = self.s.check_sh()
        first = done.stdout.splitlines()[0]
        self.assertTrue(first.startswith("Full checks: cannot tell what changed, no merge base with origin/main"),
                        first)
        self.assertNotIn("STUB DOCS CHECKS", done.stdout)
        self.assertIn("STOP: stub", done.stderr)

    def test_a_crash_of_the_verdict_takes_the_full_path_and_says_so(self) -> None:
        self.s.write("tools/ci/changed_kind.py", "raise SystemExit('boom')\n")
        self.s.write("wiki/a.md", "# A, edited\n")
        done = self.s.check_sh()
        self.assertTrue(done.stdout.startswith("Full checks: tools/ci/changed_kind.py --git failed: boom"), done.stdout)
        self.assertIn("STOP: stub", done.stderr)


class OneList(unittest.TestCase):
    def test_ci_and_check_sh_run_the_same_docs_checks_script(self) -> None:
        workflow = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")
        step = workflow[workflow.index("      - name: Quick docs checks\n"):]
        step = step[:step.index("\n      - ", 1)]
        self.assertIn("if: steps.kind.outputs.kind == 'docs'", step)
        self.assertIn("run: bash tools/ci/docs_checks.sh", step)
        self.assertNotIn("python3 ", step, "a docs check listed in the workflow, not in tools/ci/docs_checks.sh")
        # check.sh's docs-only path runs the same script: CheckSh.test_a_docs_only_branch_takes_the_quick_path_...

    def test_each_docs_check_is_also_in_the_full_run(self) -> None:
        """The docs path skips the full run, so its checks must be ones the full run makes too: the manifest's
        docs-only steps, each in the static group or a job of its own that check.sh always queues (not the portal
        build, which check.sh runs only where its inputs are)."""
        docs = manifest.select(manifest.load(), "check", docs_only=True)
        self.assertGreaterEqual(len(docs), 8)
        for step in docs:
            with self.subTest(step.name):
                self.assertTrue(step.group == "static" or (not step.group and step.name != "portal"))
        # that docs_checks.sh takes them from the manifest and lists none by hand: the next test runs it

    def test_docs_checks_runs_every_check_and_fails_when_one_did(self) -> None:
        """Every check it runs is a docs-only step of the manifest (asked for with exactly those arguments) or one of
        its unit test lines: a check listed by hand would be one heading more."""
        docs = manifest.select(manifest.load(), "check", docs_only=True)
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "tools/ci").mkdir(parents=True)
            shutil.copy(ROOT / "tools/ci/docs_checks.sh", repo / "tools/ci/docs_checks.sh")
            (repo / "lines").write_text("".join(manifest.shell_line(s) + "\n" for s in docs))
            units = docs_unit_tests.lines(docs_unit_tests.tests())
            (repo / "units").write_text("".join(line + "\n" for line in units))
            bin_dir = repo / "bin"
            bin_dir.mkdir()
            # a python3 that answers the manifest's docs-only lines, logs each other script and fails the ai-speak
            # check only
            (bin_dir / "python3").write_text(
                '#!/usr/bin/env bash\n'
                f'if [[ "$*" == "tools/pipeline/manifest.py jobs check --docs-only" ]]; then cat "{repo}/lines"; exit 0; fi\n'
                f'if [[ "$1" == tools/ci/docs_unit_tests.py ]]; then cat "{repo}/units"; exit 0; fi\n'
                'if [[ "$1" == tools/pipeline/manifest.py ]]; then echo "manifest.py: not the docs-only list: $*" >&2; exit 1; fi\n'
                'echo "ran $1"\n[[ "$1" != *check_ai_speak.py ]]\n')
            (bin_dir / "python3").chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            env.pop("HOPS_PY", None)
            done = subprocess.run(["bash", str(repo / "tools/ci/docs_checks.sh")], env=env, capture_output=True,
                                  text=True, timeout=30)
            self.assertEqual(1, done.returncode)
            self.assertEqual(len(docs) + len(units), len(re.findall(r"^ran ", done.stdout, re.M)),
                             done.stdout)
            self.assertEqual(len(docs) + len(units), len(re.findall(r"^--- ", done.stdout, re.M)),
                             done.stdout)
            self.assertIn("quick docs checks FAILED: ai-speak", done.stdout)


def check_sh_list(name: str) -> set[str]:
    """The names in one of check.sh's space-separated lists (SLOW, BY_CLASS, LE_TESTS), every assignment added up."""
    text = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
    found = re.findall(rf'^\s*(?:\[\[[^\]]*\]\]\s*\|\|\s*)?{name}\+?="([^"]*)"', text, re.M)
    if not found:
        raise AssertionError(f"tools/check.sh: no {name}= list")
    return {w for words in found for w in words.split()}


class DocsUnitTests(unittest.TestCase):
    """The unit tests docs_checks.sh runs: tools/ci/docs_unit_tests.py makes them from the stamp declarations of what
    reads docs (tools/audit/check_stamps.py), so every declaration on docs is run or left out with a reason."""

    def test_the_real_list_runs_as_check_sh_names_its_tests(self) -> None:
        tests = docs_unit_tests.tests()
        stamps = [stamp for stamp, *_ in tests]
        self.assertIn("unit-guards test_name_copies", stamps)
        self.assertIn(("unit-jmri test_speedmatch_distance", "jmri/layouts/hart/scripts/tests",
                       "test_speedmatch_distance.py", "RunnerSource."), tests)
        check_sh = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
        for stamp, folder, file, _k in tests:
            with self.subTest(stamp):
                self.assertIn(folder, check_sh)
                # check.sh runs these files under another job name (the Layout Editor job, one job per class)
                self.assertNotIn(file.removesuffix(".py"), check_sh_list("LE_TESTS"))
                self.assertNotIn(file, check_sh_list("BY_CLASS"))
        done = subprocess.run([sys.executable, str(ROOT / "tools/ci/docs_unit_tests.py")], capture_output=True,
                              text=True, timeout=60)
        self.assertEqual((0, docs_unit_tests.lines(tests)), (done.returncode, done.stdout.splitlines()), done.stderr)

    def test_each_k_filter_names_a_test_class_of_its_file(self) -> None:
        for stamp, folder, file, k in docs_unit_tests.tests():
            if k is None:
                continue
            with self.subTest(stamp):
                done = subprocess.run([sys.executable, str(ROOT / "tools/audit/test_classes.py"),
                                       str(ROOT / folder / file)], capture_output=True, text=True, timeout=60)
                self.assertEqual(0, done.returncode, done.stderr)
                classes = {c.split(".")[-1] for c in done.stdout.split()}
                self.assertIn(k.split(".")[0], classes, f"-k {k} names no test class of {file}")

    def stamps(self, extra: dict, by_kind: dict | None = None, docs_k: dict | None = None):
        """A stand-in for check_stamps with only these declarations."""
        return type("Stamps", (), {"BY_KIND": by_kind or {"unit-guards": ("tools/**/*",)}, "EXTRA": extra,
                                   "MANIFEST_CHECK": ("tools/**/*",), "RUNS_JOBS": {}, "DOCS_K": docs_k or {},
                                   "declared": staticmethod(lambda name: ())})

    def test_problems_fail_the_list_and_name_the_reason(self) -> None:
        real = "unit-guards test_name_copies"
        cases = (
            (self.stamps({}), {}, "no unit test is declared on docs/ or wiki/ outside LEFT_OUT"),
            (self.stamps({real: ("docs/**/*",)}), {"unit-guards test_gone": "x"}, "LEFT_OUT names 'unit-guards test_gone'"),
            (self.stamps({real: ("docs/**/*",)}, {"unit-guards": ("wiki/**/*",)}), {}, "'unit-guards' is declared"),
            (self.stamps({"unit-guards test_no_such_file": ("docs/**/*",)}), {}, "test_no_such_file.py is gone"),
            (self.stamps({real: ("docs/**/*",)}, docs_k={"unit-jmri test_x": "A."}), {}, "DOCS_K names 'unit-jmri"),
            (self.stamps({real: ("docs/**/*",)}, docs_k={real: "A; rm"}), {}, "is not a class or test name"),
        )
        for stamps, left_out, why in cases:
            with self.subTest(why), self.assertRaisesRegex(docs_unit_tests.Problem, why):
                docs_unit_tests.tests(stamps, left_out)
        self.assertEqual(docs_unit_tests.lines(docs_unit_tests.tests(self.stamps({real: ("docs/x.md",)}), {})),
                         ["unit-guards-test_name_copies python3 -m unittest discover -b -q -s tools/audit/tests "
                          "-p test_name_copies.py"])
        with mock.patch.object(docs_unit_tests, "tests", side_effect=docs_unit_tests.Problem("none")), \
                mock.patch("sys.stderr"):
            self.assertEqual(1, docs_unit_tests.main())

    def test_the_probe_reads_patterns_as_the_stamps_do(self) -> None:
        covers = docs_unit_tests.covers_markdown_docs
        self.assertTrue(covers(("**/*",)))
        self.assertTrue(covers(("docs/jmri/**/*",)))
        self.assertTrue(covers(("docs/INDEX.md",)))
        self.assertFalse(covers(("**/*.py", "www/**/*", "tools/**/*")))
        self.assertFalse(covers(("docs/x.json",)))
        self.assertTrue(covers(("docs/jmri/*/**/*",)))     # a wildcard segment in the middle
        self.assertTrue(covers(("wiki/*/notes/*.md",)))

    def test_check_sh_lists_are_read(self) -> None:
        self.assertIn("test_build_layout_le", check_sh_list("LE_TESTS"))
        self.assertIn("test_worktrees.py", check_sh_list("BY_CLASS"))
        self.assertIn("test_deploy_gates.py", check_sh_list("BY_CLASS"))
        with self.assertRaisesRegex(AssertionError, "no NOPE= list"):
            check_sh_list("NOPE")


if __name__ == "__main__":
    unittest.main()
