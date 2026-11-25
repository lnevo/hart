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
import portal_inputs  # noqa: E402

manifest = check_stamps.pm      # tools/pipeline/manifest.py, as the stamps load it

# check.sh's variables that pick a path; the tests start each run without them.
PATH_VARS = ("CI", "FULL", "CHECK_ONLY", "CHECK_AUDIT", "HART_TABLES", "PORTAL_CHECK", "CHECK_RECORD_TO",
             "CHECK_SKIP_FROM", "CHECK_SKIP_NOTE", "PYTHONPATH")
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
        for env in ({"FULL": "1"}, {"CI": "true"}, {"CHECK_ONLY": "static"}, {"PORTAL_CHECK": "1"}):
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
        self.assertIn('bash tools/ci/docs_checks.sh', (ROOT / "tools/check.sh").read_text(encoding="utf-8"))

    def test_each_docs_check_is_also_in_the_full_run(self) -> None:
        """The docs path skips the full run, so its checks must be ones the full run makes too: the manifest's
        docs-only steps, each in the static group or a job of its own that check.sh always queues (not the portal
        build, which check.sh runs only where its inputs are)."""
        docs = manifest.select(manifest.load(), "check", docs_only=True)
        self.assertGreaterEqual(len(docs), 8)
        for step in docs:
            with self.subTest(step.name):
                self.assertTrue(step.group == "static" or (not step.group and step.name != "portal"))
        text = (ROOT / "tools/ci/docs_checks.sh").read_text(encoding="utf-8")
        self.assertIn("python3 tools/pipeline/manifest.py jobs check --docs-only", text)
        by_hand = [line for line in text.splitlines() if line.startswith("check ") and " -m unittest " not in line]
        self.assertEqual([], by_hand, "a docs check listed by hand: mark its step docs_only in tools/pipeline/checks.toml")

    def test_docs_checks_runs_every_check_and_fails_when_one_did(self) -> None:
        docs = manifest.select(manifest.load(), "check", docs_only=True)
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "tools/ci").mkdir(parents=True)
            shutil.copy(ROOT / "tools/ci/docs_checks.sh", repo / "tools/ci/docs_checks.sh")
            (repo / "lines").write_text("".join(manifest.shell_line(s) + "\n" for s in docs))
            bin_dir = repo / "bin"
            bin_dir.mkdir()
            # a python3 that answers the manifest's docs-only lines, logs each other script and fails the ai-speak
            # check only
            (bin_dir / "python3").write_text(
                '#!/usr/bin/env bash\n'
                f'if [[ "$1" == tools/pipeline/manifest.py ]]; then cat "{repo}/lines"; exit 0; fi\n'
                'echo "ran $1"\n[[ "$1" != *check_ai_speak.py ]]\n')
            (bin_dir / "python3").chmod(0o755)
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
            env.pop("HOPS_PY", None)
            done = subprocess.run(["bash", str(repo / "tools/ci/docs_checks.sh")], env=env, capture_output=True,
                                  text=True, timeout=30)
            self.assertEqual(1, done.returncode)
            self.assertEqual(len(docs) + len(docs_unit_tests()), len(re.findall(r"^ran ", done.stdout, re.M)),
                             done.stdout)
            self.assertIn("quick docs checks FAILED: ai-speak", done.stdout)


# check.sh's unit job kinds by test folder (tools/check.sh), for the stamp names of the tests docs_checks.sh runs.
KIND_BY_DIR = {"tools/audit/tests": "unit-guards", "tools/hosts/tests": "unit-hosts",
               "tools/schematic/tests": "unit-schematic", "jmri/layouts/hart/scripts/tests": "unit-jmri"}
UNIT_LINE = re.compile(r"^check (?P<name>\S+) python3 -m unittest discover -b -q -s (?P<dir>\S+) -p (?P<file>test\w*\.py)"
                       r"(?: -k (?P<k>\S+))?$")
# The stamp declarations (tools/audit/check_stamps.py) that cover Markdown under docs/ or wiki/ but whose tests the
# docs-only path leaves out, each with why (owner, 2026-11-24: a short list; whole suites that only partly read docs
# stay out). A new or changed declaration on docs/ or wiki/ fails below until docs_checks.sh runs it or it is listed.
LEFT_OUT = {
    "static": "its checks that read docs are in docs_checks.sh's list; stays one job (owner, 2026-11-24)",
    "public-text": "check_public_text.py is in docs_checks.sh's list",
    "portal": "the portal build stays with the website deploy, as in CI (owner, 2026-11-24)",
    "unit-portal": "whole suite of site builders (39 s); reads docs/ops and docs/wiring only as page sources",
    "unit-hart-ops": "whole suite (car cards, publications); reads docs only in part",
    "unit-schematic": "whole suite; reads wiki/pipelines/ only in part",
    "unit-anyrail": "whole suite; reads docs/ only for the track plan article",
    "unit-hosts test_deploy_stage": "stages a deploy (36 s); copies one docs/jmri/ CSV, reads no Markdown",
    "unit-guards test_check_stamps": "the stamp machinery's own tests (38 s); declared on its sample jobs' "
                                     "declarations (RUNS_JOBS), docs/ through unit-anyrail's",
    "unit-guards test_hart_tables_writers": "runs each table writer only to see it refuse to write under "
                                            "HART_TABLES; status_counts.py reads wiki/STATUS.md on the way",
    "unit-guards test_jmri_process_patterns": "reads the .sh, .ps1 and .py files git lists, docs/ included; no Markdown",
    "unit-guards test_pipeline_map": "its real-map tests read the graph and the pages, which only a full-path change "
                                     "(docs/pipeline-map/) alters; both pages are the pipeline-map check",
    "unit-guards test_pipeline_map_coverage": "the agent docs it checks are .claude/ and AGENTS.md files: full path",
    "unit-guards test_docs_index": "builds fake docs trees; the real index is the docs-index check",
    "unit-guards test_agent_docs_map": "its one test on the real wiki (the committed graph is current) is what the "
                                       "pipeline-map check's build_pipeline_map.py --check also fails on",
    "unit-guards test_map_lane": "its tests on the real map (the committed graph is current, a hand edit fails) are "
                                 "what the pipeline-map check's build_pipeline_map.py --check also fails on",
    "unit-guards test_agent_docs_cells": "its runs of check_agent_docs.py on the real wiki and AGENTS.md are what "
                                         "the agent-docs check in docs_checks.sh's list checks",
    "unit-guards test_status_merge": "its one test on the real wiki/STATUS.md (no doubled entries) is what the "
                                     "status-counts check in docs_checks.sh's list also fails on",
    "unit-guards test_helix_stl_index": "lists the docs/benchwork/helix/stl/ models, no Markdown",
    "unit-guards test_publish_draft": "reads docs/ops/ drawings and JSON, no Markdown",
    "unit-guards test_write_inventory": "reads docs/wiring/ CSV, no Markdown",
    "unit-hosts test_live_paths": "reads the docs/ paths the deploy scripts name, not Markdown text",
    "unit-jmri test_infer_block_lengths": "reads docs/jmri/ data files, no Markdown",
    "unit-jmri test_speedmatch": "reads docs/jmri/ data files (block_events.csv), no Markdown",
    "unit-jmri test_speedmatch_dashboard": "reads docs/jmri/ data files, no Markdown",
    "unit-jmri test_speedmatch_publish_live": "reads docs/jmri/ data files, no Markdown",
    "unit-jmri test_speedmatch_site_export": "reads docs/jmri/ and www/ai/ data files, no Markdown",
}


def docs_unit_tests() -> dict[str, re.Match]:
    """docs_checks.sh's unit test lines by stamp name ("unit-guards test_name_copies")."""
    found = {}
    for line in (ROOT / "tools/ci/docs_checks.sh").read_text(encoding="utf-8").splitlines():
        if line.startswith("check ") and " -m unittest" in line:
            m = UNIT_LINE.match(line)
            if m is None or m["dir"] not in KIND_BY_DIR:
                raise AssertionError(f"docs_checks.sh: a unit test line not in the form the guard reads: {line}")
            found[f"{KIND_BY_DIR[m['dir']]} {m['file'].removesuffix('.py')}"] = m
    return found


def covers_markdown_docs(patterns: tuple[str, ...]) -> bool:
    """Whether a stamp declaration covers a Markdown file under docs/ or wiki/, matched by the stamps' own rule
    (panel_stamps._glob_match). Each docs/ or wiki/ pattern is probed with a path made from its own segments, a
    wildcard segment named "x" and the last one "x.md"."""
    probes = {"docs/x.md", "wiki/x.md"}
    for p in patterns:
        if p.startswith(("docs/", "wiki/")):
            parts = ["x" if "*" in part else part for part in p.split("/")]
            if not parts[-1].endswith(".md"):
                parts[-1] = "x.md"
            probes.add("/".join(parts))
    return any(check_stamps.ps._glob_match(probe, p) for p in patterns for probe in probes)


def check_sh_list(name: str) -> set[str]:
    """The names in one of check.sh's space-separated lists (SLOW, BY_CLASS, LE_TESTS), every assignment added up."""
    text = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
    found = re.findall(rf'^\s*(?:\[\[[^\]]*\]\]\s*\|\|\s*)?{name}\+?="([^"]*)"', text, re.M)
    if not found:
        raise AssertionError(f"tools/check.sh: no {name}= list")
    return {w for words in found for w in words.split()}


class DocsUnitTests(unittest.TestCase):
    """The unit tests docs_checks.sh runs follow the stamp declarations of what reads docs (tools/audit/check_stamps.py)."""

    def test_each_listed_test_is_declared_on_docs_and_named_for_its_file(self) -> None:
        tests = docs_unit_tests()
        self.assertGreaterEqual(len(tests), 2)
        for stamp, m in tests.items():
            with self.subTest(stamp):
                self.assertTrue((ROOT / m["dir"] / m["file"]).is_file())
                self.assertEqual(stamp.replace(" ", "-"), m["name"])
                extra = check_stamps.EXTRA.get(stamp)
                self.assertIsNotNone(extra, f"{stamp}: check_stamps.EXTRA does not say it reads docs or the wiki")
                self.assertTrue(covers_markdown_docs(extra), f"{stamp}: its declaration covers no Markdown doc")
                self.assertNotIn(stamp, LEFT_OUT)
                # check.sh runs these files under another job name (the Layout Editor job, one job per class)
                self.assertNotIn(m["file"].removesuffix(".py"), check_sh_list("LE_TESTS"))
                self.assertNotIn(m["file"], check_sh_list("BY_CLASS"))

    def test_each_k_filter_names_a_test_class_of_its_file(self) -> None:
        for stamp, m in docs_unit_tests().items():
            if m["k"] is None:
                continue
            with self.subTest(stamp):
                done = subprocess.run([sys.executable, str(ROOT / "tools/audit/test_classes.py"),
                                       str(ROOT / m["dir"] / m["file"])], capture_output=True, text=True, timeout=60)
                self.assertEqual(0, done.returncode, done.stderr)
                classes = {c.split(".")[-1] for c in done.stdout.split()}
                self.assertIn(m["k"].split(".")[0], classes, f"-k {m['k']} names no test class of {m['file']}")

    def test_every_declaration_on_markdown_docs_is_run_or_left_out_with_a_reason(self) -> None:
        # a job that runs other jobs (RUNS_JOBS) is declared on theirs too: its whole declaration
        declared = {**check_stamps.BY_KIND, **check_stamps.EXTRA,
                    **{k: check_stamps.declared(k) for k in check_stamps.RUNS_JOBS}}
        on_docs = {k for k, v in declared.items() if covers_markdown_docs(v)}
        handled = set(docs_unit_tests()) | set(LEFT_OUT)
        self.assertEqual([], sorted(on_docs - handled), "declared on docs/ or wiki/: run it in docs_checks.sh or "
                                                        "add it to LEFT_OUT with the reason")
        self.assertEqual([], sorted(set(LEFT_OUT) - on_docs), "LEFT_OUT names a job no longer declared on docs")

    def test_the_probe_reads_patterns_as_the_stamps_do(self) -> None:
        self.assertTrue(covers_markdown_docs(("**/*",)))
        self.assertTrue(covers_markdown_docs(("docs/jmri/**/*",)))
        self.assertTrue(covers_markdown_docs(("docs/INDEX.md",)))
        self.assertFalse(covers_markdown_docs(("**/*.py", "www/**/*", "tools/**/*")))
        self.assertFalse(covers_markdown_docs(("docs/x.json",)))
        self.assertTrue(covers_markdown_docs(("docs/jmri/*/**/*",)))     # a wildcard segment in the middle
        self.assertTrue(covers_markdown_docs(("wiki/*/notes/*.md",)))

    def test_check_sh_lists_are_read(self) -> None:
        self.assertIn("test_build_layout_le", check_sh_list("LE_TESTS"))
        self.assertIn("test_worktrees.py", check_sh_list("BY_CLASS"))
        self.assertIn("test_deploy_gates.py", check_sh_list("BY_CLASS"))
        with self.assertRaisesRegex(AssertionError, "no NOPE= list"):
            check_sh_list("NOPE")

    def test_a_unit_line_in_another_form_fails_the_guard(self) -> None:
        bad = "check x python3 -m unittest tools/audit/tests/test_name_copies.py\n"
        with mock.patch.object(Path, "read_text", return_value=bad):
            with self.assertRaisesRegex(AssertionError, "not in the form the guard reads"):
                docs_unit_tests()


if __name__ == "__main__":
    unittest.main()
