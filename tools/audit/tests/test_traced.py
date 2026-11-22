"""traced: the trace hook and the read sets that make panels' and check.sh's stamps are built from (tools/audit/traced.py).

Each test runs a small Python script in a scratch repo under the real hook, records a stamp from its trace and then
changes the repo the way an edit would."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
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


class KeepTest(unittest.TestCase):
    def test_what_a_stamp_leaves_out(self) -> None:
        root, skip = "/r", traced._skip_prefixes("/r")
        self.assertEqual(traced.keep("/r/data/a.csv", root, skip), "data/a.csv")
        for p in ("/r/.cache/x", "/home/u/hart/.cache/hart/schematic/x", "/r/tools/__pycache__/m.pyc",
                  "/r/external/model-railroad-skills/a.py", "/r/.git/index", "/usr/lib/x.py", "/tmp/x"):
            with self.subTest(path=p):
                self.assertIsNone(traced.keep(p, root, skip))
        self.assertEqual(traced.keep("/r/.git", root, skip), ".git")          # a worktree's .git file
        self.assertEqual(traced.keep("/home/u/Documents/plan.any", root, skip), "/home/u/Documents/plan.any")

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


if __name__ == "__main__":
    unittest.main()
