"""tools/pipeline/manifest.py: what the loader refuses and how it says so, the shell lines it prints, the per-job
digests and git refs the stamps key on, and tools/check.sh and tools/ci/docs_checks.sh running what it lists (in
scratch repos with a stand-in manifest.py): a manifest that fails or lists nothing stops them, each step is a job of
its own, and check.sh's own conditions (the panels jobs first, when the portal job runs) still apply.

Split for size on 2026-11-26: the loader's refusals of a step are in test_pipeline_manifest_refusals.py and check.sh
on the stand-in manifest in test_pipeline_manifest_check_sh.py. Both import their helpers from here. The tests that
read this repo's map stay here, as the stamp of this file's job lists the map as an input (tools/audit/check_stamps.py
EXTRA)."""
from __future__ import annotations

import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("pipeline_manifest", ROOT / "tools/pipeline/manifest.py")
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M          # its dataclasses look their module up while the class is made
SPEC.loader.exec_module(M)

TRACKED = {"tools/a.py", "tools/b.sh", "lib/src/pkg/mod.py", "lib/src/pkg/__init__.py", "data/x.csv",
           "data/sub/y.csv", "www/index.html"}
GRAPH = {"domains": [{"id": "layout"}, {"id": "website"}],
         "nodes": [{"id": "media", "path": "media", "local": True}, {"id": "ext:x", "path": ""}], "edges": []}
REPO = M.repo_from(TRACKED, GRAPH)
GOOD = '''
[[step]]
name = "one"
runner = "check"
group = "static"
cmd = ["python3", "tools/a.py", "--check"]
git = ["head", "base"]
domain = "layout"
label = "a.py"
desc = "First."
docs_only = true
inputs = ["data/x.csv", { path = "data/sub", label = "reads", side = "check" }]
outputs = ["www/index.html"]
'''


def parse(text: str, where=REPO):
    return M.parse(tomllib.loads(text), "t.toml", where)


def step(**fields) -> str:
    """GOOD's step with fields replaced (a value of None drops the field), as TOML."""
    base = {"name": '"one"', "runner": '"check"', "cmd": '["python3", "tools/a.py"]', "domain": '"layout"',
            "label": '"a.py"', "desc": '"First."', "git": "[]"}
    base.update(fields)
    return "[[step]]\n" + "".join(f"{k} = {v}\n" for k, v in base.items() if v is not None)


class DeclarationsTest(unittest.TestCase):
    """manifest.declarations, covers and undeclared: what the trace audit (check_stamps.step_reads) compares a
    job's reads with."""
    TEXT = (step(name='"a"', group='"static"', inputs='["data/sub", { path = "data/x.csv", label = "l" }]',
                 outputs='["www/index.html"]', quiet_inputs='["lib/*.txt"]')
            + step(name='"b"', group='"static"', cmd='["env", "PYTHONPATH=lib/src", "python3", "-m", "pkg.mod", "x"]')
            + step(name='"p"', group='"static"', cmd='["bash", "tools/b.sh", "--check"]')
            + step(name='"r"', cmd='["python3", "tools/r.py"]', programs='{ ruff = ["**/*.py", "ruff.toml"] }'))

    def decls(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "checks.toml"
            p.write_text(text, encoding="utf-8")
            return M.declarations(p)

    def test_one_job_per_step_with_its_patterns(self) -> None:
        d = self.decls(self.TEXT)
        self.assertEqual(list(d), ["a", "b", "p", "r"])
        self.assertEqual({len(steps) for steps in d.values()}, {1})
        (a,), (b,), (p,), (r,) = d.values()
        self.assertEqual((a.name, a.python, a.script), ("a", True, "tools/a.py"))
        self.assertEqual(a.patterns, ("data/sub", "data/x.csv", "www/index.html", "lib/*.txt"))
        self.assertEqual(b.script, "lib/src/pkg/mod.py")
        self.assertFalse(p.python)
        self.assertEqual(r.patterns, ("**/*.py", "ruff.toml"))

    def test_undeclared(self) -> None:
        a = self.decls(self.TEXT)["a"][0]
        reads = ["data/sub/y.csv", "data/x.csv", "www/index.html", "lib/n.txt", "tools/fixture.json", "jmri/x.py",
                 "data/subway.csv", "lib/deep/n.txt", "wiki/STATUS.md", "wiki/STATUS.md"]
        # a data file under tools/ and a .py file read as data are reads like any other (the code a job imported or
        # ran never reaches undeclared: check_stamps.step_reads leaves it out by the trace's "c" lines)
        self.assertEqual(M.undeclared(a, reads), ["data/subway.csv", "jmri/x.py", "lib/deep/n.txt",
                                                  "tools/fixture.json", "wiki/STATUS.md"])
        self.assertEqual(M.undeclared(a, ["tools/a.py"]), [])          # its own script

    def test_errors_are_manifest_errors(self) -> None:
        for text, why in ((step(cmd='"python3 tools/a.py"'), "cmd: not a list of words"),
                          (step(cmd='["python3"]'), "cmd: runs nothing"),
                          (step(inputs='"data/x.csv"'), "inputs: not a list"),
                          (step(outputs='[{ label = "x" }]'), "outputs: None is not a path"),
                          (step(quiet_inputs='["/abs"]'), "quiet_inputs: /abs is not a path from the repo root"),
                          (step(programs='{ ruff = "x" }'), "programs: not a table"),
                          (step(programs='{ ruff = ["../x"] }'), "programs: ../x has an empty"),
                          (step(name='"a"') + step(name='"a"'), "two steps named 'a'"),
                          ("", "no \\[\\[step\\]\\]")):
            with self.subTest(why=why):
                with self.assertRaisesRegex(M.ManifestError, why):
                    self.decls(text)

    def test_two_steps_running_the_same_words_are_two_jobs(self) -> None:
        text = step(name='"a"', group='"static"') + step(name='"b"', group='"static"')
        self.assertEqual(list(self.decls(text)), ["a", "b"])

    def test_this_repo(self) -> None:
        d = M.declarations()
        self.assertEqual(set(d), set(M.job_keys()))
        steps = {s.name: s for s in M.load()}
        panels = {M.PANEL_JOB_PREFIX + s.name: s for s in M.panel_steps()}
        for job, decls in d.items():
            for s in decls:
                with self.subTest(step=s.name):
                    full = steps.get(s.name) or panels[s.name]
                    self.assertEqual(s.script, full.script)
                    self.assertEqual(set(s.patterns), {e.path for e in (*full.inputs, *full.outputs)}
                                     | set(getattr(full, "quiet_inputs", ())) | {p for _, g in full.programs for p in g})
                    self.assertEqual(s.unaudited, M.PANELS_UNAUDITED if s.name in panels else "")


class FileAndRepoTest(unittest.TestCase):
    def load_text(self, data: bytes) -> tuple:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "checks.toml"
            p.write_bytes(data)
            return M.load(p, REPO)

    def test_a_file(self) -> None:
        self.assertEqual(self.load_text(GOOD.encode())[0].name, "one")

    def test_unreadable_files_name_the_file(self) -> None:
        with self.assertRaisesRegex(M.ManifestError, r"gone\.toml: cannot read it"):
            M.load(Path("/nonexistent/gone.toml"), REPO)
        with self.assertRaisesRegex(M.ManifestError, r"checks\.toml: not valid TOML: .*line 1"):
            self.load_text(b"[[step]\n")
        with self.assertRaisesRegex(M.ManifestError, r"checks\.toml: not UTF-8"):
            self.load_text(b"\xff\xfe")

    def test_git_failures_are_errors_not_tracebacks(self) -> None:
        failed = subprocess.CompletedProcess(["git"], 128, "", "fatal: not a git repository")
        with mock.patch.object(M.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(M.ManifestError, "git ls-files failed .*not a git repository"):
                M.repo()
        with mock.patch.object(M.subprocess, "run", side_effect=FileNotFoundError("git")):
            with self.assertRaisesRegex(M.ManifestError, "git ls-files could not run"):
                M.repo()
        with mock.patch.object(M.subprocess, "run", return_value=subprocess.CompletedProcess(["git"], 0, "", "")):
            with self.assertRaisesRegex(M.ManifestError, "lists no file"):
                M.repo()

    def test_a_tracked_file_gone_from_the_checkout_does_not_count(self) -> None:
        listed = subprocess.CompletedProcess(["git"], 0, "tools/check.sh\0tools/deleted_not_staged.py\0", "")
        with mock.patch.object(M.subprocess, "run", return_value=listed):
            where = M.repo()
        self.assertEqual(where.files, {"tools/check.sh"})
        with self.assertRaisesRegex(M.ManifestError, "deleted_not_staged.py is not a tracked file"):
            M.parse(tomllib.loads(step(cmd='["python3", "tools/deleted_not_staged.py"]', domain='"extras"')),
                    "t.toml", where)

    def test_a_broken_map_is_an_error(self) -> None:
        graph_map = M.pipeline_map()
        with mock.patch.object(graph_map, "read", side_effect=graph_map.GraphError("the graph is not valid JSON")):
            with self.assertRaisesRegex(M.ManifestError, "pipeline_map.json: the graph is not valid JSON"):
                M.repo()
        with self.assertRaisesRegex(M.ManifestError, "no domains"):
            M.repo_from(TRACKED, {"domains": [], "nodes": []})

    def test_folders_come_from_the_files(self) -> None:
        self.assertEqual(REPO.folders, {"tools", "lib", "lib/src", "lib/src/pkg", "data", "data/sub", "www"})
        self.assertEqual(REPO.local, {"media"})


class OutputTest(unittest.TestCase):
    STEPS = parse(step(name='"a"', group='"static"', docs_only="true")
                  + step(name='"b"', group='"static"', cmd='["env", "PYTHONPATH=lib/src", "python3", "-m", "pkg.mod"]')
                  + step(name='"c"', cmd='["{python}", "tools/a.py", "it\'s $HOME"]'))

    def test_shell_lines(self) -> None:
        a, b, c = (M.shell_line(s) for s in self.STEPS)
        self.assertEqual(a, "a python3 tools/a.py")
        self.assertEqual(b, 'b env PYTHONPATH="lib/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m pkg.mod')
        self.assertEqual(c, 'c "$HOPS_PY" tools/a.py \'it\'"\'"\'s $HOME\'')

    def test_select(self) -> None:
        names = lambda **kw: [s.name for s in M.select(self.STEPS, "check", **kw)]  # noqa: E731
        self.assertEqual(names(), ["a", "b", "c"])
        self.assertEqual(names(group="static"), ["a", "b"])
        self.assertEqual(names(ungrouped=True), ["c"])
        self.assertEqual(names(docs_only=True), ["a"])
        with self.assertRaisesRegex(M.ManifestError, "no check step matches"):
            M.select(self.STEPS[2:], "check", group="static")
        with self.assertRaisesRegex(M.ManifestError, "runner 'panels'"):
            M.select(self.STEPS, "panels")

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = M.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_the_command_line_reports_a_bad_manifest_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.toml"
            p.write_text(step(domain='"nowhere"'))
            for argv in (("check",), ("list",), ("jobs", "check")):
                with self.subTest(argv=argv):
                    rc, out, err = self.run_main("--manifest", str(p), *argv)
                    self.assertEqual((rc, out), (1, ""))
                    self.assertIn("bad.toml: step 'one': domain: 'nowhere' is not a map domain", err)
                    self.assertNotIn("Traceback", err)

    def test_the_command_line_on_this_repo(self) -> None:
        rc, out, err = self.run_main("jobs", "check", "--ungrouped")
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual([line.split()[0] for line in out.splitlines()], ["public-text", "ruff", "mypy", "portal"])
        rc, out, _ = self.run_main("list")
        self.assertEqual(rc, 0)
        self.assertEqual(len(out.splitlines()), len(M.load()))


class ThisRepoTest(unittest.TestCase):
    def test_the_manifest_loads(self) -> None:
        steps = M.load()
        self.assertTrue(steps)
        self.assertTrue(M.select(steps, "check", group="static"))


class JobKeyTest(unittest.TestCase):
    """job_keys: what check.sh's stamps key each manifest job on (tools/audit/check_stamps.manifest_key): every step is
    a job of its own, keyed on its own entry and the git refs it names."""
    TEXT = (step(name='"a"', group='"static"', git='["head", "base"]')
            + step(name='"b"', group='"static"', cmd='["python3", "tools/b.py"]')
            + step(name='"c"') + step(name='"d"', cmd='["python3", "tools/d.py"]'))

    def keys(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "checks.toml"
            p.write_text(text, encoding="utf-8")
            return M.job_keys(p)

    def changed(self, before: str, after: str) -> list[str]:
        old, new = self.keys(before), self.keys(after)
        self.assertEqual(set(old), set(new))
        return sorted(job for job in old if old[job] != new[job])

    def test_one_job_per_step_grouped_or_not(self) -> None:
        keys = self.keys(self.TEXT)
        self.assertEqual(list(keys), ["a", "b", "c", "d"])
        self.assertEqual(keys["a"].git, ("head", "base"))
        self.assertEqual(keys["b"].git, ())

    def test_an_edited_cmd_changes_its_own_job_only(self) -> None:
        self.assertEqual(self.changed(self.TEXT, self.TEXT.replace('"tools/d.py"', '"tools/d.py", "--check"')), ["d"])
        self.assertEqual(self.changed(self.TEXT, self.TEXT.replace('"tools/b.py"', '"tools/b.py", "--check"')), ["b"])

    def test_a_changed_git_field_changes_its_own_job_only(self) -> None:
        self.assertEqual(self.changed(self.TEXT, self.TEXT.replace('git = ["head", "base"]', "git = []")), ["a"])

    def test_the_order_of_the_steps_changes_nothing(self) -> None:
        a, b, c, d = self.TEXT.split("[[step]]\n")[1:]
        self.assertEqual(self.changed(self.TEXT, "".join("[[step]]\n" + x for x in (d, b, c, a))), [])

    def test_comments_and_layout_change_nothing(self) -> None:
        relaid = "# a comment\n" + self.TEXT.replace('desc = "First."', 'desc   =   "First."  # why')
        self.assertEqual(self.changed(self.TEXT, relaid), [])

    def test_any_field_of_the_entry_counts(self) -> None:
        self.assertEqual(self.changed(self.TEXT, self.TEXT.replace('name = "c"\n', 'name = "c"\ndocs_only = true\n')),
                         ["c"])

    def test_errors(self) -> None:
        with self.assertRaisesRegex(M.ManifestError, "gone.toml: cannot read it"):
            M.job_keys(Path("/nonexistent/gone.toml"))
        for text, why in (("", "no \\[\\[step\\]\\]"), (step(name=None), "step 1: no name"),
                          (step(name="1"), "not text"),
                          (step(name='"x"') + step(name='"x"'), "two steps named 'x'"),
                          (step(git=None), "step 'one': git: None must be a list"),
                          (step(git='["tip"]'), "step 'one': git: 'tip': not a ref name"),
                          (step(when="2026-11-25"), "JSON cannot hold")):
            with self.subTest(why=why):
                with self.assertRaisesRegex(M.ManifestError, why):
                    self.keys(text)

    def test_this_repo(self) -> None:
        """Every step is a job, except the panels step: one job per panels.toml step in its place (stage 6)."""
        keys = M.job_keys()
        steps = M.load()
        panels = [M.PANEL_JOB_PREFIX + s.name for s in M.panel_steps()]
        want = [n for s in steps for n in (panels if M.runs_panels(s.cmd) else [s.name])]
        self.assertEqual(list(keys), want)
        self.assertEqual({k: v.git for k, v in keys.items() if k not in panels},
                         {s.name: s.git for s in steps if not M.runs_panels(s.cmd)})
        self.assertNotIn("static", keys)
        self.assertNotIn("panels", keys)


def scratch_check_sh(base: Path):
    """A scratch repo (test_check_docs_only.Scratch) with tools/check.sh and a stand-in tools/pipeline/manifest.py that
    prints $STUB_STATIC, $STUB_OWN or $STUB_DOCS for --group static, --ungrouped and --docs-only, or fails when
    STUB_MANIFEST_FAIL is set; tools/a.py and the panels script print what they were run with."""
    from test_check_docs_only import Scratch       # noqa: PLC0415 - its folder is on sys.path under discover
    s = Scratch(base, with_check_sh=True)
    s.write("tools/pipeline/manifest.py", STUB_MANIFEST)
    s.write("tools/a.py", "import os, sys\nprint('ran', *sys.argv[1:], 'PYTHONPATH=' + os.environ.get('PYTHONPATH', ''))\n")
    s.write("lib/src/pkg/mod.py", "import os\nprint('ran mod PYTHONPATH=' + os.environ.get('PYTHONPATH', ''))\n")
    s.write("tools/p.sh", 'echo "ran shell $*"\n')
    s.commit("stubs")
    git_update = ["git", "-C", str(s.repo), "update-ref", "refs/remotes/origin/main", "HEAD"]
    subprocess.run(git_update, check=True)          # no change on the branch: check.sh takes the full path
    return s


STUB_MANIFEST = '''import os, sys
if os.environ.get("STUB_MANIFEST_FAIL"):
    sys.exit("manifest.py: stub manifest error")
var = {"--group": "STUB_STATIC", "--ungrouped": "STUB_OWN", "--docs-only": "STUB_DOCS"}[sys.argv[3]]
print(os.environ.get(var, ""), end="")
'''
STATIC = "\n".join(("one python3 tools/a.py --check",
                    'two env PYTHONPATH="lib/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m pkg.mod',
                    "panels-tables python3 tools/a.py panels-tables", "shell bash tools/p.sh --check")) + "\n"
STATIC_ONLY = "^(one|two|panels-tables|shell|gone|odd)$"         # the static jobs these tests queue
OWN = "solo python3 tools/a.py solo\nportal python3 tools/a.py portal\n"


class DocsChecksShTest(unittest.TestCase):
    """docs_checks.sh runs the manifest's docs-only lines, then its unit tests; a manifest that fails or lists none
    stops it before any check (python3 here is a stand-in that logs each script; tools/pipeline/manifest.py is
    answered from $STUB_DOCS)."""

    def run_docs(self, **env: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "tools/ci").mkdir(parents=True)
            (repo / "tools/ci/docs_checks.sh").write_text((ROOT / "tools/ci/docs_checks.sh").read_text())
            bin_dir = repo / "bin"
            bin_dir.mkdir()
            (bin_dir / "python3").write_text(
                '#!/usr/bin/env bash\n'
                'if [[ "$1" == tools/pipeline/manifest.py ]]; then\n'
                '  [[ -z "${STUB_MANIFEST_FAIL:-}" ]] || { echo "manifest.py: stub error" >&2; exit 1; }\n'
                '  printf %s "$STUB_DOCS"; exit 0\n'
                'fi\n'
                'if [[ "$1" == tools/ci/docs_unit_tests.py ]]; then\n'
                '  [[ -z "${STUB_UNITS_FAIL:-}" ]] || { echo "docs_unit_tests.py: stub error" >&2; exit 1; }\n'
                '  printf %s "${STUB_UNITS-unit-x python3 -m unittest discover -s t -p test_x.py}"; exit 0\n'
                'fi\n'
                '[[ "$1" != tools/eat.py ]] || cat >/dev/null\n'    # a check that reads its stdin to the end
                'echo "ran $*"\n')
            (bin_dir / "python3").chmod(0o755)
            full = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOPS_PY": "python3", **env}
            return subprocess.run(["bash", str(repo / "tools/ci/docs_checks.sh")], env=full, capture_output=True,
                                  text=True, timeout=30)

    def test_the_docs_only_lines_run_then_the_unit_tests(self) -> None:
        lines = "".join(M.shell_line(s) + "\n" for s in M.select(M.load(), "check", docs_only=True))
        done = self.run_docs(STUB_DOCS=lines)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        ran = re.findall(r"^ran (\S+ ?\S*)", done.stdout, re.M)
        scripts = [s.cmd[1] if s.cmd[1] != "-m" else s.cmd[2] for s in M.select(M.load(), "check", docs_only=True)]
        self.assertEqual([r.split()[0] for r in ran[:len(scripts)]], scripts)
        self.assertTrue(all(r.startswith("-m unittest") for r in ran[len(scripts):]), ran)
        self.assertGreater(len(ran), len(scripts))

    def test_a_manifest_that_fails_or_lists_nothing_runs_nothing(self) -> None:
        for env, said in (({"STUB_MANIFEST_FAIL": "1", "STUB_DOCS": ""}, "jobs check --docs-only failed"),
                          ({"STUB_DOCS": ""}, "--docs-only listed no check"),
                          ({"STUB_DOCS": "\n\n"}, "--docs-only listed no check"),
                          # a run with no unit test to run fails, before any check, as an empty manifest list does
                          ({"STUB_DOCS": "a python3 tools/a.py\n", "STUB_UNITS": ""}, "listed no unit test"),
                          ({"STUB_DOCS": "a python3 tools/a.py\n", "STUB_UNITS": " \n"}, "listed no unit test"),
                          ({"STUB_DOCS": "a python3 tools/a.py\n", "STUB_UNITS_FAIL": "1"},
                           "docs_unit_tests.py failed")):
            with self.subTest(env=env):
                done = self.run_docs(**env)
                self.assertEqual(2, done.returncode)
                self.assertIn(said, done.stdout)
                self.assertNotIn("ran ", done.stdout)

    def test_a_check_that_reads_stdin_does_not_eat_the_lines_after_it(self) -> None:
        done = self.run_docs(STUB_DOCS="eat python3 tools/eat.py\nnext python3 tools/next.py\n")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("ran tools/eat.py", done.stdout)
        self.assertIn("ran tools/next.py", done.stdout)

    def test_a_line_that_will_not_parse_is_a_failure(self) -> None:
        done = self.run_docs(STUB_DOCS="ok python3 tools/a.py\nbad python3 'unclosed\n")
        self.assertEqual(1, done.returncode)
        self.assertIn("ran tools/a.py", done.stdout)
        self.assertIn("quick docs checks FAILED: bad (its line would not parse)", done.stdout)


# The scripts tools/check.sh may name itself: its own machinery (what changed, submodules, the manifest's lines, the
# stamps, test classes, whether the portal runs, the docs-only list, the profile guard, the timings log) and the unit
# test folders.
# A read-only check goes in tools/pipeline/checks.toml, where the map lane and the stamps see it, not here.
CHECK_SH_MACHINERY = {"tools/ci/changed_kind.py", "tools/hosts/profile_tables_guard.sh", "tools/agent/worktrees.py",
                      "tools/ci/docs_checks.sh", "tools/pipeline/manifest.py", "tools/audit/check_stamps.py",
                      "tools/audit/test_classes.py", "tools/audit/portal_inputs.py",
                      "tools/pipeline/step_timings.sh"}
SCRIPT_RE = re.compile(r"[\w$\"{}./*-]*/[\w*.-]*\.(?:py|sh)\b")
TEST_GLOB_RE = re.compile(r'(?:"\$JMRI_TESTS"|[\w/]+/tests)/test\*\.py')
# the only `later` calls with a command of their own: unit()'s, the manifest's static lines (run_line, the panels
# jobs first), its own lines and the placeholders that run nothing (true)
LATER_OK = re.compile(r'later "\$name" env -u HART_TABLES "\$@"$|eval "later \$line"$'
                      r'|later "\$\{line%% \*\}" run_line "\$line"$'
                      r'|later "[^"]* skipped[^"]*" true$')
RUN_OK = re.compile(r"""eval "run_check \$line"' \$\{1\+"\$@"\}'$""")


def check_sh_problems(text: str, manifest_scripts) -> list[str]:
    """Why check.sh runs a check outside the step manifest's loop, or []: a script that is not its machinery or a
    unit test folder, a `run` or `later` with a command of its own, a `unit` job that is no unittest run, or a step's
    script named in check.sh itself."""
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for word in SCRIPT_RE.findall(line):
            path = word.strip('"').removeprefix('"').replace('"$ROOT/', "").replace("$ROOT/", "")
            if path not in CHECK_SH_MACHINERY and not TEST_GLOB_RE.fullmatch(word):
                out.append(f"line {n}: names {path}, which is not check.sh's machinery: {line}")
        if re.match(r"(eval\s+\"?)?run(?:_check)?\s", line) and not RUN_OK.match(line):
            out.append(f"line {n}: a run line outside the manifest's static loop: {line}")
        if re.match(r"(eval\s+\"?)?later\s", line) and not LATER_OK.match(line):
            out.append(f"line {n}: a later line with a command of its own: {line}")
        if re.match(r"unit\s", line) and "-m unittest" not in line:
            out.append(f"line {n}: a unit job that is not a unittest run: {line}")
        for script in manifest_scripts:
            if script in line:
                out.append(f"line {n}: names {script}, a step of tools/pipeline/checks.toml: {line}")
    return out


class CheckShRunsOnlyTheManifestTest(unittest.TestCase):
    """Stage 3 took check.sh out of map coverage (its checks are drawn from the manifest), so a check added to check.sh
    by hand would be drawn nowhere and declared nowhere: check.sh may run read-only checks only from the manifest."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
        cls.scripts = sorted({s.script for s in M.load()})

    def test_check_sh_runs_its_checks_from_the_manifest_only(self) -> None:
        self.assertEqual(check_sh_problems(self.text, self.scripts), [])

    def test_the_guard_sees_what_it_looks_for(self) -> None:
        self.assertIn("eval \"later $line\"", self.text)          # the patterns match the real lines, not nothing
        self.assertTrue(any(RUN_OK.match(raw.strip()) for raw in self.text.splitlines()))
        self.assertGreater(len(self.scripts), 30)

    def test_a_check_added_by_hand_is_caught(self) -> None:
        for added, why in (("run phase03 python3 jmri/scripts/check_x.py", "names jmri/scripts/check_x.py"),
                           ("run phase03 python3 jmri/scripts/check_x.py", "a run line outside"),
                           ('eval "run extra python3 tools/x.py"', "a run line outside"),
                           ("run_check extra python3 tools/x.py", "a run line outside"),
                           ("later extra run_line 'extra python3 tools/x.py'", "a later line with a command"),
                           ("later extra python3 tools/audit/check_x.py", "a later line with a command"),
                           ("later extra true_check", "a later line with a command"),
                           ('python3 tools/audit/check_x.py || fail=1', "names tools/audit/check_x.py"),
                           ('bash "$ROOT/tools/x/check.sh"', "names tools/x/check.sh"),
                           ("unit unit-x python3 tools/x/run_tests.py", "not a unittest run"),
                           (f"  {self.scripts[0]} --check", f"names {self.scripts[0]}, a step")):
            with self.subTest(added=added, why=why):
                problems = check_sh_problems(self.text + "\n" + added + "\n", self.scripts)
                self.assertTrue(any(why in p for p in problems), problems)
        self.assertEqual(check_sh_problems(self.text + "\n# run x python3 tools/x.py\n", self.scripts), [])


if __name__ == "__main__":
    unittest.main()
