"""tools/pipeline/manifest.py: what the loader refuses and how it says so, the shell lines it prints, and (for now) that
tools/pipeline/checks.toml lists the same checks as tools/check.sh and tools/ci/docs_checks.sh."""
from __future__ import annotations

import importlib.util
import io
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
domain = "layout"
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
            "desc": '"First."'}
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

    def test_fields(self) -> None:
        self.assertRefused(step(colour='"red"'), "step 'one': colour: not a field")
        self.assertRefused(step(desc=None), "step 'one': desc: missing")
        self.assertRefused(step(name=None), "step 1: name: missing")
        self.assertRefused(step(docs_only='"yes"'), "docs_only: must be true or false")
        self.assertRefused(step(cmd='"python3 tools/a.py"'), "cmd: must be a list")
        self.assertRefused(step(desc='"  "'), "desc: must be a str with text")
        self.assertRefused(step(runner='"panels"'), "runner: 'panels' is not one of check")
        self.assertRefused(step(group='"fast"'), "group: 'fast'")
        self.assertRefused(step(domain='"ops"'), "domain: 'ops' is not a map domain (layout, website)")

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
        self.assertRefused(step(group='"static"', cmd='["{python}", "tools/a.py"]'), "a job of its own")
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
        with mock.patch.object(M.MAP, "read", side_effect=M.MAP.GraphError("the graph is not valid JSON")):
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


# TEMPORARY (stage 1 of ADR-037): tools/check.sh and tools/ci/docs_checks.sh still keep their own lists. Stage 2 makes
# them read `manifest.py jobs` and deletes this class.
class TemporarySyncTest(unittest.TestCase):
    CHECK_SH = (ROOT / "tools/check.sh").read_text()
    DOCS_SH = (ROOT / "tools/ci/docs_checks.sh").read_text()
    # check.sh adds --full to the panels check when its stamps are off; the manifest does not say that yet (stage 2)
    PANELS_FULL = ' ${panels_full[@]+"${panels_full[@]}"}'

    @classmethod
    def setUpClass(cls) -> None:
        cls.steps = M.load()

    def test_check_sh_run_lines_are_the_static_group_in_order(self) -> None:
        runs = [line for line in self.CHECK_SH.splitlines() if line.startswith("run ")]
        self.assertEqual([line for line in runs if line.endswith(self.PANELS_FULL)],
                         [next(line for line in runs if line.startswith("run panels "))])
        runs = [line.removesuffix(self.PANELS_FULL) for line in runs]
        self.assertEqual(runs, ["run " + M.shell_line(s) for s in M.select(self.steps, "check", group="static")])

    def test_check_sh_own_jobs_are_the_ungrouped_steps(self) -> None:
        later = [line.strip() for line in self.CHECK_SH.splitlines()
                 if re.match(r"\s*later [a-z]", line) and not line.strip().startswith("later static ")]
        self.assertEqual(later, ["later " + M.shell_line(s) for s in M.select(self.steps, "check", ungrouped=True)])

    def test_docs_checks_sh_is_the_docs_only_steps_and_unit_tests(self) -> None:
        # docs_checks.sh's order is its own (each check runs whatever the others do), so the lines are compared as a
        # set; its unit-* lines are unit tests, which the manifest does not hold (design section 6)
        checks = [line for line in self.DOCS_SH.splitlines() if line.startswith("check ")]
        theirs = sorted(line for line in checks if not line.split()[1].startswith("unit-"))
        self.assertEqual(theirs, sorted("check " + M.shell_line(s) for s in M.select(self.steps, "check",
                                                                                      docs_only=True)))


if __name__ == "__main__":
    unittest.main()
