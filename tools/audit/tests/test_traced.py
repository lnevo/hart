"""traced: the trace hook and the read sets that make panels' and check.sh's stamps are built from (tools/audit/traced.py).

Each test runs a small Python script in a scratch repo under the real hook, records a stamp from its trace and then
changes the repo the way an edit would."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import traced  # noqa: E402

HOOK = Path(traced.HOOK_DIR)


def run_traced(root: Path, code: str, log: Path, roots: int = 1, env_extra: dict | None = None) -> int:
    """Run `code` as a script in `root` under the hook, logging into `log` (the runner's "b" lines first)."""
    log.write_text("0\tb\n" * roots)
    script = root / "job.py"
    script.write_text(textwrap.dedent(code))
    env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
    env.update(HART_TRACE_LOG=str(log), HART_TRACE_ROOT=str(root),
               PYTHONPATH=str(HOOK) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
               **(env_extra or {}))
    return subprocess.run([sys.executable, str(script)], cwd=root, env=env, capture_output=True).returncode


class ReadSetTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        self.root, self.log = (tmp / "repo").resolve() if False else tmp / "repo", tmp / "trace.log"
        self.root.mkdir()
        self.root = self.root.resolve()
        for rel in ("data/a.csv", "data/b.csv", "data/sub/c.csv", ".cache/hart/x.json", "README.md"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("v1\n")

    def record(self, code: str, **kw) -> dict:
        self.assertEqual(run_traced(self.root, code, self.log, **kw), 0)
        t = traced.parse(self.log)
        self.assertIsNone(traced.problem(t))
        return traced.make_stamp("k", t, str(self.root))

    def current(self, stamp: dict) -> bool:
        return traced.mismatch(stamp, "k", str(self.root)) is None

    def test_an_edit_to_a_file_read_misses_and_one_not_read_does_not(self) -> None:
        stamp = self.record("open('data/a.csv').read()\n")
        self.assertIn("data/a.csv", stamp["state"]["files"])
        self.assertTrue(self.current(stamp))
        (self.root / "data/b.csv").write_text("v2\n")
        self.assertTrue(self.current(stamp), "b.csv was never read")
        (self.root / "data/a.csv").write_text("v2\n")
        self.assertFalse(self.current(stamp))

    def test_a_new_file_in_a_listed_folder_misses(self) -> None:
        stamp = self.record("import os\nsorted(os.listdir('data'))\n")
        self.assertTrue(self.current(stamp))
        (self.root / "data/new.csv").write_text("x\n")
        self.assertFalse(self.current(stamp))

    def test_a_glob_lists_its_folder(self) -> None:
        stamp = self.record("from pathlib import Path\nlist(Path('data/sub').glob('*.csv'))\n")
        (self.root / "data/sub/d.csv").write_text("x\n")
        self.assertFalse(self.current(stamp))

    def test_a_missing_file_that_appears_misses(self) -> None:
        for probe in ("from pathlib import Path\nPath('data/later.csv').exists()\n",
                      "try:\n    open('data/later.csv')\nexcept FileNotFoundError:\n    pass\n"):
            with self.subTest(probe=probe):
                (self.root / "data/later.csv").unlink(missing_ok=True)
                stamp = self.record(probe)
                self.assertIn("data/later.csv", stamp["state"]["missing"])
                self.assertTrue(self.current(stamp))
                (self.root / "data/later.csv").write_text("x\n")
                self.assertFalse(self.current(stamp))

    def test_a_file_stated_and_then_removed_misses(self) -> None:
        stamp = self.record("import os\nos.path.isfile('data/b.csv')\n")
        (self.root / "data/b.csv").unlink()
        self.assertFalse(self.current(stamp))

    def test_cache_reads_are_left_out(self) -> None:
        stamp = self.record("open('.cache/hart/x.json').read()\nimport os\nos.listdir('.cache/hart')\n")
        names = [n for k in ("files", "dirs", "missing", "present") for n in stamp["state"][k]]
        self.assertFalse([n for n in names if ".cache" in n.split("/")], names)
        (self.root / ".cache/hart/x.json").write_text("v2\n")
        (self.root / ".cache/hart/y.json").write_text("v2\n")
        self.assertTrue(self.current(stamp))

    def test_a_read_through_a_link_in_the_cache_reads_the_data_file(self) -> None:
        (self.root / ".cache/hart/view").mkdir()
        (self.root / ".cache/hart/view/a.csv").symlink_to(self.root / "data/a.csv")
        stamp = self.record("open('.cache/hart/view/a.csv').read()\n")
        self.assertIn("data/a.csv", stamp["state"]["files"])

    def test_an_import_counts_as_a_read_of_its_source(self) -> None:
        (self.root / "lib").mkdir()
        (self.root / "lib/mod.py").write_text("X = 1\n")
        code = "import sys\nsys.path.insert(0, 'lib')\nimport mod\n"
        self.record(code)                      # writes the .pyc: the second run reads it instead of the source
        stamp = self.record(code)
        self.assertIn("lib/mod.py", stamp["state"]["files"])

    def test_code_is_marked_and_data_is_not(self) -> None:
        """The "c" lines (ADR-037 stage 4c): the main script, an import (from its source and from its .pyc), runpy and
        a traceback's source are code; a .py read with open(), pkgutil.get_data and a file under tools/ are data.
        Every one of them is still a read, which the stamps hash."""
        for rel, text in (("lib/mod.py", "X = 1\n"), ("lib/pkg/__init__.py", ""), ("lib/pkg/res.txt", "r\n"),
                          ("lib/text.py", "Y = 2\n"), ("lib/run.py", "Z = 3\n"), ("lib/boom.py", "def f():\n  1/0\n"),
                          ("tools/levels/main.svg", "<svg/>\n")):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text)
        code = ("import sys, runpy, pkgutil, traceback\nsys.path.insert(0, 'lib')\nimport mod, pkg, boom\n"
                "open('lib/text.py').read()\npkgutil.get_data('pkg', 'res.txt')\nrunpy.run_path('lib/run.py')\n"
                "open('tools/levels/main.svg').read()\n"
                "try:\n    boom.f()\nexcept ZeroDivisionError:\n    traceback.format_exc()\n")
        for _ in range(2):                     # the second run imports mod and boom from their .pyc
            self.record(code)
            t = traced.parse(self.log)
            reads = {r for r in (traced.keep(p, str(self.root), ()) for p in t.reads) if r and not os.path.isabs(r)}
            marked = {r for r in (traced.keep(p, str(self.root), ()) for p in t.code) if r and not os.path.isabs(r)}
            self.assertEqual(marked, {"job.py", "lib/mod.py", "lib/pkg/__init__.py", "lib/run.py", "lib/boom.py"})
            self.assertLessEqual(marked, reads)
            self.assertNotIn(f"\tr\t{self.root}/job.py\n", self.log.read_text())    # a code open is no data read
            self.assertLessEqual({"lib/text.py", "lib/pkg/res.txt", "tools/levels/main.svg"}, reads - marked)

    def test_opened_as_code_reads_the_calling_frame(self) -> None:
        def frame(name: str, file: str, up=None):
            return unittest.mock.Mock(f_code=unittest.mock.Mock(co_name=name, co_filename=file), f_back=up)
        boot = "<frozen importlib._bootstrap_external>"
        self.assertTrue(traced._opened_as_code(frame("get_data", boot, frame("get_code", boot))))
        self.assertFalse(traced._opened_as_code(frame("get_data", boot, frame("get_data", "/py/pkgutil.py"))))
        self.assertFalse(traced._opened_as_code(frame("get_data", boot)))
        self.assertTrue(traced._opened_as_code(frame("_get_code_from_file", "/py/runpy.py")))
        self.assertTrue(traced._opened_as_code(frame("_get_code_from_file", "<frozen runpy>")))
        self.assertTrue(traced._opened_as_code(frame("_read_directory", "<frozen zipimport>")))
        self.assertTrue(traced._opened_as_code(frame("open", "/py/tokenize.py", frame("updatecache", "/py/linecache.py"))))
        self.assertFalse(traced._opened_as_code(frame("open", "/py/tokenize.py", frame("main", "/repo/job.py"))))
        self.assertFalse(traced._opened_as_code(frame("<module>", "/repo/job.py")))

    def test_a_python_child_is_traced(self) -> None:
        stamp = self.record("import subprocess, sys\n"
                            "subprocess.run([sys.executable, '-c', \"open('data/sub/c.csv').read()\"], check=True)\n")
        self.assertIn("data/sub/c.csv", stamp["state"]["files"])
        self.assertEqual(traced.untraced(traced.parse(self.log), str(self.root))[0], [])

    def test_a_shell_or_a_python_child_without_the_hook_is_untraced(self) -> None:
        for code, prog in (("import subprocess\nsubprocess.run(['sh', '-c', 'cat data/a.csv'])\n", "sh"),
                           ("import subprocess, sys\nsubprocess.run([sys.executable, '-I', '-c', '1'])\n",
                            Path(sys.executable).name)):
            with self.subTest(prog=prog):
                self.assertEqual(run_traced(self.root, code, self.log), 0)
                self.assertEqual(traced.untraced(traced.parse(self.log), str(self.root))[0], [prog])

    def test_a_subprocess_outside_the_checkout_is_not_counted(self) -> None:
        code = "import subprocess, tempfile\nsubprocess.run(['sh', '-c', 'true'], cwd=tempfile.gettempdir())\n"
        self.assertEqual(run_traced(self.root, code, self.log), 0)
        self.assertEqual(traced.untraced(traced.parse(self.log), str(self.root)), ([], []))

    def test_a_read_only_git_command_is_replayed(self) -> None:
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, env=env)
        code = "import subprocess\nsubprocess.run(['git', 'ls-files', '-o', '--exclude-standard', 'data'], capture_output=True)\n"
        self.assertEqual(run_traced(self.root, code, self.log), 0)
        progs, cmds = traced.untraced(traced.parse(self.log), str(self.root))
        self.assertEqual(progs, [])
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0][0], traced.ROOT_MARK)
        before = traced.git_replay(cmds, str(self.root))
        self.assertEqual(traced.git_replay(cmds, str(self.root)), before)
        (self.root / "data/brand-new.csv").write_text("x\n")
        self.assertNotEqual(traced.git_replay(cmds, str(self.root)), before)

    def test_a_replayed_answer_that_names_the_checkout_holds_in_a_copy_of_it(self) -> None:
        """make remote runs each check in a new worktree: `rev-parse --show-toplevel` names it, so the checkout's
        path is hashed as {root}; a path outside the checkout is still compared as it is."""
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}
        copy = self.root.parent / "copy"
        for root in (self.root, copy):
            root.mkdir(exist_ok=True)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
        cmds = [[traced.ROOT_MARK, "git", "-C", traced.ROOT_MARK, "rev-parse", "--show-toplevel"]]
        self.assertEqual(traced.git_replay(cmds, str(copy)), traced.git_replay(cmds, str(self.root)))
        outside = [[traced.ROOT_MARK, "git", "-C", str(copy), "rev-parse", "--show-toplevel"]]
        self.assertNotEqual(traced.git_replay(outside, str(self.root)), traced.git_replay(cmds, str(self.root)))

    def test_a_writing_git_command_is_untraced(self) -> None:
        code = "import subprocess\nsubprocess.run(['git', 'init', '-q'], capture_output=True)\n"
        self.assertEqual(run_traced(self.root, code, self.log), 0)
        self.assertEqual(traced.untraced(traced.parse(self.log), str(self.root))[0], ["git init"])


class ReviewTest(ReadSetTest):
    """Cases from the code review of the traced stamps: each could have recorded a stamp that skips a stale job."""

    def untraced(self, code: str) -> list[str]:
        self.assertEqual(run_traced(self.root, code, self.log), 0)
        return traced.untraced(traced.parse(self.log), str(self.root))[0]

    def late(self, code: str, meanwhile) -> list[str]:
        """changed_since after `code` ran and `meanwhile` changed the repo (as another session would, mid-run)."""
        self.assertEqual(run_traced(self.root, code, self.log), 0)
        meanwhile()
        t = traced.parse(self.log)
        return traced.changed_since(t, traced.read_set(t, str(self.root)), str(self.root))

    def test_a_folder_that_gains_a_file_mid_run_records_nothing(self) -> None:
        late = self.late("import os\nos.listdir('data/sub')\n", lambda: (self.root / "data/sub/new.csv").write_text("x"))
        self.assertIn("data/sub", late)

    def test_litter_or_a_missing_folder_mid_run_still_records(self) -> None:
        # a first run elsewhere makes __pycache__ in listed folders (the Windows box's fresh worktrees did)
        late = self.late("import os\nos.listdir('data/sub')\ntry:\n    os.listdir('data/none')\nexcept OSError:\n    pass\n",
                         lambda: (self.root / "data/sub/__pycache__").mkdir())
        self.assertEqual(late, [])

    def test_a_read_file_deleted_mid_run_records_nothing(self) -> None:
        self.assertIn("data/a.csv", self.late("open('data/a.csv').read()\n", (self.root / "data/a.csv").unlink))

    def test_an_absent_file_that_appears_mid_run_records_nothing(self) -> None:
        late = self.late("import os\nos.path.exists('data/soon.csv')\n",
                         lambda: (self.root / "data/soon.csv").write_text("x"))
        self.assertIn("data/soon.csv", late)

    def test_a_file_stated_for_its_size_misses_when_the_size_changes(self) -> None:
        stamp = self.record("import os\nos.path.getsize('data/b.csv')\n")
        (self.root / "data/b.csv").write_text("a longer v1\n")
        self.assertFalse(self.current(stamp))

    def test_a_python_started_by_a_shell_string_does_not_hide_the_shell(self) -> None:
        code = ("import subprocess, sys\n"
                "subprocess.run(f'cat data/a.csv >/dev/null; exec {sys.executable} -c 1', shell=True, check=True)\n")
        self.assertEqual(self.untraced(code), ["sh"])

    def test_a_stale_token_in_the_environment_does_not_mark_a_spawn_traced(self) -> None:
        # the sh spawn leaves its token in os.environ; a multiprocessing worker (no Popen event) inherits it
        code = ("import multiprocessing, subprocess\n"
                "def work():\n    pass\n"
                "if __name__ == '__main__':\n"
                "    subprocess.run(['sh', '-c', 'cat data/a.csv >/dev/null'])\n"
                "    p = multiprocessing.get_context('spawn').Process(target=work)\n"
                "    p.start()\n    p.join()\n")
        self.assertEqual(self.untraced(code), ["sh"])

    def test_an_exec_keeps_the_tokens_apart(self) -> None:
        code = ("import os, subprocess, sys\n"
                "if len(sys.argv) == 1:\n"
                "    subprocess.run(['sh', '-c', 'true'])\n"
                "    os.execv(sys.executable, [sys.executable, sys.argv[0], 'again'])\n"
                "subprocess.run([sys.executable, '-c', '1'], check=True)\n")
        self.assertEqual(self.untraced(code), ["sh"])

    def test_a_glob_with_a_root_dir_lists_that_folder(self) -> None:
        stamp = self.record("import glob\nglob.glob('*.csv', root_dir='data/sub')\n")
        self.assertIn("data/sub", stamp["state"]["dirs"])
        self.assertIn("glob.glob/2", traced._EVENTS)        # the event that carries root_dir
        self.assertNotIn("glob.glob", traced._EVENTS)       # the same call's plain event has none


class ProblemTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        self.root, self.log = tmp / "repo", tmp / "trace.log"
        self.root.mkdir()

    def test_no_trace_is_a_problem(self) -> None:
        self.assertIsNotNone(traced.problem(traced.parse(self.log)))     # no file at all
        self.log.write_text("0\tb\n")
        self.assertIn("did not load", traced.problem(traced.parse(self.log)))

    def test_a_runner_spawned_program_alone_is_a_trace(self) -> None:
        """check.sh's panels job: bash, written into the log by check.sh itself, and no Python process expected."""
        self.log.write_text(f"0\tt\t1700000000000000000\n0\tx\tcheck.sh-run\t{self.root}\tbash\ttools/b.sh\n")
        t = traced.parse(self.log)
        self.assertIsNone(traced.problem(t))
        self.assertEqual(t.started_ns, 1700000000000000000)
        self.assertEqual(traced.untraced(t, str(self.root)), (["bash"], []))
        for text in (f"0\tt\t1\n0\tb\n0\tx\tcheck.sh-run\t{self.root}\tbash\tx.sh\n",   # Python expected
                     f"0\tx\tcheck.sh-run\t{self.root}\tbash\tx.sh\n",              # no start time
                     f"5\tx\ttok\t{self.root}\tbash\tx.sh\n",                    # a hooked process's spawn, no start
                     ""):
            with self.subTest(text=text):
                self.log.write_text(text)
                self.assertIn("did not load", traced.problem(traced.parse(self.log)))

    def test_a_process_that_dropped_the_hook_is_a_problem(self) -> None:
        self.assertEqual(run_traced(self.root, "pass\n", self.log, roots=2), 0)
        self.assertIn("1 of the 2", traced.problem(traced.parse(self.log)))

    def test_a_crash_still_parses_but_the_runner_records_nothing(self) -> None:
        # the runners record only after a pass; what a crashed process logged stays readable and harmless
        self.assertNotEqual(run_traced(self.root, "open('nope.txt')\n", self.log), 0)
        self.assertIsNone(traced.problem(traced.parse(self.log)))

    def test_a_file_changed_while_the_job_ran_is_reported(self) -> None:
        (self.root / "a.txt").write_text("v1\n")
        code = "import time\nopen('a.txt').read()\ntime.sleep(0.05)\nopen('a.txt', 'a')\n"
        self.assertEqual(run_traced(self.root, code, self.log), 0)
        t = traced.parse(self.log)
        rs = traced.read_set(t, str(self.root))
        self.assertEqual(traced.changed_since(t, rs, str(self.root)), [], "a file the job wrote itself is fine")
        (self.root / "a.txt").write_text("edited meanwhile\n")
        t.writes.clear()
        self.assertEqual(traced.changed_since(t, rs, str(self.root)), ["a.txt"])

    def test_a_stamp_from_another_version_or_key_never_holds(self) -> None:
        self.assertIsNotNone(traced.mismatch(None, "k", str(self.root)))
        self.assertIsNotNone(traced.mismatch({"version": 0, "key": "k", "state": {}}, "k", str(self.root)))
        self.assertIsNotNone(traced.mismatch({"version": traced.VERSION, "key": "j", "state": {}}, "k", str(self.root)))
        self.assertIsNone(traced.mismatch({"version": traced.VERSION, "key": "k", "state": {}}, "k", str(self.root)))


class WhichAndSkipTest(unittest.TestCase):
    """The tool lookups and unittest skips the hook logs: what a test that skips on a missing tool skipped on."""

    def setUp(self) -> None:
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        self.root, self.log, self.bin = tmp / "repo", tmp / "trace.log", tmp / "bin"
        self.root.mkdir()
        self.bin.mkdir()
        path = f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}"
        patch = unittest.mock.patch.dict(os.environ, {"PATH": path})
        patch.start()
        self.addCleanup(patch.stop)

    def install_tool(self) -> Path:
        tool = self.bin / "hart-no-such-tool"
        tool.write_text("#!/bin/sh\n")
        tool.chmod(0o755)
        return tool

    def test_a_lookup_on_the_starting_path_is_an_input(self) -> None:
        code = "import shutil\nshutil.which('hart-no-such-tool')\n"
        self.assertEqual(run_traced(self.root, code, self.log), 0)
        t = traced.parse(self.log)
        self.assertEqual(t.which, {("hart-no-such-tool", "")})
        stamp = traced.make_stamp("k", t, str(self.root))
        self.assertIsNone(traced.mismatch(stamp, "k", str(self.root)))
        tool = self.install_tool()
        self.assertIn("finds " + str(tool), traced.mismatch(stamp, "k", str(self.root)))

    def test_a_lookup_on_a_stub_path_or_another_path_is_no_input(self) -> None:
        code = ("import os, shutil\nshutil.which('hart-no-such-tool', path='/nowhere')\n"
                "os.environ['PATH'] = '/elsewhere'\nshutil.which('hart-no-such-tool')\n")
        self.assertEqual(run_traced(self.root, code, self.log), 0)
        self.assertEqual(traced.parse(self.log).which, set())

    def test_a_child_started_on_a_stub_path_notes_nothing(self) -> None:
        """A test's Python child whose PATH puts a stub folder first finds the stub: no input of the job."""
        self.install_tool()
        code = ("import os, subprocess, sys\n"
                f"env = dict(os.environ, PATH={str(self.bin)!r} + os.pathsep + '/usr/bin')\n"
                "subprocess.run([sys.executable, '-c', 'import shutil; shutil.which(\"hart-no-such-tool\")'], env=env,"
                " check=True)\n")
        empty = self.root.parent / "empty-bin"
        empty.mkdir()
        stub_free = f"{empty}{os.pathsep}{os.environ['PATH'].split(os.pathsep, 1)[1]}"
        with unittest.mock.patch.dict(os.environ, {"PATH": stub_free}):
            self.assertEqual(run_traced(self.root, code, self.log), 0)
        self.assertEqual(traced.parse(self.log).which, set())

    def write_tests(self) -> None:
        (self.root / "test_s.py").write_text(textwrap.dedent("""\
            import shutil, unittest
            TOOL = shutil.which("hart-no-such-tool")

            class S(unittest.TestCase):
                @unittest.skipUnless(TOOL, "no hart-no-such-tool\\there")
                def test_needs_the_tool(self):
                    pass

                def test_plain(self):
                    pass
            """))

    def run_unittest(self, *args: str) -> subprocess.CompletedProcess:
        self.log.write_text("0\tb\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
        env.update(HART_TRACE_LOG=str(self.log), HART_TRACE_ROOT=str(self.root), PYTHONPATH=str(HOOK))
        return subprocess.run([sys.executable, *args], cwd=self.root, env=env, capture_output=True, text=True)

    def test_a_unittest_process_logs_each_skip_with_its_reason(self) -> None:
        self.write_tests()
        done = self.run_unittest("-m", "unittest", "-q", "test_s")
        self.assertIn("OK (skipped=1)", done.stderr)
        t = traced.parse(self.log)
        # the tab in the reason (the log's separator) is written as a space
        self.assertEqual(t.skips, [("test_s.S.test_needs_the_tool", "no hart-no-such-tool here")])
        self.assertEqual(t.which, {("hart-no-such-tool", "")})

    def test_a_process_that_is_no_unittest_run_does_not_load_unittest(self) -> None:
        code = "import sys\nassert 'unittest' not in sys.modules, 'the hook imported unittest'\n"
        self.assertEqual(run_traced(self.root, code, self.log), 0)
        self.assertEqual(traced.parse(self.log).skips, [])

    def test_runs_unittest(self) -> None:
        self.assertTrue(traced._runs_unittest(["python3", "-m", "unittest", "discover"]))
        self.assertTrue(traced._runs_unittest(["python3", "-b", "-m", "unittest"]))
        for argv in (["python3", "job.py", "-m", "unittest"][:2], ["python3", "-m"], ["python3", "-m", "pytest"], []):
            with self.subTest(argv=argv):
                self.assertFalse(traced._runs_unittest(argv))


class KeepTest(unittest.TestCase):
    def test_what_a_stamp_leaves_out(self) -> None:
        root, skip = "/r", traced._skip_prefixes("/r")
        self.assertEqual(traced.keep("/r/data/a.csv", root, skip), "data/a.csv")
        for p in ("/r/.cache/x", "/home/u/hart/.cache/hart/schematic/x", "/r/tools/__pycache__/m.pyc",
                  "/r/external/model-railroad-skills/a.py", "/r/.git/index", "/usr/lib/x.py", "/tmp/x"):
            with self.subTest(path=p):
                self.assertIsNone(traced.keep(p, root, skip))
        self.assertEqual(traced.keep("/r/.git", root, skip), ".git")          # a worktree's .git file
        with tempfile.TemporaryDirectory() as home:
            target = Path(home) / "cpython-3.13.7-platform"
            target.mkdir()
            link = Path(home) / "cpython-3.13-platform"       # uv's link to the interpreter it installed
            link.symlink_to(target)
            only_interpreter = (os.path.realpath(target) + os.sep,)
            self.assertEqual(traced.keep(str(target / "x"), root, ()), str(target / "x"))
            self.assertIsNone(traced.keep(str(link), root, only_interpreter))
        self.assertEqual(traced.keep("/Volumes/u/Documents/plan.any", root, skip), "/Volumes/u/Documents/plan.any")

    def test_a_pyc_stands_for_its_source(self) -> None:
        traced._state.setdefault("prefix", None)
        self.assertEqual(traced._source_of_pyc("/r/a/__pycache__/m.cpython-313.pyc"), "/r/a/m.py")

    def test_git_subcommands(self) -> None:
        self.assertTrue(traced.git_reads_only(["git", "-C", "/r", "rev-parse", "HEAD"]))
        self.assertTrue(traced.git_reads_only(["git", "config", "--get", "user.name"]))
        self.assertFalse(traced.git_reads_only(["git", "config", "user.name", "x"]))
        self.assertFalse(traced.git_reads_only(["git", "-c", "a=b", "commit", "-m", "x"]))
        self.assertTrue(traced.git_reads_only(["git", "worktree", "list"]))
        self.assertFalse(traced.git_reads_only(["git", "worktree", "add", "x"]))


class LoadTest(unittest.TestCase):
    PROBE = ("import importlib.util, json, sys\n"
             "before = list(sys.path)\n"
             "spec = importlib.util.spec_from_file_location('_hart_traced', sys.argv[1])\n"
             "t = importlib.util.module_from_spec(spec)\n"
             "spec.loader.exec_module(t)\n"
             "print(json.dumps([t.HOOK_FILES, callable(t.parse), callable(t.listing), t.VERSION,\n"
             "                  t.Trace.__name__, sorted(k for k in sys.modules if 'traced' in k),\n"
             "                  sys.path == before, t.parse is sys.modules['traced_read'].parse]))\n")

    def probe(self, path: Path) -> subprocess.CompletedProcess:
        """Load `path` as the hook and panel_stamps do: by path, isolated (-I: nothing of the repo on sys.path),
        from another folder."""
        with tempfile.TemporaryDirectory() as cwd:
            return subprocess.run([sys.executable, "-I", "-c", self.PROBE, str(path)], cwd=cwd,
                                  capture_output=True, text=True, timeout=60)

    def test_traced_and_its_parts_load_by_path_from_any_cwd(self) -> None:
        """The part is imported as a module of its own, its names are traced's, sys.path is left as it was, and
        every part is in HOOK_FILES."""
        done = self.probe(Path(traced.__file__))
        self.assertEqual(done.returncode, 0, done.stderr)
        files, parse, listing, version, trace, registered, path_kept, same = json.loads(done.stdout)
        self.assertEqual(files, list(traced.HOOK_FILES))
        self.assertIn("tools/audit/traced_read.py", files)
        self.assertEqual((parse, listing, version, trace, registered), (True, True, traced.VERSION, "Trace",
                                                                        ["traced_read"]))
        self.assertTrue(path_kept)
        self.assertTrue(same)

    def test_every_name_of_the_part_is_traceds(self) -> None:
        import traced_read
        names = {k for k, v in vars(traced_read).items()
                 if not k.startswith("__") and k != "annotations" and not isinstance(v, types.ModuleType)}
        self.assertEqual(sorted(k for k in names if getattr(traced, k, None) is not getattr(traced_read, k)), [])

    def test_a_missing_part_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "traced.py"
            shutil.copy(traced.__file__, copy)
            done = self.probe(copy)
        self.assertNotEqual(done.returncode, 0)
        self.assertRegex(done.stderr, r"ImportError: traced: its part .*traced_read\.py is missing")

    def test_a_part_imported_from_another_folder_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            shutil.copy(traced.__file__, folder / "traced.py")
            shutil.copy(Path(traced.__file__).with_name("traced_read.py"), folder / "traced_read.py")
            spec = importlib.util.spec_from_file_location("traced_copy_test", folder / "traced.py")
            mod = importlib.util.module_from_spec(spec)
            with self.assertRaisesRegex(ImportError, r"traced: its part traced_read was imported from .*, not from"):
                spec.loader.exec_module(mod)


if __name__ == "__main__":
    unittest.main()
