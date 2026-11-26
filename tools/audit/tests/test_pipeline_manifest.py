"""tools/pipeline/manifest.py: what the loader refuses and how it says so, the shell lines it prints, the per-job
digests and git refs the stamps key on, and tools/check.sh and tools/ci/docs_checks.sh running what it lists (in
scratch repos with a stand-in manifest.py): a manifest that fails or lists nothing stops them, each step is a job of
its own, and check.sh's own conditions (the panels jobs first, when the portal job runs) still apply."""
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


class Refusing(unittest.TestCase):
    def assertRefused(self, text: str, *parts: str) -> str:
        with self.assertRaises(M.ManifestError) as cm:
            parse(text)
        msg = str(cm.exception)
        for part in parts:
            self.assertIn(part, msg)
        return msg


class LoadTest(Refusing):
    def test_a_good_step(self) -> None:
        (s,) = parse(GOOD)
        self.assertEqual((s.name, s.group, s.script, s.docs_only), ("one", "static", "tools/a.py", True))
        self.assertEqual(s.cmd, ("python3", "tools/a.py", "--check"))
        self.assertEqual(s.git, ("head", "base"))
        self.assertEqual(s.inputs, (M.Edge("data/x.csv"), M.Edge("data/sub", "reads", "check")))
        self.assertEqual(s.outputs, (M.Edge("www/index.html"),))

    def test_the_file_order_is_kept(self) -> None:
        steps = parse(step(name='"b"') + step(name='"a"'))
        self.assertEqual([s.name for s in steps], ["b", "a"])

    def test_no_steps_is_an_error(self) -> None:
        self.assertRefused("", "t.toml", "no [[step]]")
        self.assertRefused("step = []", "no [[step]]")

    def test_only_step_tables(self) -> None:
        self.assertRefused('title = "x"\n' + GOOD, "only [[step]] tables", "title")
        self.assertRefused("step = [1, 2]", "[[step]] tables")
        self.assertRefused('step = "x"', "[[step]] tables")

    def test_names_are_unique_and_plain(self) -> None:
        self.assertRefused(step() + step(), "step 'one': name: also step 1's name")
        self.assertRefused(step(name='"One Two"'), "lower case")
        self.assertRefused(step(name='"static"'), "'static' is a group's name")

    def test_fields(self) -> None:
        self.assertRefused(step(colour='"red"'), "step 'one': colour: not a field")
        self.assertRefused(step(desc=None), "step 'one': desc: missing")
        self.assertRefused(step(label=None), "step 'one': label: missing")
        self.assertRefused(step(label='""'), "label: must be a str with text")
        self.assertEqual(parse(step())[0].label, "a.py")
        self.assertRefused(step(name=None), "step 1: name: missing")
        self.assertRefused(step(docs_only='"yes"'), "docs_only: must be true or false")
        self.assertRefused(step(after_edit="1"), "after_edit: must be true or false")
        self.assertRefused(step(after_edit="true", cmd='["{python}", "tools/a.py"]'), "after_edit: the after-edit hook")
        self.assertEqual(len(parse(step(after_edit="true"))), 1)
        self.assertRefused(step(cmd='"python3 tools/a.py"'), "cmd: must be a list")
        self.assertRefused(step(desc='"  "'), "desc: must be a str with text")
        self.assertRefused(step(runner='"panels"'), "runner: 'panels' is not one of check")
        self.assertRefused(step(group='"fast"'), "group: 'fast'")
        self.assertRefused(step(domain='"ops"'), "domain: 'ops' is not a map domain (layout, website)")

    def test_the_git_refs(self) -> None:
        """Every step says which refs its stamp key holds ([] for none): a step that leaves it out is refused, never
        given a default, and only refs check_stamps can read are taken."""
        self.assertEqual(parse(step(git='["origin", "head"]'))[0].git, ("origin", "head"))
        self.assertEqual(parse(step())[0].git, ())
        self.assertRefused(step(git=None), "step 'one': git: missing")
        self.assertRefused(step(git='"head"'), "git: must be a list")
        self.assertRefused(step(git='["HEAD"]'), "git: 'HEAD': not a ref name (head, base, origin)")
        self.assertRefused(step(git='["head", "head"]'), "names a ref twice")
        self.assertRefused(step(git="[1]"), "must be a list of ref names")

    def test_every_problem_is_listed_with_its_file_step_and_field(self) -> None:
        msg = self.assertRefused(step(domain='"ops"') + step(name='"two"', cmd='["python3", "tools/none.py"]'))
        self.assertEqual(msg.splitlines(), [
            "t.toml: step 'one': domain: 'ops' is not a map domain (layout, website)",
            "t.toml: step 'two': cmd: tools/none.py is not a tracked file (a new script needs git add; a deleted one is gone)",
        ])


class CmdTest(Refusing):
    def test_scripts(self) -> None:
        self.assertEqual(parse(step(cmd='["bash", "tools/b.sh", "--check"]'))[0].script, "tools/b.sh")
        self.assertRefused(step(cmd='["bash", "tools/a.py"]'), "bash runs tools/a.py, not a .sh file")
        self.assertRefused(step(cmd='["python3", "tools/b.sh"]'), "not a .py file")
        self.assertRefused(step(cmd='["python3"]'), "runs nothing")
        self.assertRefused(step(cmd='["python3", "tools"]'), "not a .py file")
        self.assertRefused(step(cmd='["node", "tools/a.py"]'), "runs node")
        self.assertRefused(step(cmd='[]'), "none empty")
        self.assertRefused(step(cmd='["python3", ""]'), "none empty")

    def test_paths_are_from_the_repo_root(self) -> None:
        for bad in ("./tools/a.py", "tools/../tools/a.py", "/tools/a.py", "tools//a.py", "tools\\\\a.py"):
            with self.subTest(bad=bad):
                self.assertRefused(step(cmd=f'["python3", "{bad}"]'), "cmd:")

    def test_modules_need_their_pythonpath(self) -> None:
        (s,) = parse(step(cmd='["env", "PYTHONPATH=lib/src", "python3", "-m", "pkg.mod", "check"]'))
        self.assertEqual(s.script, "lib/src/pkg/mod.py")
        self.assertRefused(step(cmd='["python3", "-m", "pkg.mod"]'), "needs env PYTHONPATH=dir")
        self.assertRefused(step(cmd='["env", "PYTHONPATH=lib/src", "python3", "-m", "pkg.gone"]'),
                           "lib/src/pkg/gone.py is not a tracked file")
        self.assertRefused(step(cmd='["env", "PYTHONPATH=lib/none", "python3", "-m", "pkg.mod"]'),
                           "lib/none is not a tracked folder")
        self.assertRefused(step(cmd='["env", "PYTHONPATH=./lib/src", "python3", "-m", "pkg.mod"]'), "./ or ../")
        self.assertRefused(step(cmd='["env", "PYTHONPATH=lib/src", "python3", "-m", "pkg..mod"]'), "not a module")
        self.assertRefused(step(cmd='["env", "PYTHONPATH=lib/src", "python3", "-m"]'), "not a module")

    def test_env_takes_one_pythonpath(self) -> None:
        self.assertRefused(step(cmd='["env", "FOO=1", "python3", "tools/a.py"]'), "env sets FOO")
        self.assertRefused(step(cmd='["env", "PYTHONPATH=lib/src", "PYTHONPATH=lib", "python3", "tools/a.py"]'),
                           "only one PYTHONPATH")
        self.assertRefused(step(cmd='["env", "python3", "tools/a.py"]'), "env sets nothing")
        self.assertRefused(step(cmd='["env", "PYTHONPATH=lib/src"]'), "no program after env")
        self.assertRefused(step(cmd='["env", "PYTHONPATH=lib/src", "bash", "tools/b.sh"]'), "env only before python3")

    def test_the_hops_python_is_for_a_job_of_its_own(self) -> None:
        self.assertEqual(parse(step(cmd='["{python}", "tools/a.py"]'))[0].cmd[0], "{python}")
        self.assertRefused(step(group='"static"', cmd='["{python}", "tools/a.py"]'), "is for a step in no group")
        self.assertRefused(step(cmd='["python3", "tools/a.py", "{root}"]'), "{root}: only {python}")


class EdgesTest(Refusing):
    def test_paths_globs_and_local_nodes(self) -> None:
        for good in ("data/x.csv", "data/sub", "data/*.csv", "data/**/*.csv", "**/*.py", "media"):
            with self.subTest(good=good):
                parse(step(inputs=f'["{good}"]'))
        for bad, why in (("data/z.csv", "names no tracked file"), ("data/*.txt", "names no tracked file"),
                         ("media/x", "names no tracked file"), ("data/", "empty, ./ or ../"),
                         ("./data/x.csv", "./ or ../"), ("../hart/data/x.csv", "./ or ../"),
                         ("/data/x.csv", "not a path from the repo root"), ("", "is not a path")):
            with self.subTest(bad=bad):
                self.assertRefused(step(inputs=f'["{bad}"]'), "step 'one': inputs:", why)

    def test_a_star_stays_in_its_folder(self) -> None:
        self.assertRefused(step(inputs='["data/*.csv", "*/y.csv"]'), "*/y.csv names no tracked file")
        self.assertTrue(M.glob_regex("**/*.py").fullmatch("a.py"))
        self.assertTrue(M.glob_regex("**/*.py").fullmatch("x/y/a.py"))
        self.assertFalse(M.glob_regex("x/*.py").fullmatch("x/y/a.py"))
        self.assertFalse(M.glob_regex("x/a?py").fullmatch("x/a/py"))
        self.assertFalse(M.glob_regex("x.py").fullmatch("xxpy"))

    def test_edge_tables(self) -> None:
        self.assertRefused(step(inputs='[{ label = "x" }]'), "no path")
        self.assertRefused(step(inputs='[{ path = "data/x.csv", side = "sideways" }]'), "not a map edge side")
        self.assertRefused(step(inputs='[{ path = "data/x.csv", label = "" }]'), "label must be text")
        self.assertRefused(step(inputs='[{ path = "data/x.csv", why = "x" }]'), "why not allowed")
        self.assertRefused(step(outputs='[{ path = "data/x.csv", side = "check" }]'), "outputs:", "side not allowed")
        self.assertRefused(step(inputs='["data/x.csv", { path = "data/x.csv", label = "x" }]'), "listed twice")
        self.assertRefused(step(inputs='[1]'), "1 is not a path")

    def test_programs(self) -> None:
        (s,) = parse(step(programs='{ ruff = ["**/*.py", "data/x.csv"] }'))
        self.assertEqual(s.programs, (("ruff", ("**/*.py", "data/x.csv")),))
        self.assertRefused(step(programs='{ ruff = [] }'), "programs: ruff: must be a list")
        self.assertRefused(step(programs='{ ruff = ["**/*.rs"] }'), "programs: ruff: **/*.rs names no tracked")
        self.assertRefused(step(programs='{ "Ru ff" = ["data/x.csv"] }'), "not a program name")

    def test_quiet_inputs(self) -> None:
        (s,) = parse(step(quiet_inputs='["data/x.csv", "data/sub"]'))
        self.assertEqual(s.quiet_inputs, ("data/x.csv", "data/sub"))
        self.assertEqual(s.inputs, ())
        self.assertRefused(step(quiet_inputs='[{ path = "data/x.csv" }]'), "quiet_inputs: must be a list of paths")
        self.assertRefused(step(quiet_inputs='["data/gone.csv"]'), "quiet_inputs: data/gone.csv names no tracked")
        self.assertRefused(step(quiet_inputs='["./data/x.csv"]'), "quiet_inputs: ./data/x.csv has an empty")
        self.assertRefused(step(quiet_inputs='"data/x.csv"'), "quiet_inputs: must be a list")
        self.assertRefused(step(inputs='[{ path = "data/x.csv", label = "l" }]', quiet_inputs='["data/x.csv"]'),
                           "quiet_inputs: data/x.csv also in inputs")
        # an input whose path is no text is named as such, beside quiet_inputs, not a TypeError
        self.assertRefused(step(inputs='[{ path = ["data/x.csv"] }]', quiet_inputs='["data/x.csv"]'),
                           "is not a path")


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
        self.assertEqual([line.split()[0] for line in out.splitlines()], ["public-text", "ruff", "portal"])
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


class CheckShTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.s = scratch_check_sh(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_check(self, **env: str) -> subprocess.CompletedProcess:
        base = {"STUB_PIN": "", "STUB_STATIC": STATIC, "STUB_OWN": OWN, "FULL": "1", "CHECK_ONLY": STATIC_ONLY}
        return self.s.check_sh(**{**base, **env})

    def assertStopped(self, done: subprocess.CompletedProcess, *said: str) -> None:
        self.assertEqual(2, done.returncode, done.stdout + done.stderr)
        for text in said:
            self.assertIn(text, done.stderr)
        self.assertNotIn("ALL PASSED", done.stdout)
        self.assertNotIn("ran ", done.stdout)
        self.assertNotIn("Traceback", done.stderr)

    def test_a_manifest_that_fails_stops_the_run_before_any_job(self) -> None:
        self.assertStopped(self.run_check(STUB_MANIFEST_FAIL="1"), "manifest.py: stub manifest error",
                           "STOP: tools/pipeline/manifest.py jobs check --group static failed")

    def test_an_empty_list_stops_the_run(self) -> None:
        self.assertStopped(self.run_check(STUB_STATIC=""), "jobs check --group static listed no check")
        self.assertStopped(self.run_check(STUB_OWN="\n"), "jobs check --ungrouped listed no check")

    def test_a_line_that_is_not_a_step_stops_the_run(self) -> None:
        self.assertStopped(self.run_check(STUB_STATIC="Not a line\n"),
                           'printed "Not a line"')

    def test_the_steps_check_sh_adds_to_must_be_listed(self) -> None:
        self.assertStopped(self.run_check(STUB_STATIC=STATIC.replace("panels-tables python3", "pan python3")),
                           "no panels-tables job")
        self.assertStopped(self.run_check(STUB_OWN="solo python3 tools/a.py\n"), "no portal step")

    def test_each_static_line_is_a_job_of_its_own_panels_first_with_the_callers_pythonpath(self) -> None:
        done = self.run_check(PYTHONPATH="/caller")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        jobs = [line for line in done.stdout.splitlines() if line.startswith("--- ")]
        self.assertEqual([j.split(" (")[0] for j in jobs], ["--- panels-tables", "--- one", "--- two", "--- shell"])
        ran = [line for line in done.stdout.splitlines() if line.startswith("ran ")]
        self.assertEqual(ran, ["ran panels-tables PYTHONPATH=/caller", "ran --check PYTHONPATH=/caller",
                               "ran mod PYTHONPATH=lib/src:/caller", "ran shell --check"])
        self.assertEqual("ALL PASSED", done.stdout.splitlines()[-1])
        done = self.run_check(PYTHONPATH="")
        self.assertIn("ran mod PYTHONPATH=lib/src\n", done.stdout)

    def test_a_panels_job_runs_its_line_as_it_is_in_every_run(self) -> None:
        """Stage 6: no --full (that was build_panels.sh's); each panels job is a Python check like any other."""
        for env in ({"FULL": ""}, {"FULL": "1"}, {"CI": "true", "FULL": ""}):
            with self.subTest(env=env):
                done = self.run_check(**env)
                self.assertEqual(0, done.returncode, done.stdout + done.stderr)
                self.assertRegex(done.stdout, r"(?m)^ran panels-tables PYTHONPATH=")
                self.assertNotIn("--full", done.stdout)

    def test_a_line_the_shell_cannot_parse_stops_the_run(self) -> None:
        for env in ({"STUB_STATIC": STATIC + "bad python3 'unclosed\n"}, {"STUB_OWN": "bad python3 'unclosed\n" + OWN}):
            with self.subTest(env=env):
                self.assertStopped(self.run_check(**env), "printed a line the shell cannot parse: bad python3 'unclosed")

    def test_a_failing_check_fails_its_own_job_and_the_run(self) -> None:
        done = self.run_check(STUB_STATIC=STATIC + "gone python3 tools/none.py\n")
        self.assertEqual(1, done.returncode)
        self.assertIn("--- gone FAILED", done.stdout)
        self.assertIn("--- one (", done.stdout)
        self.assertEqual("FAILED", done.stdout.splitlines()[-1])

    def test_a_check_of_another_program_is_refused_not_run(self) -> None:
        done = self.run_check(STUB_STATIC=STATIC + "odd node tools/a.py\n")
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn("--- odd FAILED", done.stdout)
        self.assertIn("odd: check.sh's run_check takes python3, env VAR=... python3 or bash, not node; not run",
                      done.stdout)

    def test_the_results_file_names_each_job_and_its_result(self) -> None:
        """CHECK_RESULTS_TO: what tools/ci/stamp_gate.py's skip record and weekly guard read."""
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "results.tsv"
            done = self.run_check(STUB_STATIC=STATIC + "gone python3 tools/none.py\n", CHECK_RESULTS_TO=str(out))
            self.assertEqual(1, done.returncode)
            self.assertEqual(out.read_text(), "panels-tables\tpassed\none\tpassed\ntwo\tpassed\nshell\tpassed\ngone\tfailed\n")
            done = self.run_check(CHECK_ONLY="^nothing-by-this-name$", CHECK_RESULTS_TO=str(out))
            self.assertEqual(1, done.returncode)
            self.assertEqual(out.read_text(), "", "no job: an empty file, which the gate refuses, not a blank line")
            done = self.run_check(CHECK_RESULTS_TO=str(Path(d) / "no-such-folder" / "r.tsv"))
            self.assertEqual(2, done.returncode)
            self.assertIn("no-such-folder/r.tsv: cannot write it", done.stderr)
            self.assertNotIn("ran ", done.stdout)

    def test_no_job_to_run_is_no_pass(self) -> None:
        done = self.run_check(CHECK_ONLY="^nothing-by-this-name$")
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn("--- no job to run: CHECK_ONLY=^nothing-by-this-name$ matches none", done.stdout)
        self.assertEqual("FAILED", done.stdout.splitlines()[-1])

    def test_steps_in_no_group_are_jobs_of_their_own_and_portal_keeps_its_conditions(self) -> None:
        done = self.run_check(CHECK_ONLY="^(solo|portal.*)$", PORTAL_CHECK="1")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("--- solo (", done.stdout)
        self.assertIn("ran solo PYTHONPATH=", done.stdout)
        self.assertIn("ran portal PYTHONPATH=", done.stdout)
        done = self.run_check(CHECK_ONLY="^portal", CI="true")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("--- portal skipped in CI (", done.stdout)
        self.assertNotIn("ran portal", done.stdout)


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
# stamps, test classes, whether the portal runs, the docs-only list, the profile guard) and the unit test folders.
# A read-only check goes in tools/pipeline/checks.toml, where the map lane and the stamps see it, not here.
CHECK_SH_MACHINERY = {"tools/ci/changed_kind.py", "tools/hosts/profile_tables_guard.sh", "tools/agent/worktrees.py",
                      "tools/ci/docs_checks.sh", "tools/pipeline/manifest.py", "tools/audit/check_stamps.py",
                      "tools/audit/test_classes.py", "tools/audit/portal_inputs.py"}
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
