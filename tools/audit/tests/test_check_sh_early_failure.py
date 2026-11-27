"""tools/check.sh prints a failed job as soon as it ends, while a job queued ahead of it still runs, and its final
pass (every job in queue order, the results file, the last line) is the same as without the early report. Run in a
scratch repo (test_pipeline_manifest.scratch_check_sh) whose first job waits until the test releases it."""
from __future__ import annotations

import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

# its folder is on sys.path under discover
from test_pipeline_manifest import OWN, scratch_check_sh

# panels-tables is queued first; it waits for the release file the test makes once it has seen the early report, and
# fails after 30 s without it, so a pass shows the report came while it still ran
SLOW = ("import os, sys, time\nend = time.time() + 30\n"
        "while not os.path.exists(os.environ['STUB_RELEASE']):\n"
        "    if time.time() > end:\n        sys.exit('never released')\n    time.sleep(0.05)\nprint('slow released')\n")
STATIC = ("panels-tables python3 tools/slow.py\none python3 tools/a.py --check\n"
          "gone python3 tools/none.py\n")
EARLY = re.compile(r"(?ms)^EARLY FAILURE: (\S+) FAILED \(\d+s\), more jobs still running\n(.*?)"
                   r"^EARLY FAILURE: end of \1; every job is reported in queue order once all have ended\n")


class EarlyFailure(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.s = scratch_check_sh(Path(cls.tmp.name))
        cls.s.write("tools/slow.py", SLOW)
        cls.s.commit("slow stand-in")
        subprocess.run(["git", "-C", str(cls.s.repo), "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_streamed(self, static: str, release: Path, results: Path) -> tuple[int, str, bool]:
        """check.sh's exit code and output, and whether the slow job was still waiting when the early report came."""
        env = self.s.check_sh_env(STUB_PIN="", STUB_STATIC=static, STUB_OWN=OWN, FULL="1", CHECK_MAX_JOBS="4",
                                  CHECK_ONLY="^(panels-tables|one|gone)$", STUB_RELEASE=str(release),
                                  CHECK_RESULTS_TO=str(results))
        out, early_while_waiting, start = [], False, time.time()
        with subprocess.Popen(["bash", str(self.s.repo / "tools/check.sh")], cwd=self.s.repo, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
            assert proc.stdout is not None
            for line in proc.stdout:
                out.append(line)
                if line.startswith("EARLY FAILURE: end of ") and not release.exists():
                    early_while_waiting = True
                    release.touch()
                self.assertLess(time.time() - start, 50, "check.sh did not end")
            release.touch()
            return proc.wait(timeout=30), "".join(out), early_while_waiting

    def test_a_quick_failure_is_printed_while_a_slow_job_runs_and_again_in_its_place(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            results = Path(d) / "results.tsv"
            rc, out, early = self.run_streamed(STATIC, Path(d) / "release", results)
            self.assertEqual(1, rc, out)
            self.assertTrue(early, out)
            reports = EARLY.findall(out)
            self.assertEqual(["gone"], [name for name, _ in reports], out)
            final = EARLY.sub("", out)
            self.assertLess(out.index("EARLY FAILURE: gone"), out.index("--- panels-tables ("))
            heads = [line.split(" (")[0] for line in final.splitlines() if line.startswith("--- ")]
            self.assertEqual(["--- panels-tables", "--- one", "--- gone FAILED"], heads)
            self.assertIn("slow released\n", final)
            # the final pass prints the failed job's whole log again under its heading
            self.assertIn(reports[0][1], final[final.index("--- gone FAILED"):])
            self.assertIn("none.py", reports[0][1])
            self.assertEqual("FAILED", final.splitlines()[-1])
            self.assertEqual("panels-tables\tpassed\none\tpassed\ngone\tfailed\n", results.read_text())

    def test_a_run_with_no_failure_prints_no_early_report(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            release = Path(d) / "release"
            release.touch()
            rc, out, _ = self.run_streamed(STATIC.replace("tools/none.py", "tools/a.py"), release,
                                           Path(d) / "results.tsv")
        self.assertEqual(0, rc, out)
        self.assertNotIn("EARLY FAILURE", out)
        self.assertEqual("ALL PASSED", out.splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
