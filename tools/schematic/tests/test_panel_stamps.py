"""panel_stamps: the stamps that let `make panels` skip a step whose inputs and outputs are what its last run left,
the sml-current guard, and the audit that pins every step's declared inputs."""
from __future__ import annotations

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
SCRIPT = (REPO / "tools/schematic/build_panels.sh").read_text(encoding="utf-8")
# `step NAME CMD...` and `guard NAME CMD...` lines of build_panels.sh
LINES = [(m.group(1), m.group(2), m.group(3).split())
         for m in re.finditer(r"^(step|guard) (\S+) (.+)$", SCRIPT, re.M)]


class DeclarationTest(unittest.TestCase):
    def test_every_step_is_declared_and_only_steps(self) -> None:
        self.assertEqual([n for k, n, _ in LINES if k == "step"], list(ps.STEPS))

    def test_the_steps_run_in_the_order_the_pipeline_needs(self) -> None:
        order = [n for _, n, _ in LINES]
        for before, after in [("masts", "signals"), ("signals", "head-plan"), ("head-plan", "cats"),
                              ("le-cutover", "sml-current"), ("sml-current", "tables"), ("tables", "cats")]:
            self.assertLess(order.index(before), order.index(after), f"{before} before {after}")

    def test_every_output_pattern_names_a_file(self) -> None:
        for name, step in ps.STEPS.items():
            for pat in step.outputs:
                if "/trial/" in pat:      # gitignored, so a fresh checkout does not hold them yet
                    continue
                with self.subTest(step=name, output=pat):
                    self.assertTrue(ps.expand([pat]), f"{pat} matches nothing")

    def test_glob_matching_follows_path_glob(self) -> None:
        self.assertTrue(ps._glob_match("a/b/c.py", "a/**/*.py"))
        self.assertTrue(ps._glob_match("a/c.py", "a/**/*.py"))
        self.assertFalse(ps._glob_match("a/b/c.py", "a/*.py"))
        self.assertFalse(ps._glob_match("a/b/c.txt", "a/**/*.py"))


class StampTest(unittest.TestCase):
    """A fake repo holding the head-plan step's files."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.store = self.tmp / "repo", self.tmp / "stamps"
        for rel, text in {"jmri/layouts/hart/data/wiring.csv": "w\n",
                          "jmri/layouts/hart/data/schematic/lcos_nodes.csv": "n\n",
                          "jmri/layouts/hart/output/signal_head_plan.csv": "p\n",
                          "tools/schematic/x.py": "code\n"}.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text)
        self.cmd = ["python3", "build.py"]
        patch = unittest.mock.patch.object(ps, "unstampable", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def current(self, name="head-plan", cmd=None) -> bool:
        return ps.is_current(name, self.cmd if cmd is None else cmd, self.root, self.store)

    def test_a_step_never_run_is_not_current(self) -> None:
        self.assertFalse(self.current())

    def test_hit_after_record(self) -> None:
        ps.record("head-plan", self.cmd, self.root, self.store)
        self.assertTrue(self.current())

    def test_miss_when_an_input_changes(self) -> None:
        ps.record("head-plan", self.cmd, self.root, self.store)
        (self.root / "jmri/layouts/hart/data/wiring.csv").write_text("w2\n")
        self.assertFalse(self.current())

    def test_miss_when_an_output_is_edited_or_removed(self) -> None:
        out = self.root / "jmri/layouts/hart/output/signal_head_plan.csv"
        ps.record("head-plan", self.cmd, self.root, self.store)
        out.write_text("hand edit\n")
        self.assertFalse(self.current())
        ps.record("head-plan", self.cmd, self.root, self.store)
        out.unlink()
        self.assertFalse(self.current())

    def test_miss_when_the_code_or_the_command_changes(self) -> None:
        ps.record("head-plan", self.cmd, self.root, self.store)
        self.assertFalse(self.current(cmd=["python3", "other.py"]))
        (self.root / "tools/schematic/x.py").write_text("code2\n")
        self.assertFalse(self.current())

    def test_an_unrelated_file_does_not_miss(self) -> None:
        ps.record("head-plan", self.cmd, self.root, self.store)
        (self.root / "README.md").write_text("x\n")
        self.assertTrue(self.current())

    def test_a_trial_plugin_folder_and_the_required_flag_are_in_the_stamp(self) -> None:
        ps.record("head-plan", self.cmd, self.root, self.store)
        plugin = self.tmp / "plugin"
        plugin.mkdir()
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.invalid"}
        for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x"]):
            subprocess.run(["git", *args], cwd=plugin, check=True, env=env)
        with unittest.mock.patch.dict(os.environ, {"SCHEMATIC_PLUGIN": str(plugin)}):
            self.assertFalse(self.current(), "a trial folder is another plugin")
            ps.record("head-plan", self.cmd, self.root, self.store)
            self.assertTrue(self.current())
            (plugin / "edit.py").write_text("x\n")
            subprocess.run(["git", "add", "edit.py"], cwd=plugin, check=True, env=env)
            self.assertFalse(self.current(), "an uncommitted change in the trial folder")
        with unittest.mock.patch.dict(os.environ, {"SCHEMATIC_REQUIRED": "1"}):
            self.assertFalse(self.current())

    def test_forget_drops_the_stamp(self) -> None:
        ps.record("head-plan", self.cmd, self.root, self.store)
        ps.forget("head-plan", self.store)
        self.assertFalse(self.current())


class UnstampableTest(unittest.TestCase):
    def test_hart_tables_means_no_stamps(self) -> None:
        with unittest.mock.patch.dict(os.environ, {"HART_TABLES": "/x/tables.xml"}):
            self.assertIn("HART_TABLES", ps.unstampable())
            tmp = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, tmp)
            ps.record("hands", (), REPO, tmp)
            self.assertEqual(list(tmp.iterdir()), [])
            self.assertFalse(ps.is_current("hands", (), REPO, tmp))

    def test_a_missing_plugin_means_no_stamps(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        with unittest.mock.patch.dict(os.environ, {"SCHEMATIC_PLUGIN": ""}):
            self.assertIn("not checked out", ps.unstampable(tmp))


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
            script.write_text("import os, sys\n"
                              f"open({str(self.log)!r}, 'a').write({cmd[1]!r} + ' ' + ' '.join(sys.argv[1:]) + '\\n')\n")
        (self.root / "tools/schematic").mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / "tools/schematic/build_panels.sh", self.root / "tools/schematic/build_panels.sh")
        shutil.copy(REPO / "tools/schematic/panel_stamps.py", self.root / "tools/schematic/panel_stamps.py")
        wiring = self.root / "jmri/layouts/hart/data/wiring.csv"
        wiring.parent.mkdir(parents=True, exist_ok=True)
        wiring.write_text("w\n")
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
    """Each step run once under an audit hook: every repo file it reads must be one its declaration covers."""

    def test_every_file_a_step_reads_is_declared(self) -> None:
        try:
            import build_layout_le as ble
            ble.plugin()
        except Exception as exc:  # noqa: BLE001 - no plugin checked out: nothing to audit
            self.skipTest(f"schematic-maps plugin: {exc}")
        for _kind, name, cmd in [l for l in LINES if l[0] == "step"]:
            with self.subTest(step=name), tempfile.TemporaryDirectory() as pyc:
                env = {**os.environ, "PYTHONPYCACHEPREFIX": pyc}      # imports read their source, not a cached copy
                r = subprocess.run([sys.executable, str(REPO / "tools/schematic/audit_reads.py"), *cmd[1:], "--check"],
                                   cwd=REPO, capture_output=True, text=True, env=env)
                self.assertEqual(r.returncode, 0, r.stderr[-600:])
                read = [l[2:] for l in r.stdout.splitlines() if l.startswith("R ")]
                self.assertTrue(read, f"{name}: the hook saw no reads")
                missed = [p for p in read if not ps.covered(p, name)]
                self.assertEqual(missed, [], f"{name} reads files its declaration in panel_stamps.STEPS does not cover")
                absent = [l[2:] for l in r.stdout.splitlines() if l.startswith("M ") and not ps.covered(l[2:], name)]
                self.assertEqual(absent, [], f"{name} looks for files its declaration does not cover")
                listed = [l[2:] for l in r.stdout.splitlines() if l.startswith("D ") and not ps.dir_covered(l[2:], name)]
                self.assertEqual(listed, [], f"{name} lists folders its declaration does not reach")


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
        self.assertEqual(msg, "SML discovery is stale: run jmri/layouts/hart/scripts/run_sml_discover.sh on the Mac "
                              "(PanelPro), then make panels")

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
        import re
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
