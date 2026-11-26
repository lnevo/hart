"""tools/pipeline/manifest.py: what the loader refuses in a step and how it says so (the fields, the commands, the
inputs and outputs), on TOML text checked against a stand-in repo, not this one.

Split out of test_pipeline_manifest.py on 2026-11-26 with no change in the tests, so each file stays under the size
limit (tools/audit/check_py_sizes.py). The module under test, the good step and the parse and step helpers come from
that file.
"""
from __future__ import annotations

import unittest

# its folder is on sys.path under discover
from test_pipeline_manifest import GOOD, M, parse, step


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


if __name__ == "__main__":
    unittest.main()
