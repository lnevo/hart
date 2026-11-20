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


class JavaThrowable(BaseException):
    """Stands for java.lang.Throwable: in Jython it is not a Python Exception."""


class JavaException(JavaThrowable):
    """Stands for java.lang.Exception."""


class JavaError(JavaThrowable):
    """Stands for java.lang.Error, which java.lang.Exception does not cover."""


class Unprintable(Exception):
    def __str__(self):
        raise RuntimeError("no message")


FAILED = "jmri_cmd_watcher: command handling failed: "


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
        lang = self.env["java"].lang
        lang.Throwable, lang.Exception, lang.Error = JavaThrowable, JavaException, JavaError
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

    def failing_rename(self, to, errors):
        """os.rename that raises the next of `errors` (None = works) for each move onto `to`."""
        real_rename = os.rename
        errors = list(errors)

        def rename(src, dst):
            if dst == to and errors:
                error = errors.pop(0)
                if error is not None:
                    raise error
            return real_rename(src, dst)

        return mock.patch.object(os, "rename", rename)

    def test_java_error_in_a_command_reports_error_and_watcher_runs_the_next(self):
        self.drop("raise java.lang.Error('java error')\n")
        seen = []

        def next_command():
            seen.append(self.out.read_text())
            self.drop("RESULT = 'second'\n")

        printed = self.run_loop(next_command)
        self.assertTrue(seen[0].startswith("error\n"), seen[0])
        self.assertIn("java error", seen[0])
        self.assertEqual(self.out.read_text(), "ok\nsecond")
        self.assertEqual(printed, "")

    def test_java_error_while_handling_is_printed_and_watcher_runs_the_next(self):
        self.drop("RESULT = 'first'\n")
        with self.failing_rename(self.env["LAST"], [JavaError("java ran out of something")]):
            printed = self.run_loop(lambda: None)
        self.assertEqual(printed, FAILED + "java ran out of something\n")
        self.assertEqual(self.out.read_text(), "ok\nfirst")

    def test_sys_exit_in_a_command_reports_error_and_watcher_runs_the_next(self):
        for source in ("import sys\nsys.exit(3)\n", "raise SystemExit('stop now')\n"):
            with self.subTest(source=source):
                self.drop(source)
                seen = []

                def next_command():
                    seen.append(self.out.read_text())
                    self.drop("RESULT = 'second'\n")

                printed = self.run_loop(next_command)
                self.assertTrue(seen[0].startswith("error\n"), seen[0])
                self.assertIn("SystemExit", seen[0])
                self.assertEqual(self.out.read_text(), "ok\nsecond")
                self.assertEqual(printed, "")

    def test_sys_exit_while_handling_is_printed_and_watcher_runs_the_next(self):
        self.drop("RESULT = 'first'\n")
        with self.failing_rename(self.env["LAST"], [SystemExit("handler exit")]):
            printed = self.run_loop(lambda: None)
        self.assertEqual(printed, FAILED + "handler exit\n")
        self.assertEqual(self.out.read_text(), "ok\nfirst")

    def test_persisting_failure_is_printed_once_until_it_changes_or_clears(self):
        self.drop("RESULT = 'first'\n")
        same = lambda: OSError("cannot move the command")  # noqa: E731
        errors = [same(), same(), same(), OSError("another reason"), OSError("another reason"), None, same()]
        results = []

        def look():
            results.append(self.out.read_text() if self.out.exists() else None)

        def second_command():
            look()
            self.drop("RESULT = 'second'\n")

        # Passes 1-5 fail on the same command, pass 6 runs it, pass 7 fails on the second one.
        with self.failing_rename(self.env["LAST"], errors):
            printed = self.run_loop(look, look, look, look, look, second_command, look)
        self.assertEqual(printed.splitlines(), [
            FAILED + "cannot move the command",
            FAILED + "another reason",
            FAILED + "cannot move the command",
        ])
        # The caller finds an error result while the failure stands; it is not removed and
        # rewritten on every pass, and it says the command is still waiting.
        first = "error\n" + FAILED + "cannot move the command\nThe command is still waiting and is tried again.\n"
        other = first.replace("cannot move the command", "another reason")
        self.assertEqual(results, [first, first, first, other, other, "ok\nfirst", first])
        self.assertEqual(self.out.read_text(), "ok\nsecond")

    def test_result_write_failure_leaves_an_error_result_and_watcher_runs_the_next(self):
        self.drop("RESULT = 'first'\n")
        seen = []

        def next_command():
            seen.append(self.out.read_text())
            self.drop("RESULT = 'second'\n")

        with self.failing_rename(str(self.out), [OSError("disk trouble")]):
            printed = self.run_loop(next_command)
        self.assertEqual(printed, FAILED + "disk trouble\n")
        self.assertEqual(seen, ["error\n" + FAILED + "disk trouble\n"
                                "The command file is gone (it ran, or was removed) and is not run again.\n"])
        self.assertEqual(self.out.read_text(), "ok\nsecond")

    def test_result_that_cannot_be_written_at_all_is_printed_and_watcher_runs_the_next(self):
        self.drop("RESULT = 'first'\n")
        seen = []

        def next_command():
            seen.append(self.out.exists())
            self.drop("RESULT = 'second'\n")

        with self.failing_rename(str(self.out), [OSError("disk trouble"), JavaError("still no disk")]):
            printed = self.run_loop(next_command)
        self.assertEqual(printed, FAILED + "disk trouble\n"
                         "jmri_cmd_watcher: no result could be written: still no disk\n")
        self.assertEqual(seen, [False])
        self.assertEqual(self.out.read_text(), "ok\nsecond")

    def test_failure_whose_message_cannot_be_formatted_does_not_end_the_watcher(self):
        self.drop("RESULT = 'first'\n")
        with self.failing_rename(self.env["LAST"], [Unprintable()]):
            printed = self.run_loop(lambda: None)
        self.assertEqual(printed, FAILED + "Unprintable (its message could not be printed)\n")
        self.assertEqual(self.out.read_text(), "ok\nfirst")

    def test_command_error_whose_traceback_cannot_be_formatted_still_reports_error(self):
        self.drop("raise ValueError('boom')\n")
        self.env["traceback"] = types.SimpleNamespace(format_exc=mock.Mock(side_effect=Unprintable()))
        printed = self.run_loop()
        self.assertEqual(self.out.read_text(), "error\nboom")
        self.assertEqual(printed, "")

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
