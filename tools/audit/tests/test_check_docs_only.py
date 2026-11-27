"""tools/check.sh's docs-only and light paths: a checkout that changes only Markdown docs (tools/ci/changed_kind.py --git)
runs the quick docs checks (tools/ci/docs_checks.sh, CI's list) and stops; a light one (docs, or data only static
checks read) runs tools/ci/light_checks.sh; anything else, or no merge base, runs in full. changed_kind.py is run on
example path lists, on the real declarations and on stand-ins, and light_checks.sh on stand-in scripts."""
from __future__ import annotations

import json
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
sys.path.insert(0, str(ROOT / "tools" / "hartlib" / "src"))
from hartlib import devices  # noqa: E402

FIELD_MASTER = devices.field_path().relative_to(ROOT).as_posix()   # a CSV master, by the one path

manifest = check_stamps.pm      # tools/pipeline/manifest.py, as the stamps load it


def kind_of(paths: list[str]) -> str:
    return changed_kind.verdict(paths).kind


def checkout_line(root: Path, base: str) -> str:
    """changed_kind --git's line for the checkout at `root`."""
    v = changed_kind.checkout(root, base)
    return v if isinstance(v, str) else v.line

# check.sh's variables that pick a path; the tests start each run without them.
PATH_VARS = ("CI", "FULL", "CHECK_ONLY", "CHECK_AUDIT", "CHECK_AUDIT_FAILS", "HART_TABLES", "PORTAL_CHECK",
             "CHECK_RECORD_TO", "CHECK_SKIP_FROM", "CHECK_SKIP_NOTE", "CHECK_STAMPS_DIR", "PYTHONPATH")
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
        return checkout_line(self.repo, "origin/main")

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
        self.assertEqual("full: wiki/new.png is not a data file (.json, .csv, .tsv, .txt, .md)", self.s.verdict())

    def test_one_non_docs_path_makes_it_full(self) -> None:
        # a Markdown file under docs/pipeline-map/ is data to the light rule, whose declarations this scratch repo
        # does not hold: full, with that reason
        for rel, text, why in (("tools/x.py", "x = 2\n", "tools/x.py is code"),
                               (".claude/skills/s/SKILL.md", "# S\n", ".claude/skills/s/SKILL.md is under .claude/"),
                               ("AGENTS.md", "# A2\n", "AGENTS.md is code or agent rules"),
                               ("docs/pipeline-map/notes.md", "# Map\n", "the declarations cannot be read")):
            with self.subTest(rel):
                git(self.s.repo, "reset", "-q", "--hard", "origin/main")
                git(self.s.repo, "clean", "-qfd")
                self.s.write("wiki/a.md", "# A, edited\n")
                self.s.write(rel, text)
                self.s.commit(f"change {rel}")
                verdict = self.s.verdict()
                self.assertTrue(verdict.startswith(f"full: {why}"), verdict)

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
                    verdict = checkout_line(self.s.repo, "origin/main")
                self.assertTrue(verdict.startswith("unknown: git merge-base could not run"), verdict)
                self.assertNotIn("no merge base", verdict)

    def test_a_staged_submodule_move_is_a_change(self) -> None:
        # a gitlink staged at a new commit: the working diff leaves submodules out, the staged one must not
        sha = git(self.s.repo, "rev-parse", "HEAD").strip()
        git(self.s.repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},external/plugin")
        self.s.write("wiki/a.md", "# A, edited\n")
        self.assertEqual("full: external/plugin is not a data file (.json, .csv, .tsv, .txt, .md)", self.s.verdict())


class Paths(unittest.TestCase):
    def test_dot_segments_are_not_docs(self) -> None:
        for p in ("wiki/../tools/x.md", "docs/./a.md", "../a.md", "wiki//a.md", "docs/pipeline-map/../a.md"):
            self.assertEqual("full", kind_of([p]), p)
        self.assertEqual("docs", kind_of(["./wiki/a.md"]))

    def test_describe_names_the_first_path_that_is_not_light_and_why(self) -> None:
        self.assertEqual("full: tools/x.py is code or configuration (.py)",
                         changed_kind.verdict(["wiki/a.md", "tools/x.py", "AGENTS.md"]).line)


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
        self.assertRegex(done.stdout, r"\A(docs|light|full|unknown): [^\n]+\n\Z")


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
        # not a pass of check.sh: no "ALL PASSED", and no stamp written
        self.assertNotIn("ALL PASSED", done.stdout)
        self.assertEqual("DOCS CHECKS PASSED (the docs-only path; FULL=1 runs check.sh in full)", lines[-1])

    def test_a_light_verdict_runs_the_light_checks_and_their_exit_is_the_run_s(self) -> None:
        self.s.write("tools/ci/changed_kind.py", 'print("light: 1 changed path, a stand-in verdict")\n')
        self.s.write("tools/ci/light_checks.sh", 'echo "STUB LIGHT $* HOPS_PY=$HOPS_PY"\necho "LIGHT CHECKS PASSED"\n'
                                                 'exit "${STUB_LIGHT_RC:-0}"\n')
        done = self.s.check_sh(STUB_PIN="")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertTrue(lines[0].startswith("Light change (1 changed path, a stand-in verdict)"), lines[0])
        self.assertIn("STUB LIGHT --git HOPS_PY=python3", lines)
        self.assertEqual("LIGHT CHECKS PASSED", lines[-1])
        self.assertNotIn("ALL PASSED", done.stdout.replace("LIGHT CHECKS PASSED", ""))
        self.assertNotIn("STUB DOCS CHECKS", done.stdout)
        self.assertEqual(3, self.s.check_sh(STUB_PIN="", STUB_LIGHT_RC="3").returncode)
        stopped = self.s.check_sh()     # the plugin pin guard still stops it before any check
        self.assertEqual(2, stopped.returncode)
        self.assertNotIn("STUB LIGHT", stopped.stdout)

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
        for env in ({"FULL": "1"}, {"CI": "true"}, {"CHECK_ONLY": "phase02"}, {"PORTAL_CHECK": "1"},
                    {"CHECK_AUDIT_FAILS": "1"}):
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


# ---- changed_kind.py on example path lists, and the light path (light_checks.sh)

MAP = changed_kind.MAP
# The Start menu's labels shortened and two presets added, nothing else in the map
START_MENU_PRESETS = [
    {"label": "Schematic", "focus": "docs/ops/schematic-system-draft.svg", "up": 3, "down": 1},
    {"label": "Layout Editor", "focus": "tools/schematic/build_layout_le.py", "up": 1, "down": 2},
    {"label": "tables.xml", "focus": "jmri/layouts/hart/output/tables.xml", "up": 2, "down": 1},
]


class Kinds(unittest.TestCase):
    def test_docs_only(self):
        self.assertEqual(kind_of(["wiki/STATUS.md", "docs/INDEX.md", "tools/README.md", "www/notes.md"]), "docs")

    def test_only_markdown_counts(self):
        # other file types under wiki/ or docs/ are read by full-run checks (tracked-policy, page builders)
        self.assertEqual(kind_of(["wiki/img/a.png"]), "full")
        self.assertEqual(kind_of(["docs/wiring/bench/x.csv"]), "full")
        self.assertEqual(kind_of(["docs/x.json", "wiki/a.md"]), "full")

    def test_mixed_is_full(self):
        self.assertEqual(kind_of(["wiki/STATUS.md", "tools/check.sh"]), "full")

    def test_agent_rules_are_full(self):
        for p in ("AGENTS.md", "CLAUDE.md", "cats/AGENTS.md", ".claude/skills/x/SKILL.md", ".claude/agents/a.md"):
            self.assertEqual(kind_of([p]), "full", p)

    def test_everything_under_claude_is_full(self):
        # check_stamps declares .claude/**/* for the unit suites, and the docs path runs none of them
        for p in (".claude/commands/done.md", ".claude/hooks/a.md", ".claude/a.md", ".claude/skills/x/run.sh",
                  ".claude/skills/x/notes/a.md", ".claude/agents/a.json", ".claude/settings.json"):
            self.assertEqual(kind_of([p]), "full", p)
        v = changed_kind.verdict([".claude/commands/done.md"])
        self.assertEqual("full: .claude/commands/done.md is under .claude/, where every file is code, JMRI or CATS "
                         "data, or agent rules", v.line)

    def test_pipeline_map_is_full_without_a_base_to_compare(self):
        self.assertEqual(kind_of([MAP]), "full")
        self.assertEqual(kind_of(["docs/pipeline-map/x.md"]), "full")

    def test_python_is_full(self):
        self.assertEqual(kind_of(["tools/ci/changed_kind.py"]), "full")

    def test_empty_is_full(self):
        self.assertEqual(kind_of([]), "full")
        self.assertEqual(kind_of(["", "\n"]), "full")

    def test_not_a_prefix_trick(self):
        self.assertEqual(kind_of(["wikipedia/x.py"]), "full")
        self.assertEqual(kind_of(["docsx/a.py"]), "full")

    def test_git_quoted_path_is_full(self):
        self.assertEqual(kind_of(['"wiki/caf\\303\\251.md"']), "full")

    def test_cli(self):
        script = ROOT / "tools" / "ci" / "changed_kind.py"
        out = subprocess.run([sys.executable, str(script)], input="wiki/a.md\n", capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "docs")


class RealDeclarations(unittest.TestCase):
    """Example paths against the repo's own checks.toml, stamp declarations, live_paths.txt and map."""
    d: changed_kind.Declarations

    @classmethod
    def setUpClass(cls) -> None:
        cls.d = changed_kind.load_declarations()

    def why(self, paths: list[str]) -> changed_kind.Verdict:
        return changed_kind.verdict(paths, load=lambda _root: self.d)

    def test_each_example_is_full_with_its_reason(self) -> None:
        for paths, reason in (
            (["www/data/crew.json"], "is written by"),                 # a built www/data JSON
            (["www/data/site.json"], "is read by check.sh job portal"),  # a hand-kept one the site build reads
            ([FIELD_MASTER], "is under jmri/"),   # a CSV master
            (["tools/hosts/pi/settings.json"], "ships to the layout hosts"),    # under a live_paths.txt folder
            (["tools/hosts/live_paths.txt"], "may be read by unit-"),            # the list itself: tests read it
            (["tools/ci/changed_kind.py"], "is code or configuration (.py)"),
            (["tools/pipeline/checks.toml"], "is code or configuration (.toml)"),
            (["wiki/a.md", "media/photo.jpg"], "is not a data file"),
            (["notes/x.txt"], "is in no box of"),
        ):
            with self.subTest(paths):
                v = self.why(paths)
                self.assertEqual("full", v.kind, v.why)
                self.assertIn(reason, v.why)
                self.assertEqual((), v.jobs)

    def test_static_jobs_are_make_static_s(self) -> None:
        lines = subprocess.run([sys.executable, str(ROOT / "tools/pipeline/manifest.py"), "jobs", "check", "--group",
                                "static"], capture_output=True, text=True, check=True).stdout.splitlines()
        want = [ln.split()[0] for ln in lines if not ln.startswith("panels-")]
        self.assertEqual(want, list(self.d.static))

    def test_public_text_reads_everything_and_is_on_the_docs_path(self) -> None:
        self.assertTrue(self.d.jobs["public-text"].on_light_path)
        self.assertIn("**/*", self.d.jobs["public-text"].patterns)
        self.assertFalse(self.d.jobs["portal"].on_light_path)
        self.assertFalse(self.d.jobs["mypy"].on_light_path)

    def test_unit_declarations_match_as_the_stamps_match_them(self) -> None:
        # the unit jobs' patterns go through manifest.covers here; on plain repo paths it must agree with the
        # stamps' own glob rule (panel_stamps), on every declared pattern
        paths = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True,
                               check=True).stdout.splitlines()
        paths += [".claude/skills/x/SKILL.md", "a.md", "x/y/z.md", "AGENTS.md.bak"]
        plain = [p for p in paths if changed_kind.plain(p) == p]
        pats = sorted({pat for v in self.d.units.values() for pat in v})
        self.assertTrue(pats)
        differ = [(pat, p) for pat in pats for p in plain if self.d.covers(pat, p) != _glob(p, pat)]
        self.assertEqual([], differ[:5])


class StandIns(unittest.TestCase):
    """The light rules one at a time, on declarations made up for the test."""

    def decl(self, **over) -> changed_kind.Declarations:
        base = dict(
            jobs={"lint": changed_kind.JobDecl(("data/a.csv",), True),
                  "panels-x": changed_kind.JobDecl(("data/a.csv",), True),
                  "public-text": changed_kind.JobDecl(("**/*",), True),
                  "portal": changed_kind.JobDecl(("site/**",), False)},
            static=("lint", "other"), units={"unit-guards": ("tools/**/*",)}, live=("ship",),
            nodes=[{"id": "data", "path": "data", "kind": "structured"},
                   {"id": "site", "path": "site", "kind": "output"},
                   {"id": "built.csv", "path": "built.csv", "kind": "output"},
                   {"id": "make.py", "path": "make.py", "kind": "generator"},
                   {"id": "ship", "path": "ship", "kind": "structured"},
                   {"id": "tools", "path": "tools", "kind": "unstructured"}],
            edges=[{"from": "make.py", "to": "built.csv"}, {"from": "data", "to": "make.py"},
                   {"from": "make.py", "to": "data", "side": "pointer"}],
            covers=_covers)
        base.update(over)
        return changed_kind.Declarations(**base)

    def test_a_data_file_only_static_checks_read_is_light_and_runs_its_panels_job(self) -> None:
        v = changed_kind.verdict(["data/a.csv", "wiki/x.md"], load=lambda _r: self.decl())
        self.assertEqual("light", v.kind, v.why)
        self.assertEqual(("lint", "other", "panels-x"), v.jobs)

    def test_each_rule_makes_it_full(self) -> None:
        for path, reason in (("ship/a.json", "ships to the layout hosts"), ("built.csv", "is written by make.py"),
                             ("site/a.json", "is read by check.sh job portal"), ("tools/a.json", "unit-guards"),
                             ("elsewhere/a.json", "is in no box of")):
            with self.subTest(path):
                v = changed_kind.verdict([path], load=lambda _r: self.decl())
                self.assertEqual("full", v.kind)
                self.assertIn(reason, v.why)

    def test_declarations_that_cannot_be_read_make_it_full(self) -> None:
        def broken(_root):
            raise ValueError("no manifest")
        v = changed_kind.verdict(["data/a.csv"], load=broken)
        self.assertEqual(("full", "the declarations cannot be read (ValueError: no manifest)"), (v.kind, v.why))

    def test_code_is_full_before_any_declaration_is_read(self) -> None:
        def never(_root):
            raise AssertionError("read")
        self.assertEqual("full", changed_kind.verdict(["data/a.py"], load=never).kind)


def _covers(pattern: str, path: str) -> bool:
    sys.path.insert(0, str(ROOT / "tools" / "pipeline"))
    import manifest
    return manifest.covers(pattern, path)


def _glob(path: str, pattern: str) -> bool:
    sys.path.insert(0, str(ROOT / "tools" / "audit"))
    import check_stamps
    return check_stamps.ps._glob_match(path, pattern)


class PipelineMap(unittest.TestCase):
    """The map is light when only its presets change, compared with the base copy in git."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "test")
        self.map = self.repo / MAP
        self.map.parent.mkdir(parents=True)
        shutil.copy(ROOT / MAP, self.map)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        self.graph = json.loads(self.map.read_text(encoding="utf-8"))
        self.d = changed_kind.load_declarations()

    def edit(self, **changes) -> changed_kind.Verdict:
        self.map.write_text(json.dumps({**self.graph, **changes}, indent=1), encoding="utf-8")
        return changed_kind.verdict([MAP], root=self.repo, compare="HEAD", load=lambda _r: self.d)

    def test_start_menu_presets_only_is_light_and_runs_the_map_check(self) -> None:
        v = self.edit(presets=START_MENU_PRESETS + self.graph["presets"][1:])
        self.assertEqual("light", v.kind, v.why)
        self.assertIn("pipeline-map", v.jobs)
        self.assertEqual(self.d.static, v.jobs[:len(self.d.static)])

    def test_a_box_label_or_any_other_key_is_full(self) -> None:
        nodes = [dict(n) for n in self.graph["nodes"]]
        nodes[0]["label"] = "renamed"
        for changes, key in (({"nodes": nodes}, "'nodes'"), ({"updated": "2099-01-01"}, "'updated'"),
                             ({"presets": [], "edges": []}, "'edges'")):
            with self.subTest(key):
                v = self.edit(**changes)
                self.assertEqual("full", v.kind)
                self.assertIn(f"it changes {key}", v.why)

    def test_a_map_whose_keys_do_not_change_is_full(self) -> None:
        # the same JSON, laid out another way: not a presets change, so not the light case
        v = self.edit()
        self.assertNotEqual((ROOT / MAP).read_text(encoding="utf-8"), self.map.read_text(encoding="utf-8"))
        self.assertEqual("full", v.kind)
        self.assertIn("its keys are the base's, presets included", v.why)

    def test_map_display_only(self) -> None:
        base = json.dumps({"nodes": [], "presets": [1]})
        self.assertIsNone(changed_kind.map_display_only(base, json.dumps({"nodes": [], "presets": [2]})))
        self.assertIn("its keys are the base's", changed_kind.map_display_only(base, base) or "")
        self.assertIn("it changes 'nodes'", changed_kind.map_display_only(base, json.dumps({"presets": [1]})) or "")
        self.assertEqual("the map is gone", changed_kind.map_display_only(base, None))
        self.assertEqual("a copy of the map is not a JSON object", changed_kind.map_display_only("[]", base))

    def test_no_base_copy_or_bad_json_is_full(self) -> None:
        self.assertIn("no base copy", changed_kind.verdict([MAP], root=self.repo, compare=None,
                                                           load=lambda _r: self.d).why)
        self.map.write_text("{", encoding="utf-8")
        v = changed_kind.verdict([MAP], root=self.repo, compare="HEAD", load=lambda _r: self.d)
        self.assertEqual("full", v.kind)
        self.assertIn("not JSON", v.why)


class LightCli(unittest.TestCase):
    SCRIPT = ROOT / "tools/ci/changed_kind.py"

    def cli(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.SCRIPT), *args], input=stdin, capture_output=True, text=True,
                              timeout=60)

    def test_why_and_jobs(self) -> None:
        done = self.cli("--why", stdin="tools/x.py\n")
        self.assertEqual("full: tools/x.py is code or configuration (.py)\n", done.stdout)
        done = self.cli("--jobs", stdin="tools/x.py\n")
        self.assertEqual(1, done.returncode)
        self.assertIn("not a light change: full: tools/x.py", done.stderr)
        self.assertEqual("", done.stdout)

    def test_usage_errors(self) -> None:
        for args in (("--git", "--compare", "HEAD"), ("--git", "--why"), ("--compare", "-x")):
            with self.subTest(args):
                done = self.cli(*args)
                self.assertEqual(2, done.returncode)
                self.assertNotIn("Traceback", done.stderr)


# light_checks.sh in a scratch tree, beside stand-ins for what it runs
STUB_KIND = 'import os, sys\nif os.environ.get("STUB_JOBS") is None: sys.exit("not light")\nprint(os.environ["STUB_JOBS"])\n'
STUB_CHECK = '#!/usr/bin/env bash\necho "STUB CHECK.SH CHECK_ONLY=$CHECK_ONLY"\necho "$CHECK_PASS_LINE"\nexit "${STUB_CHECK_RC:-0}"\n'
STUB_DOCS = '#!/usr/bin/env bash\necho "STUB DOCS"\nexit "${STUB_DOCS_RC:-0}"\n'


class LightChecks(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for rel, text in (("tools/ci/light_checks.sh", (ROOT / "tools/ci/light_checks.sh").read_text()),
                          ("tools/ci/changed_kind.py", STUB_KIND), ("tools/check.sh", STUB_CHECK),
                          ("tools/ci/docs_checks.sh", STUB_DOCS)):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text)
        (self.root / "tools/check.sh").chmod(0o755)

    def run_light(self, **env: str) -> subprocess.CompletedProcess:
        base = {k: v for k, v in os.environ.items() if not k.startswith(("STUB_", "CHECK_"))}
        return subprocess.run(["bash", str(self.root / "tools/ci/light_checks.sh"), "--git"], env={**base, **env},
                              capture_output=True, text=True, timeout=60)

    def test_runs_the_jobs_then_the_docs_checks_and_ends_light(self) -> None:
        done = self.run_light(STUB_JOBS="lint\npipeline-map")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertIn("STUB CHECK.SH CHECK_ONLY=^(lint|pipeline-map)$", lines)
        self.assertIn("--- light: check.sh's jobs passed", lines)
        self.assertIn("STUB DOCS", lines)
        self.assertNotIn("ALL PASSED", done.stdout)
        self.assertTrue(lines[-1].startswith("LIGHT CHECKS PASSED"), lines[-1])

    def test_a_failure_in_either_fails_after_both_ran(self) -> None:
        for env, named in (({"STUB_CHECK_RC": "1"}, "check.sh jobs"), ({"STUB_DOCS_RC": "1"}, "quick docs checks")):
            with self.subTest(named):
                done = self.run_light(STUB_JOBS="lint", **env)
                self.assertEqual(1, done.returncode)
                self.assertIn("STUB DOCS", done.stdout)
                self.assertIn(f"light checks FAILED: {named}", done.stdout)
                self.assertEqual("FAILED", done.stdout.splitlines()[-1])

    def test_no_job_list_stops_before_any_check(self) -> None:
        for env in ({}, {"STUB_JOBS": ""}):
            with self.subTest(env):
                done = self.run_light(**env)
                self.assertEqual(2, done.returncode)
                self.assertIn("STOP:", done.stdout)
                self.assertNotIn("STUB", done.stdout)


if __name__ == "__main__":
    unittest.main()
