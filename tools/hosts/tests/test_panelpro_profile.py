"""tools/hosts/panelpro_profile.py: the profile steps of a PanelPro wrapper run, on fixture profiles only.

HOME is a temporary folder in every test, so the "live" profile and ~/JMRI_UserFiles these
checks compare against are fixtures too; nothing reads or writes the real ones.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pi_drop import jython_rows  # noqa: E402
SCRIPT = ROOT / "tools/hosts/panelpro_profile.py"
LIVE_ID = "My_JMRI_Railroad.3ef75bfd"


def _load():
    spec = importlib.util.spec_from_file_location("hart_panelpro_profile_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


MOD = _load()

STARTUP = """\
<auxiliary-configuration>
    <startup>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformActionModelXml" enabled="yes" name="apps.SystemConsoleAction" type="Action"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformActionModelXml" enabled="yes" name="jmri.web.server.WebServerAction" type="Action"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformActionModelXml" enabled="yes" name="jmri.jmrit.withrottle.WiThrottleCreationAction" type="Action"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformFileModelXml" enabled="yes" name="preference:tables.xml" type="XmlFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/panel_status.py" type="ScriptFile"/>
        <perform name="preference:jython/sts_car_sync.py" type="ScriptFile" enabled="yes" class="jmri.util.startup.configurexml.PerformScriptModelXml"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/brand_new_publisher.py" type="ScriptFile"/>
        <perform xmlns="" class="apps.startup.configurexml.TriggerRouteModelXml" enabled="yes" name="IR:LADDER" type="Route"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/hide_cats_desk_windows.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="no" name="/old/discover_sml.py" type="ScriptFile"/>
        <perform xmlns="" class="apps.startup.configurexml.ScriptButtonModelXml" enabled="yes" name="Restart" type="Button">
            <property name="script" value="program:jython/RaspberryPiRestart.py"/>
        </perform>
    </startup>
</auxiliary-configuration>
"""


def _enabled(text: str, needle: str) -> list[bool]:
    return ['enabled="yes"' in t for t in re.findall(r"<perform\b[^>]*>", text) if needle in t]


class HomeCase(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name).resolve()
        env = {k: v for k, v in os.environ.items() if k != "HART_GUARD_JMRI_RUNNING"}
        env.update(HOME=str(self.tmp / "home"), HART_GUARD_JMRI_RUNNING="0")
        self._env = mock.patch.dict(os.environ, env, clear=True)
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._td.cleanup()

    def profile(self, base: Path, name: str, pid: str, user_files: str | None, nodes=()) -> Path:
        folder = base / f"{name}.jmri" / "profile"
        folder.mkdir(parents=True)
        lines = ["#x", f"profile.id={pid}"] + ([f"jmri-implementation.user-files={user_files}"] if user_files else [])
        (folder / "profile.properties").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for i, value in enumerate(nodes):
            (folder / f"node{i}").mkdir()
            (folder / f"node{i}" / "profile.properties").write_text(f"jmri-implementation.user-files={value}\n",
                                                                    encoding="utf-8")
        (folder / "profile.xml").write_text(STARTUP, encoding="utf-8")
        return folder / "profile.xml"

    def live(self) -> Path:
        return self.profile(self.tmp / "home/Library/Preferences/JMRI", "My_JMRI_Railroad", LIVE_ID,
                            r"home\:JMRI_UserFiles/")


class QuietStartup(HomeCase):
    def test_only_the_allowlist_and_the_run_script_stay_on(self) -> None:
        xml = self.live()
        notes = MOD.quiet_startup(xml, "/repo/jmri/layouts/hart/scripts/discover_sml.py")
        text = xml.read_text(encoding="utf-8")
        for off in ("WebServerAction", "WiThrottleCreationAction", "panel_status.py", "sts_car_sync.py",
                    "brand_new_publisher.py", "IR:LADDER"):
            self.assertEqual([False], _enabled(text, off), off)
        for on in ("SystemConsoleAction", "preference:tables.xml", "hide_cats_desk_windows.py", "Restart"):
            self.assertEqual([True], _enabled(text, on), on)
        self.assertEqual([True], _enabled(text, "discover_sml.py"))   # the old disabled entry was replaced
        self.assertIn("/repo/jmri/layouts/hart/scripts/discover_sml.py", text)
        self.assertIn("off: preference:jython/brand_new_publisher.py", notes)

    def test_every_deployed_startup_script_is_switched_off(self) -> None:
        # the Start Up scripts of the one jython list (the Mac and the Pi), and what the Pi apply step starts
        deployed = {Path(row.path).name for row in jython_rows() if row.role in ("startup", "pi")}
        pi = (ROOT / "tools/hosts/pi/apply_hart_package_local.sh").read_text(encoding="utf-8")
        deployed |= set(re.findall(r"--script preference:jython/(\w+\.py)", pi))
        self.assertIn("signal_coordinator.py", deployed)
        self.assertIn("mimic_relay.py", deployed)
        self.assertTrue(set(MOD.ALLOWED_SCRIPTS) <= deployed, "allowlist names a script no host runs")
        for name in deployed - set(MOD.ALLOWED_SCRIPTS):
            tag = ('<perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" '
                   f'enabled="yes" name="preference:jython/{name}" type="ScriptFile"/>')
            self.assertFalse(MOD._allowed(tag), name)

    def test_an_item_it_cannot_switch_off_stops_the_run(self) -> None:
        xml = self.live()
        odd = ('<perform class="jmri.util.startup.configurexml.PerformScriptModelXml" '
               "enabled='yes' name=\"preference:jython/panel_status.py\"/>")
        xml.write_text(STARTUP.replace("<startup>", "<startup>\n" + odd), encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            MOD.quiet_startup(xml, "/repo/x.py")
        self.assertIn("could not be switched off", str(caught.exception))


class BackupSealRestore(HomeCase):
    def setUp(self) -> None:
        super().setUp()
        self.xml = self.live()
        self.original = self.xml.read_bytes()
        MOD.backup_profile(self.xml)
        MOD.quiet_startup(self.xml, "/repo/x.py")
        MOD.seal_profile(self.xml)

    def test_restore_puts_the_backup_back_and_clears_both_files(self) -> None:
        MOD.restore_profile(self.xml)
        self.assertEqual(self.original, self.xml.read_bytes())
        self.assertFalse(MOD.backup_path(self.xml).exists())
        self.assertFalse(MOD.seal_path(self.xml).exists())

    def test_a_second_backup_refuses_with_the_recovery_command(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            MOD.backup_profile(self.xml)
        self.assertIn(f"restore --profile {self.xml}", str(caught.exception))

    def test_restore_refuses_while_jmri_runs(self) -> None:
        with mock.patch.dict(os.environ, {"HART_GUARD_JMRI_RUNNING": "1"}):
            with self.assertRaises(SystemExit) as caught:
                MOD.restore_profile(self.xml)
        self.assertIn("running", str(caught.exception))
        self.assertTrue(MOD.backup_path(self.xml).exists())

    def test_restore_refuses_a_profile_changed_since_the_seal_unless_forced(self) -> None:
        self.xml.write_text(self.xml.read_text(encoding="utf-8") + "<!-- edited -->", encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            MOD.restore_profile(self.xml)
        self.assertIn("changed since the run patched it", str(caught.exception))
        self.assertIn("overwrote changes", MOD.restore_profile(self.xml, force=True))
        self.assertEqual(self.original, self.xml.read_bytes())

    def test_restore_without_a_seal_needs_force(self) -> None:
        MOD.seal_path(self.xml).unlink()
        with self.assertRaises(SystemExit) as caught:
            MOD.restore_profile(self.xml)
        self.assertIn("is missing", str(caught.exception))
        MOD.restore_profile(self.xml, force=True)
        self.assertEqual(self.original, self.xml.read_bytes())


class CheckProfile(HomeCase):
    def test_live_profile_by_id(self) -> None:
        self.assertEqual(self.tmp / "home/JMRI_UserFiles", MOD.check_profile(self.live(), LIVE_ID, None))

    def test_a_copy_on_the_live_user_files_is_refused(self) -> None:
        self.live()
        clone = self.profile(self.tmp / "scratch", "Rehearsal", LIVE_ID, r"home\:JMRI_UserFiles/")
        with self.assertRaises(SystemExit) as caught:
            MOD.check_profile(clone, str(clone.parent.parent), None)
        self.assertIn("uses the live user files folder", str(caught.exception))
        with self.assertRaises(SystemExit) as caught:   # and a given value cannot paper over it
            MOD.check_profile(clone, str(clone.parent.parent), str(self.tmp / "home/JMRI_UserFiles"))
        self.assertIn("uses the live user files folder", str(caught.exception))
        with self.assertRaises(SystemExit) as caught:
            MOD.check_profile(clone, LIVE_ID, None)
        self.assertIn("carries the live profile's id", str(caught.exception))

    def test_a_copy_with_its_own_user_files(self) -> None:
        uf = self.tmp / "scratch/uf"
        clone = self.profile(self.tmp / "scratch", "Rehearsal", "Rehearsal.1", f"{uf}/")
        self.assertEqual(uf, MOD.check_profile(clone, str(clone.parent.parent), None))
        self.assertEqual(uf, MOD.check_profile(clone, "Rehearsal.1", str(uf)))
        with self.assertRaises(SystemExit) as caught:
            MOD.check_profile(clone, "Rehearsal.1", str(self.tmp / "other"))
        self.assertIn("is not the user files folder", str(caught.exception))
        with self.assertRaises(SystemExit) as caught:
            MOD.check_profile(clone, "Other.2", None)
        self.assertIn("would patch one profile and start another", str(caught.exception))

    def test_unknown_user_files_fail_even_with_a_given_value(self) -> None:
        cases = (("Nodes", "/shared/", ("/a/", "/b/"), "name different user files folders"),
                 ("Pref", "preference:x/", (), "cannot resolve"),
                 ("Settings", "settings:x/", (), "cannot resolve"))
        for name, shared, nodes, message in cases:
            with self.subTest(name=name):
                xml = self.profile(self.tmp / "scratch", name, f"{name}.1", shared, nodes)
                with self.assertRaises(SystemExit) as caught:
                    MOD.check_profile(xml, f"{name}.1", str(self.tmp / "given"))
                self.assertIn(message, str(caught.exception))

    def test_node_value_overrides_a_shared_absolute_one(self) -> None:
        xml = self.profile(self.tmp / "scratch", "N", "N.1", "/shared/", ("/node/", "/node/"))
        self.assertEqual(Path("/node/"), MOD.check_profile(xml, "N.1", None))

    def test_paths_with_spaces_or_shell_characters_are_refused(self) -> None:
        good = self.profile(self.tmp / "scratch", "Good", "Good.1", f"{self.tmp}/uf/")
        spaced = self.profile(self.tmp / "my scratch", "Spaced", "Spaced.1", f"{self.tmp}/uf/")
        for profile, launch, uf in ((spaced, str(spaced.parent.parent), None),
                                    (good, "Good.1; rm -rf x", None),
                                    (good, "Good.1", f"{self.tmp}/u f"),
                                    (good, "$(id)", None)):
            with self.subTest(launch=launch, uf=uf):
                with self.assertRaises(SystemExit) as caught:
                    MOD.check_profile(profile, launch, uf)
                self.assertIn("holds a space or a shell character", str(caught.exception))


class Properties(unittest.TestCase):
    def test_java_properties_rules(self) -> None:
        text = ("# comment \\\n"
                "! bang\n"
                "  a\\:b = home\\:JMRI_UserFiles/\n"
                "spaced value\n"
                "cont = one\\\n"
                "     two\\\\\n"
                "uni=\\u0041\\tz\\q\n"
                "empty\n"
                "colon:x\n"
                "esc\\ key=v\n")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "p.properties"
            p.write_text(text, encoding="utf-8")
            props = MOD.read_properties(p)
            self.assertEqual({"a:b": "home:JMRI_UserFiles/", "spaced": "value", "cont": "onetwo\\",
                              "uni": "A\tzq", "empty": "", "colon": "x", "esc key": "v"}, props)
            p.write_text("bad=\\u12G4\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                MOD.read_properties(p)
            self.assertIn("malformed \\u escape", str(caught.exception))


class JmriRunningProbe(unittest.TestCase):
    """jmri-running exits 0 while JMRI runs, 1 while none does, 2 with "unknown" when the check cannot say."""

    def probe(self, state: object) -> tuple[int, str]:
        import contextlib
        import io
        err = io.StringIO()
        with mock.patch.object(MOD.tables, "jmri_state", return_value=state), \
                mock.patch("sys.argv", ["panelpro_profile.py", "jmri-running"]), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as got:
            MOD.main()
        return int(got.exception.code or 0), err.getvalue()

    def test_each_state(self) -> None:
        self.assertEqual(self.probe(MOD.tables.JmriState.RUNNING), (0, ""))
        self.assertEqual(self.probe(MOD.tables.JmriState.STOPPED), (1, ""))
        self.assertEqual(self.probe(MOD.tables.JmriState.UNKNOWN), (2, "unknown\n"))

    def test_restore_refuses_when_the_check_cannot_say(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.xml"
            profile.write_text("<p/>", encoding="utf-8")
            MOD.backup_path(profile).write_text("<p/>", encoding="utf-8")
            with mock.patch.object(MOD.tables, "jmri_state", return_value=MOD.tables.JmriState.UNKNOWN), \
                    self.assertRaises(SystemExit) as got:
                MOD.restore_profile(profile)
            self.assertIn("cannot tell", str(got.exception.code))
            self.assertTrue(MOD.backup_path(profile).is_file())


if __name__ == "__main__":
    unittest.main()
