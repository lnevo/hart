"""panel_stamps: the traced stamps that let `make panels` skip a step whose reads and outputs are what its last run
left, the sml-current guard, and the audit that the trace sees at least what an independent audit hook sees."""
from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import panel_stamps as ps  # noqa: E402

REPO = ps.ROOT
# (mode, name, cmd) of each step build_panels.sh runs, from the panels manifest (tools/pipeline/panels.toml)
LINES = [(s.mode, s.name, list(s.cmd)) for s in ps._load_manifest().panel_steps()]


class DeclarationTest(unittest.TestCase):
    def test_every_step_is_declared_and_only_steps(self) -> None:
        self.assertEqual([n for k, n, _ in LINES if k == "step"], list(ps.STEPS))

    def test_the_steps_run_in_the_order_the_pipeline_needs(self) -> None:
        order = [n for _, n, _ in LINES]
        for before, after in [("masts", "signals"), ("signals", "head-plan"), ("head-plan", "cats"),
                              ("schematic", "sml-current"), ("sml-current", "tables"), ("tables", "cats")]:
            self.assertLess(order.index(before), order.index(after), f"{before} before {after}")

    def test_every_output_pattern_names_a_file(self) -> None:
        for name, step in ps.STEPS.items():
            for pat in step.outputs:
                with self.subTest(step=name, output=pat):
                    self.assertTrue(ps.expand([pat]), f"{pat} matches nothing")

    def test_the_device_master_is_two_files(self) -> None:
        """The device-map and panel-items steps write devices_generated.csv (hartlib.devices.WRITERS: build_masts.py
        only reads it since naming-layers step 12); no step writes the owner's field file, so a hand edit there is an
        input (the trace sees every step that reads it). The names are pinned to hartlib.devices by
        test_devices_one_path."""
        generated, field = f"{ps.DATA}/{ps.DEVICES_FILE}", f"{ps.DATA}/{ps.DEVICES_FIELD_FILE}"
        self.assertEqual([n for n, s in ps.STEPS.items() if generated in s.outputs], ["device-map", "panel-items"])
        self.assertFalse([n for n, s in ps.STEPS.items() if field in s.outputs])

    def test_the_trace_hook_is_code_of_every_step(self) -> None:
        for f in ps.traced.HOOK_FILES:
            self.assertIn(f, ps.CODE)
            self.assertTrue((REPO / f).is_file(), f)

    def test_the_coordinator_and_its_modules_are_code_of_every_step(self) -> None:
        # le_names.lcos_rule imports sml_lcos.py, one of these files (hartlib.coordinator.lcos_rule)
        sys.path.insert(0, str(REPO / "tools/hartlib/src"))
        from hartlib import coordinator
        for path in coordinator.files():
            rel = path.relative_to(REPO).as_posix()
            self.assertTrue(any(ps._glob_match(rel, pat) for pat in ps.CODE), rel)

    def test_glob_matching_follows_path_glob(self) -> None:
        self.assertTrue(ps._glob_match("a/b/c.py", "a/**/*.py"))
        self.assertTrue(ps._glob_match("a/c.py", "a/**/*.py"))
        self.assertFalse(ps._glob_match("a/b/c.py", "a/*.py"))
        self.assertFalse(ps._glob_match("a/b/c.txt", "a/**/*.py"))


class StampTest(unittest.TestCase):
    """A fake repo holding the head-plan step's output; the step is a script run under the real trace hook."""

    STEP = ("import os\n"
            "open('jmri/layouts/hart/data/wiring.csv').read()\n"
            "os.path.exists('jmri/layouts/hart/data/later.csv')\n"
            "sorted(os.listdir('jmri/layouts/hart/data/schematic'))\n"
            "open('.cache/hart/x.json').read()\n")

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.store = self.tmp / "repo", self.tmp / "stamps"
        for rel, text in {"jmri/layouts/hart/data/wiring.csv": "w\n",
                          "jmri/layouts/hart/data/schematic/lcos_nodes.csv": "n\n",
                          "jmri/layouts/hart/data/switches.csv": "s\n",
                          "jmri/layouts/hart/output/signal_head_plan.csv": "p\n",
                          ".cache/hart/x.json": "c\n",
                          "tools/schematic/x.py": "code\n"}.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text)
        self.cmd = ["python3", "build.py"]
        for target in ("unstampable", "_main_checkout"):
            patch = unittest.mock.patch.object(ps, target, return_value=None)
            patch.start()
            self.addCleanup(patch.stop)

    def run_step(self, code: str | None = None, roots: int = 1) -> Path:
        log = self.tmp / "trace.log"
        log.write_text("0\tb\n" * roots)
        (self.root / "build.py").write_text(code or self.STEP)
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
        env.update(HART_TRACE_LOG=str(log), HART_TRACE_ROOT=str(self.root), PYTHONPATH=ps.traced.HOOK_DIR)
        subprocess.run([sys.executable, "build.py"], cwd=self.root, env=env, check=True, capture_output=True)
        return log

    def record(self, code: str | None = None, name: str = "head-plan", **kw) -> str | None:
        return ps.record(name, self.run_step(code, **kw), self.cmd, self.root, self.store)

    def current(self, name="head-plan", cmd=None) -> bool:
        return ps.is_current(name, self.cmd if cmd is None else cmd, self.root, self.store)

    def test_a_step_never_run_is_not_current(self) -> None:
        self.assertFalse(self.current())

    def test_hit_after_record(self) -> None:
        self.assertIsNone(self.record())
        self.assertTrue(self.current())

    def test_miss_when_a_file_it_read_changes_and_not_for_one_it_did_not(self) -> None:
        self.record()
        (self.root / "jmri/layouts/hart/data/switches.csv").write_text("s2\n")
        self.assertTrue(self.current(), "switches.csv is data the step never read")
        (self.root / "jmri/layouts/hart/data/wiring.csv").write_text("w2\n")
        self.assertFalse(self.current())

    def test_miss_when_a_listed_folder_gains_a_file(self) -> None:
        self.record()
        (self.root / "jmri/layouts/hart/data/schematic/new.csv").write_text("x\n")
        self.assertFalse(self.current())

    def test_miss_when_a_file_it_found_absent_appears(self) -> None:
        self.record()
        (self.root / "jmri/layouts/hart/data/later.csv").write_text("x\n")
        self.assertFalse(self.current())

    def test_cache_reads_are_no_input(self) -> None:
        self.record()
        (self.root / ".cache/hart/x.json").write_text("c2\n")
        self.assertTrue(self.current())

    def test_miss_when_an_output_is_edited_or_removed(self) -> None:
        out = self.root / "jmri/layouts/hart/output/signal_head_plan.csv"
        self.record()
        out.write_text("hand edit\n")
        self.assertFalse(self.current())
        self.record()
        out.unlink()
        self.assertFalse(self.current())

    def test_miss_when_the_code_or_the_command_changes(self) -> None:
        self.record()
        self.assertFalse(self.current(cmd=["python3", "other.py"]))
        (self.root / "tools/schematic/x.py").write_text("code2\n")
        self.assertFalse(self.current())

    def test_no_trace_or_a_short_one_records_nothing(self) -> None:
        self.record()
        log = self.tmp / "empty.log"
        log.write_text("0\tb\n")
        self.assertIn("did not load", ps.record("head-plan", log, self.cmd, self.root, self.store))
        self.assertFalse(self.current(), "the old stamp is dropped")
        self.assertIn("1 of the 2", self.record(roots=2))
        self.assertFalse(self.current())

    def test_an_untraceable_subprocess_is_never_stamped_unless_declared(self) -> None:
        code = self.STEP + "import subprocess\nsubprocess.run(['sh', '-c', 'cat jmri/layouts/hart/data/switches.csv'])\n"
        self.assertIn("ran sh", self.record(code))
        self.assertFalse(self.current())
        with unittest.mock.patch.dict(ps.STEPS, {"head-plan": ps.Step(ps.STEPS["head-plan"].outputs,
                                                                      programs={"sh": ("jmri/layouts/hart/data/switches.csv",)})}):
            self.assertIsNone(self.record(code))
            self.assertTrue(self.current())
            (self.root / "jmri/layouts/hart/data/switches.csv").write_text("s2\n")
            self.assertFalse(self.current(), "the declared program's files are hashed")

    def test_every_step_that_runs_untraced_programs_declares_them(self) -> None:
        self.assertEqual({n: list(s.programs) for n, s in ps.STEPS.items() if s.programs}, {"schematic": ["chrom"]})

    def test_a_trial_plugin_folder_and_the_required_flag_are_in_the_stamp(self) -> None:
        self.record()
        plugin = self.tmp / "plugin"
        plugin.mkdir()
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.invalid"}
        for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x"]):
            subprocess.run(["git", *args], cwd=plugin, check=True, env=env)
        with unittest.mock.patch.dict(os.environ, {"SCHEMATIC_PLUGIN": str(plugin)}):
            self.assertFalse(self.current(), "a trial folder is another plugin")
            self.record()
            self.assertTrue(self.current())
            (plugin / "edit.py").write_text("x\n")
            subprocess.run(["git", "add", "edit.py"], cwd=plugin, check=True, env=env)
            self.assertFalse(self.current(), "an uncommitted change in the trial folder")
        with unittest.mock.patch.dict(os.environ, {"SCHEMATIC_REQUIRED": "1"}):
            self.assertFalse(self.current())

    def test_git_or_plugin_state_that_changed_while_the_step_ran_records_nothing(self) -> None:
        before = ps.snapshot(self.root)
        self.assertIsNone(ps.record("head-plan", self.run_step(), self.cmd, self.root, self.store, before=before))
        reason = ps.record("head-plan", self.run_step(), self.cmd, self.root, self.store, before="other " + before)
        self.assertIn("changed while the step ran", reason)
        self.assertFalse(self.current())

    def test_forget_drops_the_stamp(self) -> None:
        self.record()
        ps.forget("head-plan", self.store)
        self.assertFalse(self.current())


class UnstampableTest(unittest.TestCase):
    def test_hart_tables_means_no_stamps(self) -> None:
        with unittest.mock.patch.dict(os.environ, {"HART_TABLES": "/x/tables.xml"}):
            self.assertIn("HART_TABLES", ps.unstampable())
            tmp = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, tmp)
            self.assertIn("HART_TABLES", ps.record("hands", tmp / "no.log", (), REPO, tmp))
            self.assertEqual(list(tmp.iterdir()), [])
            self.assertFalse(ps.is_current("hands", (), REPO, tmp))

    def test_a_missing_plugin_means_no_stamps(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        with unittest.mock.patch.dict(os.environ, {"SCHEMATIC_PLUGIN": ""}):
            self.assertIn("not checked out", ps.unstampable(tmp))


class BrokenManifestTest(unittest.TestCase):
    """STEPS is read on first use: a broken panels.toml is a message and exit 2 from the commands that need it, and
    forget (after a failed step) still drops the stamp."""

    def test_forget_works_and_the_others_name_the_problem(self) -> None:
        broken = unittest.mock.patch.object(ps, "steps", side_effect=ps.StepsError("panels.toml: step 'x': broken"))
        err = io.StringIO()
        with broken, unittest.mock.patch.object(ps, "forget") as forget, contextlib.redirect_stderr(err):
            self.assertEqual(ps.main(["forget", "hands"]), 0)
            forget.assert_called_once_with("hands")
            self.assertEqual(ps.main(["current", "hands"]), 2)
            self.assertEqual(ps.main(["forget", "../x"]), 2)
        self.assertIn("panel_stamps.py: panels.toml: step 'x': broken", err.getvalue())

    def test_importing_reads_no_manifest(self) -> None:
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'tools/schematic'); "
                            "import panel_stamps as ps; print(ps._STEPS is None, 'pipeline_manifest' in sys.modules)"],
                           cwd=REPO, capture_output=True, text=True, check=True)
        self.assertEqual(r.stdout.split(), ["True", "False"])


class ShellTest(unittest.TestCase):
    """build_panels.sh in a scratch repo whose scripts are stubs that log their runs."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "repo"
        self.log = self.tmp / "log"
        for _kind, _name, cmd in LINES:
            script = self.root / cmd[1]
            script.parent.mkdir(parents=True, exist_ok=True)
            # each stub reads a file of its own (head-plan: wiring.csv), so an edit there reaches only that step
            own = "jmri/layouts/hart/data/wiring.csv" if _name == "head-plan" else f"jmri/layouts/hart/data/{_name}.in"
            script.write_text("import os, sys\n"
                              f"open({own!r}).read()\n"
                              f"open({str(self.log)!r}, 'a').write({cmd[1]!r} + ' ' + ' '.join(sys.argv[1:]) + '\\n')\n")
        (self.root / "tools/schematic").mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / "tools/schematic/build_panels.sh", self.root / "tools/schematic/build_panels.sh")
        shutil.copy(REPO / "tools/schematic/panel_stamps.py", self.root / "tools/schematic/panel_stamps.py")
        (self.root / "tools/pipeline").mkdir(parents=True, exist_ok=True)
        for f in (*ps._load_manifest().FILES, "tools/pipeline/panels.toml"):     # the step list: loader and parts
            shutil.copy(REPO / f, self.root / f)
        for f in ps.traced.HOOK_FILES:
            (self.root / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / f, self.root / f)
        wiring = self.root / "jmri/layouts/hart/data/wiring.csv"
        wiring.parent.mkdir(parents=True, exist_ok=True)
        wiring.write_text("w\n")
        for _kind, name, _cmd in LINES:
            (self.root / f"jmri/layouts/hart/data/{name}.in").write_text("v1\n")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.invalid"}
        self.env = {k: v for k, v in env.items() if k not in ("HART_TABLES", "SCHEMATIC_PLUGIN")}
        plugin = self.root / "external/model-railroad-skills"
        plugin.mkdir(parents=True)
        (plugin / "a.py").write_text("x\n")

        def git(cwd, *args):
            return subprocess.run(["git", *args], cwd=cwd, check=True, env=self.env, capture_output=True,
                                  text=True).stdout.strip()
        git(plugin, "init", "-q")
        git(plugin, "add", "a.py")
        git(plugin, "commit", "-q", "-m", "p")
        git(self.root, "init", "-q")
        # the plugin stands as a submodule at its pinned commit: a gitlink in the scratch repo's HEAD
        git(self.root, "update-index", "--add", "--cacheinfo", f"160000,{git(plugin, 'rev-parse', 'HEAD')},"
            "external/model-railroad-skills")
        git(self.root, "commit", "-q", "-m", "pin")

    def run_panels(self, *args: str) -> tuple[str, list[str]]:
        self.log.touch()
        before = self.log.read_text().splitlines()
        r = subprocess.run(["bash", "tools/schematic/build_panels.sh", *args], cwd=self.root, capture_output=True,
                           text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout, self.log.read_text().splitlines()[len(before):]

    def ran(self, lines: list[str]) -> set[str]:
        return {Path(l.split()[0]).stem for l in lines}

    def test_second_run_skips_every_step_but_runs_the_guards(self) -> None:
        out, first = self.run_panels()
        self.assertEqual(len(first), len(LINES))
        out, second = self.run_panels()
        steps = [n for k, n, _ in LINES if k == "step"]
        guards = [c[1] for k, _, c in LINES if k == "guard"]
        self.assertEqual(len(second), len(guards))
        for name in steps:
            self.assertIn(f"{name}: current, skipped", out)

    def test_an_input_change_reruns_its_step_and_not_the_others(self) -> None:
        self.run_panels()
        (self.root / "jmri/layouts/hart/data/wiring.csv").write_text("w2\n")
        out, again = self.run_panels()
        self.assertIn("head-plan: ok", out)
        self.assertIn("hands: current, skipped", out)
        self.assertTrue(any("build_hart_signal_heads" in l for l in again))
        self.assertFalse(any("build_hands" in l for l in again))

    def test_an_edit_reruns_only_the_step_that_read_it(self) -> None:
        self.run_panels()
        (self.root / "jmri/layouts/hart/data/masts.in").write_text("v2\n")
        out, again = self.run_panels()
        steps = [n for k, n, _ in LINES if k == "step"]
        self.assertEqual([n for n in steps if f"{n}: current, skipped" not in out], ["masts"], out)

    def test_a_step_with_an_untraceable_subprocess_always_runs(self) -> None:
        hands = self.root / "tools/schematic/build_hands.py"
        hands.write_text(hands.read_text() + "import subprocess\nsubprocess.run(['sh', '-c', 'true'])\n")
        out, _ = self.run_panels()
        self.assertIn("hands: not stamped: ran sh", out)
        out, second = self.run_panels()
        self.assertNotIn("hands: current", out)
        self.assertTrue(any("build_hands" in l for l in second))

    def test_full_ignores_the_stamps(self) -> None:
        self.run_panels()
        out, again = self.run_panels("--full")
        self.assertEqual(len(again), len(LINES))
        self.assertNotIn("skipped", out)

    def test_check_mode_may_skip_a_step_whose_stamp_matches(self) -> None:
        self.run_panels()
        out, again = self.run_panels("--check")
        self.assertIn("hands: current, skipped", out)
        self.assertTrue(all("--check" in l for l in again))

    def test_a_step_that_printed_skipped_is_never_stamped(self) -> None:
        (self.root / "tools/schematic/build_hands.py").write_text(
            "import sys\nprint('SKIPPED hands check: no plugin')\n"
            f"open({str(self.log)!r}, 'a').write('tools/schematic/build_hands.py\\n')\n")
        out, first = self.run_panels()
        self.assertIn("hands: printed SKIPPED, no stamp", out)
        out, second = self.run_panels()
        self.assertNotIn("hands: current", out)
        self.assertTrue(any("build_hands" in l for l in second))
        self.assertIn("staging-sets: current, skipped", out)

    def test_hart_tables_turns_the_stamps_off_and_says_so_once(self) -> None:
        self.run_panels()
        self.env["HART_TABLES"] = str(self.root / "tables.xml")
        out, again = self.run_panels()
        self.assertEqual(out.count("stamps off for this run"), 1, out)
        self.assertNotIn("skipped", out)
        self.assertEqual(len(again), len(LINES))

    def test_a_plugin_off_its_pin_turns_the_stamps_off(self) -> None:
        (self.root / "external/model-railroad-skills/a.py").write_text("y\n")
        subprocess.run(["git", "add", "a.py"], cwd=self.root / "external/model-railroad-skills", check=True,
                       env=self.env)
        subprocess.run(["git", "commit", "-q", "-m", "moved"], cwd=self.root / "external/model-railroad-skills",
                       check=True, env=self.env)
        out, _ = self.run_panels()
        self.assertIn("stamps off for this run: the schematic-maps plugin is at", out)
        self.assertFalse((self.root / ".cache/panel-stamps").exists())

    def test_a_failed_step_forgets_its_stamp(self) -> None:
        self.run_panels()
        hands = self.root / "tools/schematic/build_hands.py"
        hands.write_text("raise SystemExit(1)\n")
        r = subprocess.run(["bash", "tools/schematic/build_panels.sh"], cwd=self.root, capture_output=True, text=True,
                           env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("hands: FAILED", r.stdout)
        self.assertFalse((self.root / ".cache/panel-stamps/hands.sha256").exists())


class AuditTest(unittest.TestCase):
    """Each step run once under two hooks: tools/schematic/audit_reads.py (in the process) and the trace hook. Every
    repo file the audit sees read or found absent and every folder it sees listed must be in the trace's read set, so
    the stamp misses nothing the step's own process touches; the trace also covers its Python children."""

    def test_the_trace_holds_every_read_the_audit_sees(self) -> None:
        try:
            import build_layout_le as ble
            ble.plugin()
        except Exception as exc:  # noqa: BLE001 - no plugin checked out: nothing to audit
            self.skipTest(f"schematic-maps plugin: {exc}")
        skip = ps.traced._skip_prefixes(str(REPO))

        def kept(paths):
            return {k for k in (ps.traced.keep(str(REPO / p), str(REPO), skip) for p in paths) if k is not None}
        for _kind, name, cmd in [l for l in LINES if l[0] == "step"]:
            with self.subTest(step=name), tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "trace.log"
                log.write_text("0\tb\n")
                env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
                env.update(PYTHONPYCACHEPREFIX=str(Path(tmp) / "pyc"), HART_TRACE_LOG=str(log),
                           HART_TRACE_ROOT=str(REPO), PYTHONPATH=ps.traced.HOOK_DIR)  # imports read their source
                r = subprocess.run([sys.executable, str(REPO / "tools/schematic/audit_reads.py"), *cmd[1:], "--check"],
                                   cwd=REPO, capture_output=True, text=True, env=env)
                self.assertEqual(r.returncode, 0, r.stderr[-600:])
                lines = r.stdout.splitlines()
                audit = {kind: kept(l[2:] for l in lines if l.startswith(kind + " ")) for kind in "RMD"}
                self.assertTrue(audit["R"], f"{name}: the audit hook saw no reads")
                t = ps.traced.parse(log)
                self.assertIsNone(ps.traced.problem(t))
                rs = ps.traced.read_set(t, str(REPO))
                files, missing, dirs = set(rs["files"]), set(rs["missing"]), set(rs["dirs"])
                self.assertEqual(sorted(audit["R"] - files), [], f"{name}: read and not in the trace")
                self.assertEqual(sorted(audit["M"] - missing - files), [], f"{name}: probed absent, not in the trace")
                self.assertEqual(sorted(audit["D"] - dirs), [], f"{name}: listed and not in the trace")


class SmlCurrentTest(unittest.TestCase):
    def setUp(self) -> None:
        import check_sml_current as cs
        self.cs = cs
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.stamp = self.tmp / "discovered_sml.stamp"

    def test_match(self) -> None:
        self.stamp.write_text("abc123\n")
        self.assertIsNone(self.cs.verdict(self.stamp, "abc123"))

    def test_mismatch_says_what_to_run(self) -> None:
        self.stamp.write_text("abc123\n")
        msg = self.cs.verdict(self.stamp, "def456")
        self.assertEqual(msg, "SML discovery is stale: make panels on the Mac discovers itself; elsewhere run "
                              "jmri/layouts/hart/scripts/run_sml_discover.sh on the Mac (PanelPro), then make panels")

    def test_missing_stamp_is_stale(self) -> None:
        self.assertIn("SML discovery is stale", self.cs.verdict(self.stamp, "abc"))

    def base(self) -> bytes:
        import build_layout_le as ble
        try:
            ble.plugin()
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"schematic-maps plugin: {exc}")
        import build_tables as bt
        import publish_draft as pd
        with pd.cache_on():
            return bt.generate(with_logic=False)[0]

    def test_a_comment_or_a_sensor_name_change_keeps_the_digest(self) -> None:
        import build_tables as bt
        data = self.base()
        text = data.decode("utf-8")
        self.assertIn("<comment>Node: 1 Block: 1</comment>", text)
        same = text.replace("<comment>Node: 1 Block: 1</comment>", "<comment>edited note</comment>")
        self.assertEqual(bt.discovery_digest(data), bt.discovery_digest(same.encode("utf-8")))
        renamed = text.replace("<userName>BS K-1</userName>", "<userName>BS K-1x</userName>", 1)
        self.assertNotEqual(renamed, text)
        self.assertEqual(bt.discovery_digest(data), bt.discovery_digest(renamed.encode("utf-8")))

    def test_a_mast_or_a_track_change_trips_the_digest(self) -> None:
        import build_tables as bt
        text = self.base().decode("utf-8")
        mast = text.replace("<userName>Mast 4RA</userName>", "<userName>Mast 4RAx</userName>", 1)
        self.assertNotEqual(mast, text)
        self.assertNotEqual(bt.discovery_digest(text.encode()), bt.discovery_digest(mast.encode()))
        track = re.sub(r"(<tracksegment [^>]*?)ident=\"([^\"]+)\"", r'\1ident="\2x"', text, count=1)
        self.assertNotEqual(track, text)
        self.assertNotEqual(bt.discovery_digest(text.encode()), bt.discovery_digest(track.encode()))
        turnout = text.replace("<turnout ", "<turnout feedbackkind=\"1\" ", 1)
        self.assertNotEqual(bt.discovery_digest(text.encode()), bt.discovery_digest(turnout.encode()))

    def test_the_committed_stamp_matches_the_sources(self) -> None:
        try:
            import build_layout_le as ble
            ble.plugin()
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"schematic-maps plugin: {exc}")
        self.assertIsNone(self.cs.verdict(self.cs.STAMP, self.cs.base_digest()))


if __name__ == "__main__":
    unittest.main()
