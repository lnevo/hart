"""tools/ci/stamp_gate.py and check.sh's CI stamp modes: a pull request run skips only the jobs main's last full pass
covered, and any doubt about the stamps runs everything."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "ci"))
import stamp_gate as gate  # noqa: E402

BASE = "a" * 40
RUNNER = {"image_os": "ubuntu24", "runner_os": "Linux", "arch": "x86_64", "git": "git version 2.53.0", "bash": "GNU bash, version 5.2.21",
          "python": "3.13.9 (main)", "executable": "/opt/hostedtoolcache/Python/3.13.9/x64/bin/python3.13"}
DATA = ["www/data/fleet.json"]


class DecideTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "unit_mimic-0123456789.json").write_text("{}")
        self.manifest()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def manifest(self, **over) -> None:
        data = {"version": gate.VERSION, "sha": BASE, "runner": dict(RUNNER), "stamps": 1, **over}
        (self.dir / gate.MANIFEST).write_text(json.dumps(data))

    def decide(self, changed=None, **kw) -> str | None:
        kw.setdefault("now", dict(RUNNER))
        kw.setdefault("base", BASE)
        return gate.decide(self.dir, changed=DATA if changed is None else changed, **kw)

    def test_matching_stamps_for_the_merge_base_skip(self) -> None:
        self.assertIsNone(self.decide())

    def test_stamps_made_on_another_main_commit_mean_full(self) -> None:
        self.assertIn("not on the merge base", self.decide(base="b" * 40))
        self.manifest(sha="c" * 40)
        self.assertIn("not on the merge base", self.decide())

    def test_no_or_unreadable_manifest_means_full(self) -> None:
        (self.dir / gate.MANIFEST).write_text("{not json")
        self.assertIn("cannot be read", self.decide())
        (self.dir / gate.MANIFEST).unlink()
        self.assertIn("no stamps from main", self.decide())
        self.manifest(version=99)
        self.assertIn("another version", self.decide())
        self.manifest(runner="linux")
        self.assertIn("names no runner", self.decide())

    def test_another_runner_or_python_means_full(self) -> None:
        for k, v in (("python", "3.13.10"), ("image_os", "ubuntu26"), ("arch", "aarch64"), ("runner_os", "macOS"),
                     ("git", "git version 2.54.0"), ("bash", "GNU bash, version 5.3")):
            with self.subTest(k):
                self.assertIn(f"another runner ({k}", self.decide(now={**RUNNER, k: v}))
        self.assertIn("another runner (extra", self.decide(now={**RUNNER, "extra": "x"}))

    def test_no_stamp_files_means_full(self) -> None:
        (self.dir / "unit_mimic-0123456789.json").unlink()
        (self.dir / "filehash.json").write_text("{}")
        self.assertIn("holds no stamps", self.decide())

    def test_the_label_or_the_commit_token_forces_full(self) -> None:
        self.assertIn("full-ci label", self.decide(labels=["docs", " full-ci"]))
        self.assertIsNone(self.decide(labels=["full-ci-later", ""]))
        self.assertIn("[full-ci]", self.decide(message="fix: a thing\n\n[full-ci]\n"))
        self.assertIsNone(self.decide(message="fix: full ci another day"))

    def test_a_new_plugin_pin_forces_full(self) -> None:
        self.assertIn("plugin pin", self.decide(pin_changed=True))

    def test_a_change_to_check_sh_the_workflow_or_the_stamp_code_forces_full(self) -> None:
        for p in ("tools/check.sh", ".github/workflows/check.yml", "tools/ci/stamp_gate.py", "tools/ci/changed_kind.py",
                  "tools/audit/check_stamps.py", "tools/audit/traced.py", "tools/audit/trace_hook/sitecustomize.py",
                  "tools/schematic/panel_stamps.py", "tools/hartlib/src/hartlib/paths.py",
                  "tools/audit/stamp_audit/sitecustomize.py", "./tools/check.sh"):
            with self.subTest(p):
                self.assertIn("machinery", self.decide(changed=[*DATA, p]))
        for p in ("tools/check.sh.bak", "tools/cia.py", ".github/workflows/other.yml", "tools/audit/tracedx.py"):
            with self.subTest(p):
                self.assertIsNone(self.decide(changed=[p]))

    def test_no_changed_paths_or_no_base_means_full(self) -> None:
        self.assertIn("no changed paths", self.decide(changed=["", " "]))
        self.assertIn("no merge base", self.decide(base=""))

    def test_cli_exit_codes(self) -> None:
        def cli(*args, stdin="www/data/fleet.json\n"):
            return subprocess.run([sys.executable, str(ROOT / "tools/ci/stamp_gate.py"), *args], input=stdin,
                                  capture_output=True, text=True, timeout=30)
        done = cli("decide", str(self.dir), "--base", "b" * 40)
        self.assertEqual(3, done.returncode)
        self.assertTrue(done.stdout.startswith("full: "))
        done = cli("decide", str(self.dir), "--base", BASE, "--labels", "full-ci")
        self.assertEqual((3, "full: the pull request has the full-ci label\n"), (done.returncode, done.stdout))
        done = cli("decide", str(self.dir), "--base", BASE, "--message-file", str(self.dir / "nowhere"))
        self.assertEqual(3, done.returncode)


class ManifestTest(unittest.TestCase):
    def test_manifest_names_the_commit_and_runner_and_drops_the_file_hash_cache(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "filehash.json").write_text("{}")
            (Path(d) / "static-0123456789.json").write_text("{}")
            gate.write_manifest(Path(d), BASE)
            data = json.loads((Path(d) / gate.MANIFEST).read_text())
            self.assertEqual((BASE, 1, gate.runner()), (data["sha"], data["stamps"], data["runner"]))
            self.assertFalse((Path(d) / "filehash.json").exists())
            self.assertIsNone(gate.decide(Path(d), BASE, DATA))
            with self.assertRaises(SystemExit):
                gate.write_manifest(Path(d), "main")


class CheckShModesTest(unittest.TestCase):
    """check.sh with CHECK_RECORD_TO (main's push run) and CHECK_SKIP_FROM (a pull request run), on one small job."""

    JOB = "^unit-mimic$"

    def check_sh(self, **env) -> subprocess.CompletedProcess:
        base = {k: v for k, v in os.environ.items()
                if k not in ("HART_TABLES", "FULL", "CI", "CHECK_AUDIT", "CHECK_SKIP_FROM", "CHECK_RECORD_TO",
                             "CHECK_SKIP_NOTE", "CHECK_STAMPS_DIR", "HART_TRACE_LOG", "HART_TRACE_SPAWN")}
        return subprocess.run(["bash", str(ROOT / "tools/check.sh")], env={**base, "CHECK_ONLY": self.JOB, **env},
                              capture_output=True, text=True, timeout=300, cwd=ROOT)

    def test_record_then_skip_and_a_skip_run_records_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            stamps = Path(d) / "stamps"
            done = self.check_sh(CI="1", CHECK_RECORD_TO=str(stamps))
            self.assertEqual(0, done.returncode, done.stdout[-2000:])
            recorded = sorted(p.name for p in stamps.glob("unit_mimic-*.json"))
            if not recorded:
                self.skipTest("unit-mimic recorded no stamp here (unstampable in this checkout)\n" + done.stdout[-500:])
            done = self.check_sh(CI="1", CHECK_SKIP_FROM=str(stamps), CHECK_SKIP_NOTE="current on main abc123")
            self.assertEqual(0, done.returncode, done.stdout[-2000:])
            self.assertIn("unit-mimic: current on main abc123, skipped", done.stdout)
            self.assertIn("1 of 1 jobs current on main abc123, skipped; 0 ran", done.stdout)
            # FULL=1 runs it even with matching stamps
            done = self.check_sh(CI="1", CHECK_SKIP_FROM=str(stamps), FULL="1")
            self.assertNotIn("skipped", done.stdout)
            self.assertIn("--- unit-mimic (", done.stdout)
            # a skip run with no stamps runs the job and writes none
            empty = Path(d) / "empty"
            empty.mkdir()
            done = self.check_sh(CI="1", CHECK_SKIP_FROM=str(empty))
            self.assertIn("--- unit-mimic (", done.stdout)
            self.assertEqual([], sorted(p.name for p in empty.glob("unit_mimic-*.json")))
            self.assertIn("runs: no stamp", done.stdout)
            # a stamp for a job whose inputs differ is not a skip: another key in the same file
            stamp = stamps / recorded[0]
            data = json.loads(stamp.read_text())
            data["key"] = "0" * 64
            stamp.write_text(json.dumps(data))
            done = self.check_sh(CI="1", CHECK_SKIP_FROM=str(stamps))
            self.assertIn("--- unit-mimic (", done.stdout)
            self.assertIn("runs: the code, command, interpreter, plugin or environment changed", done.stdout)

    def test_the_jobs_never_inherit_the_modes(self) -> None:
        """A job that runs check.sh itself (test_check_stamps.AuditTest) must not see main's stamp folder."""
        text = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
        start = text.index('SKIP_NOTE="current"')
        block = text[start:text.index("\n", text.index("unset CHECK_RECORD_TO")) + 1]
        show = ('env | grep -E "^CHECK_(RECORD_TO|SKIP_FROM|SKIP_NOTE|STAMPS_DIR)=" || true\n'
                'echo "NOTE=$SKIP_NOTE ENV=${STAMP_ENV[*]}"\n')
        with tempfile.TemporaryDirectory() as d:
            for mode in ("CHECK_RECORD_TO", "CHECK_SKIP_FROM"):
                with self.subTest(mode):
                    # FULL=1 (a full check.sh run) takes the no-stamps branch: drop it, as check_sh() does
                    env = {k: v for k, v in os.environ.items() if not k.startswith("CHECK_") and k != "FULL"}
                    done = subprocess.run(["bash", "-c", "STAMPS=0\nRECORD=0\n" + block + show],
                                          env={**env, "CI": "1", mode: d, "CHECK_SKIP_NOTE": "current on main abc"},
                                          capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, done.returncode, done.stderr)
                    self.assertNotRegex(done.stdout, r"(?m)^CHECK_")
                    self.assertIn(f"ENV=CHECK_STAMPS_DIR={d}", done.stdout)

    def test_the_modes_are_for_ci_only_and_one_at_a_time(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            done = self.check_sh(CHECK_SKIP_FROM=d)
            self.assertEqual(2, done.returncode)
            self.assertIn("for CI runs only", done.stderr)
            done = self.check_sh(CI="1", CHECK_SKIP_FROM=d, CHECK_RECORD_TO=d)
            self.assertEqual(2, done.returncode)
            self.assertIn("either records or skips", done.stderr)
            done = self.check_sh(CI="1", CHECK_SKIP_FROM=str(Path(d) / "nowhere"))
            self.assertEqual(2, done.returncode)


class WorkflowTest(unittest.TestCase):
    """check.yml wires the gate as designed (read from the file; the gate's logic is tested above)."""

    def setUp(self) -> None:
        self.text = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")

    def test_pull_requests_restore_only_the_exact_merge_base_stamps(self) -> None:
        restore = self.text.index("uses: actions/cache/restore@v4")
        block = self.text[restore:self.text.index("- name:", restore)]
        self.assertIn("key: check-stamps-${{ steps.base.outputs.sha }}", block)
        self.assertNotIn("restore-keys", block)
        self.assertIn("run: echo \"sha=$(git rev-parse HEAD^1)\"", self.text)

    def test_only_a_push_run_records_and_saves(self) -> None:
        self.assertIn("CHECK_RECORD_TO: ${{ github.event_name == 'push' && ", self.text)
        save = self.text.index("uses: actions/cache/save@v4")
        self.assertIn("if: github.event_name == 'push'", self.text[save - 200:save])
        self.assertIn("key: check-stamps-${{ github.sha }}", self.text[save:])
        self.assertLess(self.text.index("run: ./tools/check.sh"), save)

    def test_the_docs_path_and_no_label_trigger(self) -> None:
        """No `labeled` trigger: a run for any label would cancel the pull request's run in progress (the gate reads
        the labels live, so a re-run after adding full-ci sees it)."""
        self.assertIn("if: github.event_name == 'pull_request' && steps.kind.outputs.kind != 'docs'", self.text)
        self.assertNotIn("types:", self.text[:self.text.index("push:")])
        self.assertIn("|| labels=full-ci", self.text)

    def gate_block(self) -> str:
        start = self.text.index("        run: |", self.text.index("name: Skip what main covered?"))
        lines = []
        for line in self.text[start:].splitlines()[1:]:
            if line.strip() and not line.startswith("          "):
                break
            lines.append(line[10:])
        return "\n".join(lines) + "\n"

    def run_gate(self, gh: str, base: str) -> tuple[subprocess.CompletedProcess, str]:
        """The gate step's script under `bash -e` (GitHub's default shell), with a stand-in gh on PATH, in this
        checkout (HEAD^1 and HEAD are any two commits: the paths between them are what the gate sees)."""
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "bin"
            stub.mkdir()
            (stub / "gh").write_text("#!/bin/sh\n" + gh)
            (stub / "gh").chmod(0o755)
            out = Path(d) / "out"
            env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "GITHUB_OUTPUT": str(out),
                   "GITHUB_REPOSITORY": "o/r", "GITHUB_WORKSPACE": str(ROOT), "RUNNER_TEMP": d, "PR": "1",
                   "BASE": base, "PIN_CHANGED": "false", "GH_TOKEN": "x"}
            done = subprocess.run(["bash", "-e", "-c", self.gate_block()], cwd=ROOT, env=env, capture_output=True,
                                  text=True, timeout=60)
            return done, out.read_text() if out.exists() else ""

    def test_a_full_verdict_runs_everything_and_does_not_end_the_step(self) -> None:
        done, out = self.run_gate('case "$*" in *labels*) echo docs;; *) echo "fix: a thing";; esac\n', "b" * 40)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("full: ", done.stdout)
        self.assertIn("::notice::every check.sh job runs", done.stdout)
        self.assertNotIn("skip_from=", out)

    def test_a_failed_label_or_message_lookup_runs_everything(self) -> None:
        done, out = self.run_gate("exit 1\n", "b" * 40)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("full: the pull request has the full-ci label", done.stdout)
        self.assertNotIn("skip_from=", out)


if __name__ == "__main__":
    unittest.main()
