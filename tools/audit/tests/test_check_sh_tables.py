"""tools/check.sh with HART_TABLES: table checks read the named file, unit tests never see it."""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
CHECK = ROOT / "tools/check.sh"


def imported_modules(source: str) -> set[str]:
    """Top-level names of the modules a source file imports, in any form (import a, import a as b, import a.b,
    from a import b, from a.b import c, from . import a) and at any depth (inside a function or a try as well)."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.ImportFrom):          # from . import a
            found |= {alias.name for alias in node.names}
    return found


class CheckShTables(unittest.TestCase):
    def test_every_unittest_step_runs_without_hart_tables(self) -> None:
        text = CHECK.read_text(encoding="utf-8")
        steps = [line.strip() for line in text.splitlines() if "-m unittest" in line]
        self.assertTrue(steps)
        for line in steps:
            self.assertTrue(line.startswith("unit "), line)
        self.assertIn('env -u HART_TABLES "$@"', text)

    def test_the_layout_editor_files_run_as_one_job(self) -> None:
        """One process, so test_build_layout_le.built() (cached per process) builds the candidate once: every test
        file that imports that module, directly or through another test file, is in LE_TESTS, and the per-file loop
        leaves those files out."""
        text = CHECK.read_text(encoding="utf-8")
        line = next(x for x in text.splitlines() if x.startswith("LE_TESTS="))
        names = line.split('"')[1].split()
        imports = {p.stem: imported_modules(p.read_text(encoding="utf-8"))
                   for p in (ROOT / "tools/audit/tests").glob("test*.py")}
        users = {"test_build_layout_le"}
        while True:
            more = {stem for stem, mods in imports.items() if mods & users} - users
            if not more:
                break
            users |= more
        self.assertEqual(sorted(users), sorted(names))
        # that check.sh runs them in one process and leaves them out of the per-file jobs: ScratchCheckSh below

    def test_every_import_form_is_seen(self) -> None:
        for source in ("import test_build_layout_le", "import test_build_layout_le as T  # noqa",
                       "import os, test_build_layout_le", "from . import test_build_layout_le",
                       "from test_build_layout_le import built", "from test_build_layout_le import built as b, B",
                       "def f():\n    from test_build_layout_le import built\n",
                       "try:\n    import test_build_layout_le\nexcept ImportError:\n    pass\n"):
            self.assertIn("test_build_layout_le", imported_modules(source), source)
        for source in ("import test_build_layout_lex", "# import test_build_layout_le",
                       "x = 'import test_build_layout_le'"):
            self.assertNotIn("test_build_layout_le", imported_modules(source), source)

    def cache_block(self, home: Path, **env: str) -> subprocess.CompletedProcess:
        """Run check.sh's SCHEMATIC_CACHE block (cache folder HART_CACHE_DIR=home/.cache/hart unless given), then
        print the variable as the jobs see it."""
        text = CHECK.read_text(encoding="utf-8")
        start = text.index("# The schematic plugin's cache")
        block = text[start:text.index("\nfi\n", text.index('if [[ -z "${SCHEMATIC_CACHE+set}" ]]', start)) + 4]
        base = {k: v for k, v in os.environ.items() if k != "SCHEMATIC_CACHE"}
        return subprocess.run(["bash", "-c", f'ROOT="{ROOT}"\n' + block + 'echo "CACHE=${SCHEMATIC_CACHE-unset}"'],
                              env={**base, "HOME": str(home), "HART_CACHE_DIR": str(home / ".cache/hart"), **env},
                              capture_output=True, text=True, timeout=30)

    def test_ci_keys_the_schematic_cache_on_the_plugin_pin_and_warms_it_first(self) -> None:
        """A run restores a cache solved with its own plugin pin before main's latest, and a run whose exact key missed
        (another pin, or changed builders or data) solves the sheet once (build_panels.sh --check) before check.sh's
        parallel jobs start: since ADR-037 stage 6 every panels step is one of them."""
        text = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")
        self.assertIn("key: schematic-${{ steps.pin.outputs.pin }}-", text)
        self.assertIn("            schematic-${{ steps.pin.outputs.pin }}-\n            schematic-\n", text)
        warm = text.index("name: Warm the schematic cache when its exact key missed")
        self.assertIn("bash tools/schematic/build_panels.sh --check --full", text[warm:])
        # only on the full path and when the exact cache missed: no time added to a run whose key hit, nor to a
        # docs-only or light run
        self.assertIn("if: steps.kind.outputs.kind == 'full' && steps.schematic-cache.outputs.cache-hit != 'true'\n",
                      text[warm:])
        self.assertLess(warm, text.index("run: ./tools/check.sh"))

    def test_check_sh_turns_on_the_builds_schematic_cache(self) -> None:
        """The folder the builds use (publish_draft.CACHE, loaded under the same HART_CACHE_DIR), made private."""
        self.assertIn("path: .cache/hart/schematic", (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            spec = importlib.util.spec_from_file_location("check_sh_tables_publish_draft",
                                                          ROOT / "tools/schematic/publish_draft.py")
            draft = importlib.util.module_from_spec(spec)
            with mock.patch.dict(os.environ, {"HART_CACHE_DIR": str(home / ".cache/hart")}), \
                    mock.patch.dict(sys.modules, {spec.name: draft}):
                spec.loader.exec_module(draft)
            done = self.cache_block(home)
            self.assertEqual(home / ".cache/hart/schematic", draft.CACHE)
            self.assertIn(f"CACHE={draft.CACHE}\n", done.stdout)
            self.assertEqual(0o700, draft.CACHE.stat().st_mode & 0o777)

    def test_an_empty_or_set_schematic_cache_is_the_callers(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("CACHE=\n", self.cache_block(Path(d), SCHEMATIC_CACHE="").stdout)
            self.assertIn("CACHE=/elsewhere\n", self.cache_block(Path(d), SCHEMATIC_CACHE="/elsewhere").stdout)
            self.assertFalse((Path(d) / ".cache").exists())

    def test_a_cache_folder_that_cannot_be_made_leaves_it_off(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".cache").write_text("a file, not a folder")
            done = self.cache_block(Path(d))
            self.assertIn("CACHE=unset", done.stdout)
            self.assertIn("schematic cache off", done.stdout)

    def test_a_missing_hart_tables_file_stops_check_sh_at_once(self) -> None:
        env = {**os.environ, "HART_TABLES": "/nowhere/tables.xml"}
        done = subprocess.run(["bash", str(CHECK)], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(1, done.returncode)
        self.assertIn("HART_TABLES=/nowhere/tables.xml: no such file", done.stdout)

    def resolve(self, value: str, cwd: Path, home: Path) -> subprocess.CompletedProcess:
        """Run check.sh's HART_TABLES block (the lines before ROOT=) from `cwd`, then print the result."""
        text = CHECK.read_text(encoding="utf-8")
        block = text[text.index("if [[ -n \"${HART_TABLES:-}\" ]]"):text.index('ROOT="$(cd')]
        env = {**os.environ, "HART_TABLES": value, "HOME": str(home)}
        return subprocess.run(["bash", "-c", block + 'echo "RESOLVED=$HART_TABLES"'], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=30)

    def test_a_relative_or_tilde_hart_tables_is_the_callers(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d).resolve()
            (d / "sub").mkdir()
            (d / "sub" / "cand.xml").write_text("<layout-config/>")
            done = self.resolve("sub/cand.xml", d, d)
            self.assertIn(f"RESOLVED={d}/sub/cand.xml", done.stdout, done.stderr)
            done = self.resolve("~/sub/cand.xml", ROOT, d)
            self.assertIn(f"RESOLVED={d}/sub/cand.xml", done.stdout, done.stderr)
            self.assertIn("no such file", self.resolve("nope.xml", d, d).stdout)


class StaticPanelChecks(unittest.TestCase):
    """The panels checks are the steps of tools/pipeline/panels.toml, one list for check.sh (one job each, stage 6)
    and make panels; check.sh's run_check puts a bash check into its job's trace as a program the hook cannot see."""

    @staticmethod
    def static_steps() -> list:
        """The read-only checks: the steps of the static group in tools/pipeline/checks.toml (check.sh runs each as a
        job of its own)."""
        spec = importlib.util.spec_from_file_location("check_sh_tables_manifest", ROOT / "tools/pipeline/manifest.py")
        manifest = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {spec.name: manifest}):      # its dataclasses look their module up there
            spec.loader.exec_module(manifest)
            return list(manifest.select(manifest.load(), "check", group="static"))

    @staticmethod
    def panel_scripts() -> list[str]:
        """The scripts make panels runs: the steps of tools/pipeline/panels.toml (build_panels.sh runs them)."""
        spec = importlib.util.spec_from_file_location("check_sh_tables_manifest", ROOT / "tools/pipeline/manifest.py")
        manifest = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {spec.name: manifest}):
            spec.loader.exec_module(manifest)
            return [s.script for s in manifest.panel_steps()]

    @staticmethod
    def static_body() -> str:
        text = CHECK.read_text(encoding="utf-8")
        return text[text.index("\nrun_line() {\n"):text.index("\n# The longest jobs start first")]

    def test_static_checks_the_panel_outputs_once_one_job_per_step(self) -> None:
        steps = self.static_steps()
        self.assertIn(("panels", ("bash", "tools/schematic/build_panels.sh", "--check")),
                      [(s.name, s.cmd) for s in steps])
        panel = self.panel_scripts()
        self.assertGreaterEqual(len(panel), 16, "tools/pipeline/panels.toml's steps were not found")
        scripts = {s.script for s in steps}
        self.assertEqual([], sorted(set(panel) & scripts), "a panel step checked twice: its panels job runs it")
        done = subprocess.run([sys.executable, str(ROOT / "tools/pipeline/manifest.py"), "jobs", "check", "--group",
                               "static"], capture_output=True, text=True, timeout=60, check=True)
        jobs = [line for line in done.stdout.splitlines() if line.startswith("panels")]
        self.assertEqual(len(jobs), len(panel), "one panels-<step> job per step of tools/pipeline/panels.toml")
        self.assertTrue(all(line.startswith("panels-") for line in jobs), jobs)
        self.assertIn("panels-tables python3 tools/schematic/build_tables.py --check", jobs)

    @staticmethod
    def caller_block() -> str:
        """check.sh's lines that keep the caller's PYTHONPATH."""
        text = CHECK.read_text(encoding="utf-8")
        start = text.index("CALLER_PYTHONPATH=()\n")
        return text[start:text.index("\n", text.index('if [[ -n "${PYTHONPATH+set}" ]]', start)) + 1]

    def run_function(self, log: Path, *calls: str, **extra_env: str) -> subprocess.CompletedProcess:
        """check.sh's run_check as a check's job has it, with `log` as the job's trace, then `calls` (`run NAME CMD`
        is run_check, with static_rc=1 when one fails); prints static_rc."""
        text = CHECK.read_text(encoding="utf-8")
        start = text.index("\nrun_check() {\n") + 1
        body = text[start:text.index("\n}\n", start) + 3]
        shim = 'run() { run_check "$@" || static_rc=1; }\n'
        script = (f'ROOT="{ROOT}"\n{self.caller_block()}static_rc=0\n{body}{shim}' + "\n".join(calls)
                  + '\necho "static_rc=$static_rc"\n')
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
        env.update(HART_TRACE_LOG=str(log), **extra_env)
        return subprocess.run(["bash", "-c", script], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)

    def test_a_bash_check_is_an_untraced_program_and_a_python_one_an_expected_process(self) -> None:
        sys.path.insert(0, str(ROOT / "tools/audit"))
        import traced
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "trace.log"
            done = self.run_function(log, "run sh-check bash -c true", "run py-check python3 -c pass")
            self.assertIn("static_rc=0", done.stdout, done.stderr)
            t = traced.parse(log)
            self.assertEqual(1, t.expected_roots)
            self.assertEqual(1, len(t.runner_ns), "the bash check says when it started")
            programs, gits = traced.untraced(t, str(ROOT))
            self.assertEqual((["bash"], []), (programs, gits))

    def test_a_failing_bash_check_fails_the_job(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            done = self.run_function(Path(d) / "trace.log", "run bad bash -c 'exit 3'")
            self.assertIn("static_rc=1", done.stdout)

    def test_another_program_is_refused_and_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "ran"
            done = self.run_function(Path(d) / "trace.log", f"run other sh -c 'touch {marker}'")
            self.assertIn("static_rc=1", done.stdout)
            self.assertIn("other: check.sh's run_check takes python3, env VAR=... python3 or bash, not sh; not run", done.stdout)
            self.assertFalse(marker.exists())
            self.assertFalse((Path(d) / "trace.log").exists(), "a refused check wrote to the trace")


    def test_bash_runs_with_the_callers_pythonpath_and_outside_the_jobs_trace(self) -> None:
        """A bash check runs outside the job's hooks (when build_panels.sh was one, its stamps keyed on PYTHONPATH)."""
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "trace.log"
            # the job puts its hook on PYTHONPATH after check.sh read the caller's
            done = self.run_function(log, 'PYTHONPATH="/hook:$PYTHONPATH"; export HART_TRACE_SPAWN=t CHECK_AUDIT_LOG=a',
                                     "run see bash -c 'echo \"PP=${PYTHONPATH-unset} LOG=${HART_TRACE_LOG-unset} "
                                     "SPAWN=${HART_TRACE_SPAWN-unset} AUDIT=${CHECK_AUDIT_LOG-unset}\"'",
                                     PYTHONPATH="/caller")
            self.assertIn("PP=/caller LOG=unset SPAWN=unset AUDIT=unset", done.stdout, done.stderr)
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            done = subprocess.run(["bash", "-c", self.caller_block() + 'echo "${CALLER_PYTHONPATH[*]}"'], env=env,
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual("-u PYTHONPATH\n", done.stdout, "a caller with no PYTHONPATH: unset, not empty")

    def test_env_is_taken_only_for_a_python_check(self) -> None:
        sys.path.insert(0, str(ROOT / "tools/audit"))
        import traced
        with tempfile.TemporaryDirectory() as d:
            log, marker = Path(d) / "trace.log", Path(d) / "ran"
            done = self.run_function(log, "run py env FOO=1 python3 -c pass",
                                     f"run sh env FOO=1 sh -c 'touch {marker}'")
            self.assertIn("sh: check.sh's run_check takes python3, env VAR=... python3 or bash, not env sh; not run",
                          done.stdout)
            self.assertIn("static_rc=1", done.stdout)
            self.assertFalse(marker.exists())
            self.assertEqual(1, traced.parse(log).expected_roots)


# A stand-in test file: logs its name and process; test_build_layout_le also logs its one import ("built": the real
# module's built() caches per process), and the other Layout Editor files import it.
STUB_TEST = """import os
import unittest
{imp}

def log(what):
    with open(os.environ["STUB_LE_LOG"], "a") as f:
        f.write(f"{{what}} {{os.getpid()}}\\n")

{built}

class T(unittest.TestCase):
    def test_runs(self):
        log("{name}")
"""


class ScratchCheckSh(unittest.TestCase):
    """check.sh itself in a scratch repo (test_pipeline_manifest.scratch_check_sh: a stand-in manifest, and a panels
    script that prints what it was run with), for what its queueing does: the Layout Editor job, the panels jobs."""

    @classmethod
    def setUpClass(cls) -> None:
        from test_pipeline_manifest import scratch_check_sh   # noqa: PLC0415 - its folder is on sys.path under discover
        cls.tmp = tempfile.TemporaryDirectory()
        cls.s = scratch_check_sh(Path(cls.tmp.name))
        for name in ("test_build_layout_le", "test_le_cutover", "test_le_mast_parity", "test_other"):
            cls.s.write(f"tools/audit/tests/{name}.py", STUB_TEST.format(
                name=name, imp="import test_build_layout_le" if name.startswith("test_le_") else "",
                built='log("built")' if name == "test_build_layout_le" else ""))
        cls.s.commit("test stand-ins")
        subprocess.run(["git", "-C", str(cls.s.repo), "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_check(self, **env: str) -> subprocess.CompletedProcess:
        from test_pipeline_manifest import OWN, STATIC   # noqa: PLC0415
        return self.s.check_sh(**{"STUB_PIN": "", "STUB_STATIC": STATIC, "STUB_OWN": OWN, **env})

    def test_the_layout_editor_files_run_in_one_process_and_in_no_job_of_their_own(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "le.log"
            done = self.run_check(FULL="1", CHECK_ONLY="^unit-guards", STUB_LE_LOG=str(log))
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
            jobs = sorted(re.sub(r" \([0-9.]+s\)$", "", line) for line in done.stdout.splitlines()
                          if line.startswith("--- "))
            self.assertEqual(["--- unit-guards layout-editor (test_build_layout_le test_le_cutover test_le_mast_parity)",
                              "--- unit-guards test_other"], jobs)
            lines = [line.split() for line in log.read_text().splitlines()]
            self.assertEqual(["built", "test_build_layout_le", "test_le_cutover", "test_le_mast_parity", "test_other"],
                             sorted(what for what, _ in lines))
            pid = dict(lines)
            self.assertEqual({pid["built"]}, {pid[n] for n in ("test_build_layout_le", "test_le_cutover",
                                                                "test_le_mast_parity")}, "one process, one build")
            self.assertNotEqual(pid["built"], pid["test_other"])

    def test_the_panels_jobs_are_queued_first_and_take_their_line_as_it_is(self) -> None:
        """Stage 6: one job per panels step, queued ahead of the Layout Editor job; no --full in any run."""
        for env in ({"FULL": "1"}, {"CI": "true"}, {}):
            with self.subTest(env=env):
                with tempfile.TemporaryDirectory() as d:
                    done = self.run_check(CHECK_ONLY="^(panels-tables|one|unit-guards layout-editor.*)$",
                                          STUB_LE_LOG=str(Path(d) / "le.log"), **env)
                self.assertEqual(0, done.returncode, done.stdout + done.stderr)
                heads = [line.split(" (")[0] for line in done.stdout.splitlines() if line.startswith("--- ")]
                self.assertEqual(heads[0], "--- panels-tables", heads)
                self.assertEqual(1, done.stdout.count("ran panels-tables"), "the panels job queued once")
                self.assertNotIn("--full", done.stdout)


class LayoutIndexSource(unittest.TestCase):
    def test_the_index_names_the_checkout_file_when_hart_tables_points_elsewhere(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "tables.xml"
            copy.write_bytes((ROOT / "jmri/layouts/hart/output/tables.xml").read_bytes())
            env = {**os.environ, "HART_TABLES": str(copy)}
            done = subprocess.run([sys.executable, str(ROOT / "www/scripts/build_layout_index.py"), "--check"],
                                  env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertRegex(done.stdout, re.compile(r"layout-index\.json builds and passes its checks"))


if __name__ == "__main__":
    unittest.main()
