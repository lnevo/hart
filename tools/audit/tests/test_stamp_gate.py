"""tools/ci/stamp_gate.py and check.sh's CI stamp modes: a pull request run skips only the jobs main's last full pass
covered, and any doubt about the stamps runs everything; each passing pull request run records what it skipped, and
the weekly full run fails when a job one of them skipped fails in full."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
                  "tools/audit/stamp_audit/sitecustomize.py", "tools/audit/trace_hook/hook_chain.py", "./tools/check.sh"):
            with self.subTest(p):
                self.assertIn("machinery", self.decide(changed=[*DATA, p]))
        for p in ("tools/check.sh.bak", "tools/cia.py", ".github/workflows/other.yml", "tools/audit/tracedx.py"):
            with self.subTest(p):
                self.assertIsNone(self.decide(changed=[p]))

    def test_each_part_of_the_manifest_loader_forces_full(self) -> None:
        """manifest.py's FILES (it and the parts it imports) are each MACHINERY: a split part is no way around it."""
        spec = importlib.util.spec_from_file_location("stamp_gate_test_manifest", ROOT / "tools/pipeline/manifest.py")
        manifest = importlib.util.module_from_spec(spec)
        path_before = list(sys.path)
        with mock.patch.dict(sys.modules, {spec.name: manifest}):  # its dataclasses look their module up there
            spec.loader.exec_module(manifest)
        self.assertEqual(sys.path, path_before)         # tools/pipeline is on sys.path only while the parts import
        on_disk = {p.relative_to(ROOT).as_posix() for p in (ROOT / "tools/pipeline").glob("manifest*.py")}
        self.assertEqual(set(manifest.FILES), on_disk)  # a new manifest_*.py part must be in PARTS, so in FILES
        self.assertGreater(len(manifest.FILES), 1)
        for p in manifest.FILES:
            with self.subTest(p):
                self.assertIn(p, gate.MACHINERY)
                self.assertIn("machinery", self.decide(changed=[*DATA, p]))

    def test_each_part_of_the_stamp_code_forces_full(self) -> None:
        """check_stamps.py's FILES (it and the parts it imports, loaded by path from another folder as check.sh does)
        are each MACHINERY: a split part is no way around it."""
        probe = ("import importlib.util, json, sys\n"
                 "spec = importlib.util.spec_from_file_location('cs_by_path', sys.argv[1])\n"
                 "cs = importlib.util.module_from_spec(spec)\n"
                 "sys.modules[spec.name] = cs\n"
                 "spec.loader.exec_module(cs)\n"
                 "print(json.dumps(cs.FILES))\n")
        with tempfile.TemporaryDirectory() as cwd:
            done = subprocess.run([sys.executable, "-c", probe, str(ROOT / "tools/audit/check_stamps.py")], cwd=cwd,
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        files = json.loads(done.stdout)
        on_disk = {p.relative_to(ROOT).as_posix() for p in (ROOT / "tools/audit").glob("stamps_*.py")}
        self.assertEqual(set(files), {"tools/audit/check_stamps.py", *on_disk})  # a new stamps_*.py part is in PARTS
        self.assertGreater(len(files), 1)
        for p in files:
            with self.subTest(p):
                self.assertIn(p, gate.MACHINERY)
                self.assertIn("machinery", self.decide(changed=[*DATA, p]))

    def test_each_part_of_the_trace_hook_forces_full(self) -> None:
        """traced.HOOK_FILES (traced.py, its traced_*.py parts, the hook and its hook_chain.py) are each MACHINERY: a
        split part of the trace code is no way around it."""
        spec = importlib.util.spec_from_file_location("stamp_gate_test_traced", ROOT / "tools/audit/traced.py")
        traced = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(traced)
        on_disk = {p.relative_to(ROOT).as_posix() for p in (ROOT / "tools/audit").glob("traced_*.py")}
        self.assertTrue(on_disk)
        self.assertEqual(set(traced.HOOK_FILES),
                         {"tools/audit/traced.py", "tools/audit/trace_hook/sitecustomize.py",
                          "tools/audit/trace_hook/hook_chain.py", *on_disk})
        for p in traced.HOOK_FILES:
            with self.subTest(p):
                folder = "tools/audit/trace_hook/"
                self.assertIn(folder if p.startswith(folder) else p, gate.MACHINERY)
                self.assertIn("machinery", self.decide(changed=[*DATA, p]))

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
        block = text[start:text.index("\nfi\n", text.index("unset CHECK_RESULTS_TO")) + 4]
        show = ('env | grep -E "^CHECK_(RECORD_TO|SKIP_FROM|SKIP_NOTE|STAMPS_DIR|RESULTS_TO)=" || true\n'
                'echo "NOTE=$SKIP_NOTE ENV=${STAMP_ENV[*]} RESULTS=$RESULTS_TO"\n')
        with tempfile.TemporaryDirectory() as d:
            for mode in ("CHECK_RECORD_TO", "CHECK_SKIP_FROM"):
                with self.subTest(mode):
                    # FULL=1 (a full check.sh run) takes the no-stamps branch: drop it, as check_sh() does
                    env = {k: v for k, v in os.environ.items() if not k.startswith("CHECK_") and k != "FULL"}
                    results = f"{d}/results.tsv"
                    done = subprocess.run(["bash", "-c", "STAMPS=0\nRECORD=0\n" + block + show],
                                          env={**env, "CI": "1", mode: d, "CHECK_SKIP_NOTE": "current on main abc",
                                               "CHECK_RESULTS_TO": results},
                                          capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, done.returncode, done.stderr)
                    self.assertNotRegex(done.stdout, r"(?m)^CHECK_")
                    self.assertIn(f"ENV=CHECK_STAMPS_DIR={d}", done.stdout)
                    self.assertIn(f"RESULTS={results}", done.stdout)

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


HEAD = "b" * 40


class SkipRecordTest(unittest.TestCase):
    """record-skips and check-skips: the record a passing pull request run keeps, and the weekly full run's check."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def results(self, text: str, name: str = "results.tsv") -> Path:
        path = self.dir / name
        path.write_text(text)
        return path

    def record(self, skipped: list[str], pr: int = 7, run: int = 70, folder: str = "records") -> dict:
        rec = gate.skip_record({**{j: "skipped" for j in skipped}, "other": "passed"}, pr, run, BASE, HEAD)
        (self.dir / folder / str(run)).mkdir(parents=True, exist_ok=True)
        (self.dir / folder / str(run) / "skips.json").write_text(json.dumps(rec))
        return rec

    def test_the_results_file_is_read_whole_or_refused(self) -> None:
        self.assertEqual(gate.read_results(self.results("a\tpassed\nunit-x y\tskipped\nb\tfailed\n")),
                         {"a": "passed", "unit-x y": "skipped", "b": "failed"})
        for text, why in (("", "names no job"), ("a passed\n", "is not"), ("a\tran\n", "is not"),
                          (" a\tpassed\n", "is not"), ("a\tpassed\na\tfailed\n", "listed twice")):
            with self.subTest(text=text), self.assertRaisesRegex(gate.GateError, why):
                gate.read_results(self.results(text))
        with self.assertRaisesRegex(gate.GateError, "cannot read check.sh's results"):
            gate.read_results(self.dir / "absent.tsv")

    def test_a_passing_run_records_the_jobs_it_skipped(self) -> None:
        rec = gate.skip_record({"b": "skipped", "a": "skipped", "c": "passed"}, 7, 70, BASE, HEAD)
        self.assertEqual(rec, {"version": gate.SKIPS_VERSION, "pr": 7, "run": 70, "base": BASE, "head": HEAD,
                               "skipped": ["a", "b"], "ran": 1})
        self.assertEqual(gate.skip_record({"c": "passed"}, 7, 70, BASE, HEAD)["skipped"], [])
        for args, why in ((({"c": "failed"}, 7, 70, BASE, HEAD), "failed jobs \\(c\\)"),
                          (({"c": "passed"}, 0, 70, BASE, HEAD), "positive numbers"),
                          (({"c": "passed"}, 7, 70, "main", HEAD), "--base 'main' is not a commit"),
                          (({"c": "passed"}, 7, 70, BASE, ""), "--head '' is not a commit")):
            with self.subTest(why=why), self.assertRaisesRegex(gate.GateError, why):
                gate.skip_record(*args)

    def test_a_failed_job_a_pull_request_skipped_is_named(self) -> None:
        recs = [self.record(["x", "gone-job"], pr=7, run=70), self.record(["x"], pr=8, run=80), self.record(["y"])]
        errors, notes = gate.wrong_skips({"x": "failed", "y": "passed", "z": "failed", "other": "passed"}, recs)
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(errors[0].startswith("x: fails in this full run, and pull request #7 (run 70"), errors[0])
        self.assertIn("python3 tools/audit/check_stamps.py why x", errors[0])
        self.assertIn("pull request #8", errors[1])
        self.assertFalse(any(e.startswith("z:") for e in errors), "z failed, but no pull request skipped it")
        self.assertIn("3 skip record(s) from pull request runs, 4 skipped job(s); 2 of 4 jobs failed", notes[0])
        self.assertIn("skipped then, not run now (renamed or removed): gone-job", notes[1])
        self.assertEqual(gate.wrong_skips({"x": "passed"}, recs)[0], [])

    def test_the_weekly_results_must_be_a_full_run(self) -> None:
        with self.assertRaisesRegex(gate.GateError, "skip 1 job\\(s\\) \\(x\\): not a full run"):
            gate.wrong_skips({"x": "skipped"}, [])

    def test_a_record_that_cannot_be_read_is_an_error_not_no_skips(self) -> None:
        good = self.record(["x"])
        for data, why in (("not json", "not a skip record"), ({**good, "version": 9}, "of version 1"),
                          ({**good, "skipped": "x"}, "needs pr, run"), ({**good, "pr": "7"}, "needs pr, run"),
                          ({**good, "head": "main"}, "needs pr, run")):
            with self.subTest(why=why):
                path = self.dir / "bad.json"
                path.write_text(data if isinstance(data, str) else json.dumps(data))
                with self.assertRaisesRegex(gate.GateError, why):
                    gate.read_record(path)

    def cli(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "tools/ci/stamp_gate.py"), *argv], capture_output=True,
                              text=True, timeout=60)

    def test_the_command_line(self) -> None:
        out = self.dir / "rec" / "skips.json"
        done = self.cli("record-skips", str(self.results("a\tskipped\nb\tpassed\n")), "--pr", "7", "--run", "70",
                        "--base", BASE, "--head", HEAD, "--out", str(out))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("1 of 2 jobs skipped", done.stdout)
        self.assertEqual(json.loads(out.read_text())["skipped"], ["a"])
        done = self.cli("check-skips", str(self.results("a\tfailed\nb\tpassed\n", "full.tsv")), str(self.dir / "rec"))
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn("::error::wrong skip? a: fails in this full run, and pull request #7", done.stdout)
        done = self.cli("check-skips", str(self.results("a\tpassed\nb\tfailed\n", "full.tsv")), str(self.dir / "rec"))
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        for argv, why in ((("check-skips", str(self.dir / "full.tsv"), str(self.dir / "nowhere")), "is not a folder"),
                          (("check-skips", str(self.results("", "empty.tsv")), str(self.dir / "rec")), "names no job"),
                          (("record-skips", str(self.results("a\tfailed\n", "failed.tsv")), "--pr", "7", "--run", "70", "--base",
                            BASE, "--head", HEAD, "--out", str(out)), "failed jobs")):
            with self.subTest(why=why):
                done = self.cli(*argv)
                self.assertEqual(2, done.returncode, done.stdout + done.stderr)
                self.assertIn(why, done.stderr)
                self.assertNotIn("Traceback", done.stderr)
        (self.dir / "rec" / "broken.json").write_text("{")
        done = self.cli("check-skips", str(self.dir / "full.tsv"), str(self.dir / "rec"))
        self.assertEqual(2, done.returncode)
        self.assertIn("broken.json: not a skip record", done.stderr)


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
        self.assertIn("if: github.event_name == 'pull_request' && steps.kind.outputs.kind == 'full'", self.text)
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

    def step_block(self, name: str) -> str:
        start = self.text.index("        run: |", self.text.index(f"name: {name}"))
        lines = []
        for line in self.text[start:].splitlines()[1:]:
            if line.strip() and not line.startswith("          "):
                break
            lines.append(line[10:])
        return "\n".join(lines) + "\n"

    GH_WEEKLY = """case "$1 $2" in
  "run list") echo 11; echo 12; echo 13 ;;
  "api repos/o/r/actions/runs/12/artifacts") echo 0 ;;
  api*) echo 1 ;;
  "run download") [ -z "$STUB_DOWNLOAD_FAIL" ] || exit 1
                  mkdir -p "$9"; cp "$STUB_RECORDS/$3.json" "$9/skips.json" ;;
  *) echo "unexpected gh $*" >&2; exit 9 ;;
esac
"""

    def run_weekly(self, results: str, skipped: dict[str, list[str]], **env: str) -> subprocess.CompletedProcess:
        """The weekly guard step's script under bash, with a stand-in gh: runs 11 and 13 have a skip record (13's
        skipping `skipped["13"]`), run 12 has none."""
        with tempfile.TemporaryDirectory() as d:
            stub, recs = Path(d) / "bin", Path(d) / "recs"
            stub.mkdir()
            recs.mkdir()
            (stub / "gh").write_text("#!/bin/bash\n" + self.GH_WEEKLY)
            (stub / "gh").chmod(0o755)
            for run in ("11", "13"):
                rec = gate.skip_record({**{j: "skipped" for j in skipped.get(run, [])}, "q": "passed"}, int(run) + 100,
                                       int(run), BASE, HEAD)
                (recs / f"{run}.json").write_text(json.dumps(rec))
            (Path(d) / "check-results.tsv").write_text(results)
            full = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}", "GITHUB_REPOSITORY": "o/r",
                    "RUNNER_TEMP": d, "GH_TOKEN": "x", "STUB_RECORDS": str(recs), "STUB_DOWNLOAD_FAIL": "", **env}
            return subprocess.run(["bash", "-e", "-c", self.step_block("Did a pull request skip a job that fails here?")],
                                  cwd=ROOT, env=full, capture_output=True, text=True, timeout=60)

    def test_the_weekly_run_fails_on_a_job_a_pull_request_skipped(self) -> None:
        done = self.run_weekly("x\tfailed\ny\tpassed\n", {"13": ["x"]})
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn("::error::wrong skip? x: fails in this full run, and pull request #113 (run 13", done.stdout)
        self.assertIn("pull request runs since ", done.stdout)
        self.assertIn("that passed: 3; without a skip record: 1", done.stdout)

    def test_the_weekly_run_passes_when_no_skipped_job_fails(self) -> None:
        done = self.run_weekly("x\tfailed\ny\tpassed\n", {"13": ["y"]})
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertNotIn("::error::", done.stdout)
        self.assertIn("2 skip record(s) from pull request runs, 1 skipped job(s)", done.stdout)

    def test_the_weekly_run_fails_when_a_record_cannot_be_fetched(self) -> None:
        done = self.run_weekly("y\tpassed\n", {"13": ["y"]}, STUB_DOWNLOAD_FAIL="1")
        self.assertNotEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertNotIn("skip record(s)", done.stdout)

    def test_the_weekly_guard_runs_after_a_failed_check_sh_on_the_schedule_only(self) -> None:
        step = self.text[self.text.index("name: Did a pull request skip a job that fails here?"):]
        self.assertIn("if: ${{ !cancelled() && github.event_name == 'schedule'", step[:300])
        self.assertIn("(steps.checks.conclusion == 'success' || steps.checks.conclusion == 'failure') }}", step[:300])
        self.assertIn("id: checks", self.text[self.text.index("CHECK_RESULTS_TO") - 400:])
        self.assertLess(self.text.index("run: ./tools/check.sh"), self.text.index("name: Did a pull request skip"))
        self.assertIn("CHECK_RESULTS_TO: ${{ runner.temp }}/check-results.tsv", self.text)
        rec = self.text[self.text.index("name: Record the jobs this run skipped"):]
        self.assertIn("if: github.event_name == 'pull_request' && steps.kind.outputs.kind == 'full'", rec[:200])
        self.assertIn("name: check-skips", rec[:1200])

    def test_a_failed_label_or_message_lookup_runs_everything(self) -> None:
        done, out = self.run_gate("exit 1\n", "b" * 40)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("full: the pull request has the full-ci label", done.stdout)
        self.assertNotIn("skip_from=", out)


if __name__ == "__main__":
    unittest.main()
