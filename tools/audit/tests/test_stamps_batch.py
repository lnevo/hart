"""check_stamps current-batch, the one process that checks every job of a check.sh run, and check.sh's side of it:
the .cache folder made before the first batch and read_verdicts, which runs every job on any doubt."""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_stamps as cs  # noqa: E402
from stamps_case import RepoCase  # noqa: E402


REPO = cs.ROOT
CHECK_SH = (REPO / "tools" / "check.sh").read_text(encoding="utf-8")


class BatchTest(RepoCase):
    """current-batch checks every job in one process with one Checker (shared hash cache, git, plugin state, walks and
    snapshots); each job alone gets a Checker of its own, as one `current` process per job did. Both must give the same
    verdict, reason and snapshot for every job, whatever changed."""

    SHELL = RepoCase.JOB + "import subprocess\nsubprocess.run(['sh', '-c', 'true'])\n"
    NAMES = ["unit-hartlib", "unit-mimic", "a", "unit-hosts test_redeploy_commit", "unit-jmri test_x",
             "unit-hart-ops skipped (no ops/hart-ops/.venv)"]

    def setUp(self) -> None:
        super().setUp()
        patch = unittest.mock.patch.object(cs.ps, "unstampable", return_value=None)
        self.unstampable = patch.start()
        self.addCleanup(patch.stop)
        self.record("unit-hartlib")
        self.record("unit-mimic")
        # an untraceable program: the declaration (every file for a manifest check, CODE for unit-jmri)
        self.record("a", code=self.SHELL, script="shell_job.py")
        self.record("unit-jmri test_x", code=self.SHELL, script="shell_job.py")
        # unit-hosts test_redeploy_commit has no stamp; the placeholder is not stampable

    def alone(self) -> list[tuple[int, str | None, str | None]]:
        out = []
        for i, name in enumerate(self.NAMES):
            save = self.tmp / f"alone-{i}.stamp"
            save.unlink(missing_ok=True)
            ck = cs.Checker(self.root, self.store)
            try:
                code, reason = cs.verdict(name, ck, save)
            finally:
                ck.cache.save()
            out.append((code, reason, save.read_text() if save.exists() else None))
        return out

    def batch(self) -> list[tuple[int, str | None, str | None]]:
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        codes = cs.current_batch(self.NAMES, folder, True, self.root, self.store)
        lines = (folder / "verdicts").read_text().splitlines()
        self.assertEqual(lines, [f"{i}\t{c}" for i, c in enumerate(codes)])
        out = []
        for i, code in enumerate(codes):
            log, stamp = folder / f"{i}.stamplog", folder / f"{i}.stamp"
            reason = log.read_text().removeprefix("runs: ").removesuffix("\n") if log.exists() else None
            out.append((code, reason, stamp.read_text() if stamp.exists() else None))
        return out

    def same(self, want: list[int]) -> list[tuple[int, str | None, str | None]]:
        alone, batch = self.alone(), self.batch()
        self.assertEqual(batch, alone)
        self.assertEqual([v[0] for v in batch], want)
        return batch

    def test_no_change(self) -> None:
        got = self.same([0, 0, 0, 1, 0, 2])
        self.assertEqual(got[3][1], "no stamp")
        self.assertIn("not a stampable job", got[5][1])
        self.assertIsNone(got[5][2], "no snapshot for a job that is not stampable")

    def test_an_edit_to_a_file_the_jobs_read(self) -> None:
        (self.root / "tools/x/tests/test_a.py").write_text("v2\n")
        self.same([1, 1, 1, 1, 1, 2])

    def test_an_edit_only_the_declarations_cover(self) -> None:
        """The jobs that ran an untraceable program fall back to their declarations; the traced ones did not read it."""
        (self.root / "www/index.html").write_text("v2\n")           # in a's declaration, not in CODE
        self.same([0, 0, 1, 1, 0, 2])
        (self.root / "jmri/layouts/hart/data/switches.csv").write_text("v2\n")
        self.same([0, 0, 1, 1, 1, 2])

    def test_a_missing_stamp(self) -> None:
        cs._file("unit-mimic", self.store).unlink()
        self.assertEqual(self.same([0, 1, 0, 1, 0, 2])[1][1], "no stamp")

    def test_a_plugin_change(self) -> None:
        cs.ps.plugin_state.return_value = "another plugin commit"
        self.same([1, 1, 1, 1, 1, 2])

    def test_nothing_is_stampable_while_the_tables_or_plugin_say_so(self) -> None:
        self.unstampable.return_value = "HART_TABLES is set (x): the steps run on another tables file"
        got = self.same([2, 2, 2, 2, 2, 2])
        self.assertTrue(all(v[2] is None for v in got))

    def test_a_job_whose_check_fails_runs_records_nothing_and_loses_its_stamp(self) -> None:
        """Only that job: the others keep their verdicts; its stamp is dropped, so its next pass records afresh."""
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        real = cs.why_not_current

        def fail_on_mimic(name, *args, **kwargs):
            if name == "unit-mimic":
                raise OSError("disk gone")
            return real(name, *args, **kwargs)
        with unittest.mock.patch.object(cs, "why_not_current", side_effect=fail_on_mimic):
            codes = cs.current_batch(self.NAMES, folder, False, self.root, self.store)
        self.assertEqual(codes, [0, 2, 0, 1, 0, 2])
        self.assertIn("OSError: disk gone", (folder / "1.stamplog").read_text())
        self.assertFalse((folder / "1.stamp").exists())
        self.assertFalse(cs._file("unit-mimic", self.store).exists())
        self.assertEqual(self.alone()[1][:2], (1, "no stamp"))

    def test_a_retired_job_loses_its_stamp_and_may_not_be_queued(self) -> None:
        """The one static job's stamp (until ADR-037 stage 4b) is dropped by the first batch; queueing it is an error,
        not a job that quietly runs or skips."""
        old = cs._file("static", self.store)
        old.write_text("{}")
        folder = Path(tempfile.mkdtemp(dir=self.tmp))
        cs.current_batch(["unit-mimic"], folder, False, self.root, self.store)
        self.assertFalse(old.exists())
        with unittest.mock.patch.object(Path, "unlink", side_effect=PermissionError("read-only")):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(cs.current_batch(["unit-mimic"], folder, False, self.root, self.store), [0])
            self.assertIn("cannot drop the retired 'static' stamp: read-only", err.getvalue())
        with self.assertRaisesRegex(cs.BatchError, "'static', a job name check_stamps.RETIRED says it no longer runs"):
            cs.current_batch(["unit-mimic", "static"], folder, False, self.root, self.store)

    def test_a_batch_that_cannot_check_at_all_gives_no_verdicts(self) -> None:
        folder = self.tmp / "absent"
        with self.assertRaisesRegex(cs.BatchError, "is not a folder"):
            cs.current_batch(self.NAMES, folder, False, self.root, self.store)

    def test_the_names_and_the_folder_are_checked_first(self) -> None:
        names = self.tmp / "names"
        for text, says in (("", "names no job"), ("unit-mimic\n\nunit-hartlib\n", "line 2"),
                           (" unit-mimic\n", "line 1")):
            with self.subTest(text=text):
                names.write_text(text)
                with self.assertRaisesRegex(cs.BatchError, says):
                    cs.read_names(names)
        names.write_text("unit-mimic\nunit-cats\n")
        self.assertEqual(cs.read_names(names), ["unit-mimic", "unit-cats"])
        with self.assertRaisesRegex(cs.BatchError, "cannot read"):
            cs.read_names(self.tmp / "absent")
        with self.assertRaisesRegex(cs.BatchError, "is not a folder"):
            cs.current_batch(["unit-mimic"], self.tmp / "absent", False, self.root, self.store)

    def test_the_command_line(self) -> None:
        """`current` per job and one `current-batch`, as processes in this checkout with a scratch store."""
        names = ["unit-mimic", "unit-cats", "unit-hart-ops skipped (no ops/hart-ops/.venv)"]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HART_TRACE", "HART_TABLES"))}
        env["CHECK_STAMPS_DIR"] = str(self.store)
        tool = [sys.executable, str(REPO / "tools/audit/check_stamps.py")]

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([*tool, *args], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
        alone = [run("current", n, "--why").returncode for n in names]
        folder = self.tmp / "cli"
        folder.mkdir()
        (self.tmp / "names").write_text("".join(n + "\n" for n in names))
        done = run("current-batch", str(self.tmp / "names"), str(folder), "--why")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((folder / "verdicts").read_text(), "".join(f"{i}\t{c}\n" for i, c in enumerate(alone)))
        for args in (("current-batch", str(self.tmp / "names"), str(self.tmp / "nowhere")),
                     ("current-batch", str(self.tmp / "no-names"), str(folder))):
            with self.subTest(args=args[1:]):
                done = run(*args)
                self.assertEqual(done.returncode, 3)
                self.assertRegex(done.stderr, r"^check_stamps.py current-batch: ")
                self.assertNotIn("Traceback", done.stderr)
        done = run("record", "unit-mimic", str(folder / "0.stamp"), "--trace", "x", "--skipped", "two")
        self.assertEqual(done.returncode, 2)
        self.assertIn("--skipped takes a count", done.stdout)


class CheckShCacheTest(unittest.TestCase):
    """check.sh makes the checkout's .cache before any job starts: the panel check makes .cache/panel-stamps in a
    fresh worktree mid-run, and a job that listed the root before that recorded a listing the next run did not match
    (2026-11-24: 31 jobs reran on the second no-change run)."""

    LINE = 'if ! mkdir -p "$ROOT/.cache" 2>/dev/null; then'

    def test_it_comes_before_the_first_stamp_batch(self) -> None:
        self.assertEqual(CHECK_SH.count(self.LINE), 1)
        first_batch = CHECK_SH.index("\nstart_jobs\n")
        self.assertLess(CHECK_SH.index(self.LINE), first_batch)

    def block(self) -> str:
        start = CHECK_SH.index(self.LINE)
        return CHECK_SH[start:CHECK_SH.index("\nfi\n", start) + 4]

    def test_it_makes_the_folder_and_says_so_when_it_cannot(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            done = subprocess.run(["bash", "-c", f"set -uo pipefail\nROOT='{d}'\n{self.block()}"],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue((Path(d) / ".cache").is_dir())
            self.assertEqual(done.stdout, "")
            (Path(d) / "file").write_text("x")
            done = subprocess.run(["bash", "-c", f"set -uo pipefail\nROOT='{d}/file'\n{self.block()}"],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 0, "the run goes on")
            self.assertIn(f"cannot make {d}/file/.cache", done.stdout)


class CheckShVerdictsTest(unittest.TestCase):
    """check.sh's read_verdicts, with a stand-in python3: the batch's answers count only when it exits 0 and answers
    once for each queued job; anything else runs every job, records no stamp, and says why."""

    def verdicts(self, stub: str, stamps: str = "1") -> tuple[subprocess.CompletedProcess, str]:
        start = CHECK_SH.index("batch_failed() {")
        end = CHECK_SH.index("\n}\n", CHECK_SH.index("read_verdicts() {")) + 3
        block = CHECK_SH[start:end]
        with tempfile.TemporaryDirectory() as d:
            stub_dir = Path(d) / "bin"
            stub_dir.mkdir()
            # the stand-in also leaves a reason for job 0, as a --why batch would
            (stub_dir / "python3").write_text('#!/bin/bash\ncp "$3" "$4/names.seen"\necho "runs: x" >"$4/0.stamplog"\n'
                                              + stub)
            (stub_dir / "python3").chmod(0o755)
            (Path(d) / "jobs").mkdir()
            script = (f"set -uo pipefail\nnames=(a 'b c' d)\nverdicts=()\nSTAMPS={stamps}\nRECORD={stamps}\n"
                      f"STAMP_ENV=()\nSTAMP_WHY=()\nJOBS='{d}/jobs'\n{block}read_verdicts\n"
                      'echo "VERDICTS=${verdicts[*]}"\n')
            done = subprocess.run(["bash", "-c", script], env={**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}"},
                                  capture_output=True, text=True, timeout=30)
            seen = Path(d) / "jobs/names.seen"
            self.left = (Path(d) / "jobs/0.stamplog").exists()
            return done, seen.read_text() if seen.exists() else ""

    def test_a_good_batch_gives_each_job_its_verdict(self) -> None:
        done, names = self.verdicts("printf '0\\t0\\n1\\t1\\n2\\t2\\n' >\"$4/verdicts\"\n")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("VERDICTS=0 1 2", done.stdout)
        self.assertEqual(names, "a\nb c\nd\n")
        self.assertNotIn("every job runs", done.stdout)
        self.assertTrue(self.left)

    def test_anything_else_runs_every_job_and_says_why(self) -> None:
        for stub, says in (("echo 'job 1 (b c): OSError: disk gone' >&2\nexit 3\n", "OSError: disk gone"),
                           ("exit 0\n", "wrote no verdicts"),
                           ("printf '0\\t0\\n1\\t0\\n' >\"$4/verdicts\"\n", "verdicts for 2 of 3 jobs in 2 lines"),
                           ("printf '0\\t0\\n0\\t0\\n1\\t0\\n' >\"$4/verdicts\"\n", "verdicts for 2 of 3 jobs in 3 lines"),
                           ("printf '0\\t0\\n1\\tx\\n2\\t0\\n' >\"$4/verdicts\"\n", "no verdict of a queued job"),
                           ("printf '0\\t0\\n1\\t0\\n5\\t0\\n' >\"$4/verdicts\"\n", "no verdict of a queued job")):
            with self.subTest(says=says):
                done, _ = self.verdicts(stub)
                self.assertIn("VERDICTS=2 2 2", done.stdout)
                self.assertIn(says, done.stdout)
                self.assertIn("every job runs and none records a stamp", done.stdout)
                self.assertFalse(self.left, "a reason the failed batch wrote for one job is left to be printed")

    def test_no_stamps_no_batch(self) -> None:
        done, names = self.verdicts("exit 3\n", stamps="0")
        self.assertIn("VERDICTS=2 2 2", done.stdout)
        self.assertEqual(names, "", "the batch ran")
        self.assertNotIn("every job runs", done.stdout)


if __name__ == "__main__":
    unittest.main()
