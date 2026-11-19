"""jmri_cmd_watcher.py in the JMRI fake: a failure is printed and the watcher goes on, and
the result file only ever appears complete (temp name, then rename)."""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from jmri_fake import Layout, jmri_modules, load_script

SCRIPT = Path(__file__).resolve().parents[1] / "jmri_cmd_watcher.py"


class _Stop(BaseException):
    """Ends the watcher's endless loop from the fake sleep; `except Exception` lets it through."""


class JavaException(BaseException):
    """Stands for java.lang.Exception: in Jython it is not a Python Exception."""


class CmdWatcher(unittest.TestCase):
    def setUp(self):
        self.layout = Layout()
        # The script starts its polling thread on load; the tests drive the loop themselves.
        with mock.patch("threading.Thread") as thread:
            self.env = load_script(SCRIPT, self.layout)
        thread.assert_called_once()
        self.assertIs(thread.call_args.kwargs["target"], self.env["_loop"])
        self.assertEqual(
            (self.env["CMD"], self.env["OUT"], self.env["LAST"], self.env["READY"]),
            ("/tmp/jmri_cmd.py", "/tmp/jmri_cmd.out", "/tmp/jmri_cmd.last", "/tmp/jmri_watcher.ready"),
        )
        self.env["java"].lang.Exception = JavaException
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for name in ("CMD", "OUT", "LAST", "READY"):
            self.env[name] = str(self.dir / Path(self.env[name]).name)
        self.cmd, self.out = Path(self.env["CMD"]), Path(self.env["OUT"])

    def drop(self, source):
        """Drop a command the way the shell wrappers do."""
        tmp = Path(str(self.cmd) + ".tmp")
        tmp.write_text(source)
        os.rename(tmp, self.cmd)

    def run_loop(self, *each_pass):
        """Run the loop; each_pass[i] is called in place of the i-th sleep, then the loop stops."""
        steps = list(each_pass)
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            if not steps:
                raise _Stop()
            steps.pop(0)()

        self.env["time"] = types.SimpleNamespace(sleep=sleep)
        printed = io.StringIO()
        with jmri_modules(self.layout), contextlib.redirect_stdout(printed):
            with self.assertRaises(_Stop):
                self.env["_loop"]()
        self.assertEqual(set(slept), {0.5})
        return printed.getvalue()

    def test_ok_result_and_ready_file(self):
        self.drop("RESULT = 6 * 7\n")
        printed = self.run_loop()
        self.assertEqual(self.out.read_text(), "ok\n42")
        self.assertEqual(Path(self.env["READY"]).read_text(), "ready")
        self.assertFalse(self.cmd.exists())
        self.assertEqual(Path(self.env["LAST"]).read_text(), "RESULT = 6 * 7\n")
        self.assertEqual(printed, "")

    def test_command_sees_jmri_and_java(self):
        self.drop("RESULT = (jmri.__name__, java.__name__)\n")
        self.run_loop()
        self.assertEqual(self.out.read_text(), "ok\n('jmri', 'java')")

    def test_failing_command_reports_error_and_watcher_runs_the_next(self):
        self.drop("raise ValueError('boom')\n")
        seen = []

        def next_command():
            seen.append(self.out.read_text())
            self.drop("RESULT = 'second'\n")

        self.run_loop(next_command)
        self.assertTrue(seen[0].startswith("error\n"), seen[0])
        self.assertIn("ValueError: boom", seen[0])
        self.assertEqual(self.out.read_text(), "ok\nsecond")

    def test_java_exception_in_a_command_reports_error_and_watcher_runs_the_next(self):
        self.drop("raise java.lang.Exception('java boom')\n")
        seen = []

        def next_command():
            seen.append(self.out.read_text())
            self.drop("RESULT = 'second'\n")

        self.run_loop(next_command)
        self.assertTrue(seen[0].startswith("error\n"), seen[0])
        self.assertIn("java boom", seen[0])
        self.assertEqual(self.out.read_text(), "ok\nsecond")

    def test_java_exception_while_handling_is_printed_and_watcher_runs_the_next(self):
        self.drop("RESULT = 'first'\n")
        real_rename = os.rename
        failed = []

        def rename(src, dst):
            if dst == self.env["LAST"] and not failed:
                failed.append(src)
                raise JavaException("java cannot move the command")
            return real_rename(src, dst)

        with mock.patch.object(os, "rename", rename):
            printed = self.run_loop(lambda: None)
        self.assertEqual(printed, "jmri_cmd_watcher: command handling failed: java cannot move the command\n")
        self.assertEqual(self.out.read_text(), "ok\nfirst")

    def test_handling_failure_is_printed_and_watcher_runs_the_next(self):
        self.drop("RESULT = 'first'\n")
        real_rename = os.rename
        failed = []

        def rename(src, dst):
            if dst == self.env["LAST"] and not failed:
                failed.append(src)
                raise OSError("cannot move the command")
            return real_rename(src, dst)

        with mock.patch.object(os, "rename", rename):
            printed = self.run_loop(lambda: None)
        self.assertEqual(printed, "jmri_cmd_watcher: command handling failed: cannot move the command\n")
        self.assertEqual(self.out.read_text(), "ok\nfirst")

    def test_result_is_written_under_a_temp_name_then_renamed(self):
        for source, expected in (("RESULT = 'x' * 5000\n", "ok\n" + "x" * 5000), ("1/0\n", None)):
            with self.subTest(source=source):
                if self.out.exists():
                    self.out.unlink()
                self.drop(source)
                real_rename = os.rename
                moves = []

                def rename(src, dst):
                    if dst == str(self.out):
                        # Until this rename the reader sees no result; the temp file is whole.
                        self.assertFalse(self.out.exists())
                        moves.append((src, Path(src).read_text()))
                    return real_rename(src, dst)

                with mock.patch.object(os, "rename", rename):
                    self.run_loop()
                self.assertEqual(len(moves), 1)
                src, text = moves[0]
                self.assertEqual(src, str(self.out) + ".tmp")
                self.assertEqual(self.out.read_text(), text)
                self.assertFalse(Path(src).exists())
                if expected is None:
                    self.assertTrue(text.startswith("error\n"))
                    self.assertIn("ZeroDivisionError", text)
                else:
                    self.assertEqual(text, expected)

    def test_result_never_opened_for_writing_in_place(self):
        self.drop("RESULT = 1\n")
        opened = []
        real_open = open

        def spy(path, mode="r", *args, **kwargs):
            opened.append((str(path), mode))
            return real_open(path, mode, *args, **kwargs)

        self.env["open"] = spy
        self.run_loop()
        self.assertIn((str(self.out) + ".tmp", "w"), opened)
        self.assertNotIn(str(self.out), [path for path, mode in opened])


if __name__ == "__main__":
    unittest.main()
