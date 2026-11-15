from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "patch_jmri_startup.py"


def _load():
    spec = importlib.util.spec_from_file_location("patch_jmri_startup", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


PROFILE = """\
<?xml version="1.0" encoding="UTF-8"?>
<profile>
    <startup>
        <perform xmlns="" class="apps.startup.configurexml.ScriptButtonModelXml" enabled="no" name="Restart RPi" type="Button">
            <property name="script" value="program:jython/RaspberryPiRestart.py"/>
        </perform>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformFileModelXml" enabled="yes" name="preference:tables.xml" type="XmlFile"/>
        <perform name="/Users/lnevo/hart/jmri/layouts/hart/scripts/panel_status.py" type="ScriptFile" enabled="yes" class="jmri.util.startup.configurexml.PerformScriptModelXml"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="/home/pi/hart/jmri/scripts/signal_coordinator.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/hide_cats_desk_windows.py" type="ScriptFile"/>
    </startup>
</profile>
"""


class RetargetJython(unittest.TestCase):
    def test_rewrites_home_and_absolute_perform_script_only(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td) / "profile.xml"
            profile.write_text(PROFILE, encoding="utf-8")
            notes = mod.retarget_to_preference_jython(
                profile,
                [
                    "panel_status.py",
                    "signal_coordinator.py",
                    "hide_cats_desk_windows.py",
                ],
            )
            txt = profile.read_text(encoding="utf-8")
        self.assertEqual(
            notes,
            [
                "/Users/lnevo/hart/jmri/layouts/hart/scripts/panel_status.py -> preference:jython/panel_status.py",
                "/home/pi/hart/jmri/scripts/signal_coordinator.py -> preference:jython/signal_coordinator.py",
            ],
        )
        self.assertIn('name="preference:jython/panel_status.py"', txt)
        self.assertIn('name="preference:jython/signal_coordinator.py"', txt)
        self.assertIn('name="preference:jython/hide_cats_desk_windows.py"', txt)
        self.assertIn("program:jython/RaspberryPiRestart.py", txt)
        self.assertIn('name="preference:tables.xml"', txt)
        self.assertIn('name="Restart RPi"', txt)

    def test_idempotent(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td) / "profile.xml"
            profile.write_text(PROFILE, encoding="utf-8")
            mod.retarget_to_preference_jython(profile, ["panel_status.py"])
            notes = mod.retarget_to_preference_jython(
                profile, ["panel_status.py"]
            )
        self.assertEqual(notes, [])

    def test_renames_retired_yard_ladder_basename(self) -> None:
        mod = _load()
        profile_txt = PROFILE.replace(
            "panel_status.py", "sync_yard_ladder_buttons.py"
        )
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td) / "profile.xml"
            profile.write_text(profile_txt, encoding="utf-8")
            notes = mod.retarget_to_preference_jython(
                profile, ["panel_status.py"]
            )
            txt = profile.read_text(encoding="utf-8")
        self.assertTrue(any("sync_yard_ladder_buttons.py -> panel_status.py" in n for n in notes))
        self.assertIn('name="preference:jython/panel_status.py"', txt)
        self.assertNotIn("sync_yard_ladder_buttons.py", txt)

    def test_renames_retired_turnout_buttons_basename(self) -> None:
        mod = _load()
        profile_txt = PROFILE.replace(
            "panel_status.py", "sync_turnout_buttons.py"
        )
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td) / "profile.xml"
            profile.write_text(profile_txt, encoding="utf-8")
            notes = mod.retarget_to_preference_jython(
                profile, ["panel_status.py"]
            )
            txt = profile.read_text(encoding="utf-8")
        self.assertTrue(any("sync_turnout_buttons.py -> panel_status.py" in n for n in notes))
        self.assertIn('name="preference:jython/panel_status.py"', txt)
        self.assertNotIn("sync_turnout_buttons.py", txt)


    def test_renames_old_coordinator_and_panel_script_names(self) -> None:
        mod = _load()
        profile_txt = PROFILE.replace("panel_status.py", "sync_layout_button.py").replace(
            "signal_coordinator.py", "mqtt_signalhead_publisher.py"
        )
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td) / "profile.xml"
            profile.write_text(profile_txt, encoding="utf-8")
            mod.retarget_to_preference_jython(
                profile, ["panel_status.py", "signal_coordinator.py"]
            )
            txt = profile.read_text(encoding="utf-8")
        self.assertIn('name="preference:jython/panel_status.py"', txt)
        self.assertIn('name="preference:jython/signal_coordinator.py"', txt)
        self.assertNotIn("sync_layout_button.py", txt)
        self.assertNotIn("mqtt_signalhead_publisher.py", txt)


class HideCatsChromeSource(unittest.TestCase):
    def test_cats_only_help_quit_hooks(self) -> None:
        src = (
            Path(__file__).resolve().parents[3]
            / "jmri"
            / "layouts"
            / "hart"
            / "scripts"
            / "hide_cats_desk_windows.py"
        )
        raw = src.read_bytes()
        self.assertTrue(raw.decode("ascii"))
        text = raw.decode("ascii")
        self.assertIn("def under_cats()", text)
        self.assertIn("install_window_toolbar", text)
        self.assertIn("remove_window_toolbar", text)
        self.assertIn("add_script_style_buttons", text)
        self.assertIn("_clean_file_quit", text)
        self.assertIn("Apps.handleQuit()", text)
        self.assertNotIn("JMenuItem", text)
        self.assertNotIn("Dispatcher Guide", text)
        self.assertIn("CTC Panel", text)
        self.assertIn("decorate_dispatcher_panel", text)
        self.assertNotIn("HART: CATS Help/Quit on Dispatcher Panel", text)
        self.assertIn("HelpUtil.displayHelpRef", text)
        self.assertNotIn("\u2014", text)


    def test_load_tables_points_start_up_at_one_path(self) -> None:
        mod = _load()
        sample = (
            '<perform xmlns="" class="jmri.util.startup.configurexml.PerformFileModelXml" '
            'enabled="yes" name="preference:tables.xml" type="XmlFile"/>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.xml"
            profile.write_text(sample, encoding="utf-8")
            self.assertEqual(mod.load_tables_from(profile, "home:hart/x/tables.xml"), "changed")
            self.assertIn('name="home:hart/x/tables.xml"', profile.read_text(encoding="utf-8"))
            self.assertEqual(mod.load_tables_from(profile, "home:hart/x/tables.xml"), "already")


PUBLISHING_PROFILE = """\
<profile>
    <startup>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformFileModelXml" enabled="yes" name="preference:tables.xml" type="XmlFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/panel_status.py" type="ScriptFile"/>
        <perform name="preference:jython/sts_car_sync.py" type="ScriptFile" enabled="yes" class="jmri.util.startup.configurexml.PerformScriptModelXml"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="/home/pi/hart/jmri/scripts/signal_coordinator.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/signal_coordinator.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/mimic_relay.py" type="ScriptFile"></perform>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/hide_cats_desk_windows.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/old_panel_status.py" type="ScriptFile"/>
    </startup>
</profile>
"""


class DisablePublishing(unittest.TestCase):
    def test_every_entry_of_every_publishing_script_is_disabled(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.xml"
            profile.write_text(PUBLISHING_PROFILE, encoding="utf-8")
            notes = mod.disable_publishing(profile)
            text = profile.read_text(encoding="utf-8")
        self.assertIn("disabled 2 of 2: signal_coordinator.py", notes)
        self.assertIn("not in Start Up (ok): jmri_cmd_watcher.py", notes)
        for name in mod.PUBLISHING_STARTUP_SCRIPTS:
            for line in text.splitlines():
                if f'/{name}"' in line:
                    self.assertIn('enabled="no"', line, name)
        for keep in ("hide_cats_desk_windows.py", "old_panel_status.py", "preference:tables.xml"):
            line = next(l for l in text.splitlines() if keep in l)
            self.assertIn('enabled="yes"', line, keep)
        self.assertEqual(
            {"panel_status.py", "signal_coordinator.py", "sts_car_sync.py", "jmri_cmd_watcher.py", "mimic_relay.py"},
            set(mod.PUBLISHING_STARTUP_SCRIPTS))

    def test_an_entry_it_cannot_switch_off_stops_the_run(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.xml"
            odd = '<perform enabled=\'yes\' name="preference:jython/panel_status.py" type="ScriptFile"/>'
            profile.write_text(odd, encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                mod.disable_publishing(profile)
            self.assertIn("panel_status.py is still enabled", str(caught.exception))
            self.assertEqual(odd, profile.read_text(encoding="utf-8"))


class BackupRestore(unittest.TestCase):
    def test_backup_is_fixed_beside_the_profile_and_restore_puts_it_back(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.xml"
            profile.write_text("original", encoding="utf-8")
            bak = mod.backup_profile(profile)
            self.assertEqual(Path(tmp) / "profile.xml.hart-run.bak", bak)
            profile.write_text("patched", encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                mod.backup_profile(profile)   # an unfinished run is never overwritten
            self.assertIn("restore --profile", str(caught.exception))
            self.assertEqual("original", bak.read_text(encoding="utf-8"))
            mod.restore_profile(profile)
            self.assertEqual("original", profile.read_text(encoding="utf-8"))
            self.assertFalse(bak.exists())
            with self.assertRaises(SystemExit):
                mod.restore_profile(profile)


def _profile(root: Path, name: str, pid: str, user_files: str | None = None) -> Path:
    folder = root / f"{name}.jmri" / "profile"
    folder.mkdir(parents=True)
    props = [f"profile.id={pid}", "profile.name=x"]
    if user_files is not None:
        props.append(f"jmri-implementation.user-files={user_files}")
    (folder / "profile.properties").write_text("#c\n" + "\n".join(props) + "\n", encoding="utf-8")
    (folder / "profile.xml").write_text("<profile/>", encoding="utf-8")
    return folder / "profile.xml"


class CheckProfile(unittest.TestCase):
    def test_id_or_folder_must_name_the_patched_profile(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            xml = _profile(Path(tmp), "Rehearsal", "Rehearsal.1234", f"{tmp}/uf/")
            self.assertEqual(Path(f"{tmp}/uf/"), mod.check_profile(xml, "Rehearsal.1234", None))
            self.assertEqual(Path(f"{tmp}/uf/"), mod.check_profile(xml, str(Path(tmp) / "Rehearsal.jmri"), None))
            self.assertEqual(Path(f"{tmp}/uf/"), mod.check_profile(xml, str(Path(tmp) / "Rehearsal"), None))
            for wrong in ("My_JMRI_Railroad.3ef75bfd", str(Path(tmp) / "Other.jmri")):
                with self.assertRaises(SystemExit) as caught:
                    mod.check_profile(xml, wrong, None)
                self.assertIn("would patch one profile and start another", str(caught.exception))

    def test_user_files_follow_the_profile_and_a_wrong_override_stops(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            home_xml = _profile(Path(tmp), "Live", "Live.1", r"home\:JMRI_UserFiles/")
            self.assertEqual(Path.home() / "JMRI_UserFiles", mod.check_profile(home_xml, "Live.1", None))
            with self.assertRaises(SystemExit) as caught:
                mod.check_profile(home_xml, "Live.1", f"{tmp}/elsewhere")
            self.assertIn("is not the user files folder", str(caught.exception))
            default_xml = _profile(Path(tmp), "Plain", "Plain.1")
            self.assertEqual(Path(tmp) / "Plain.jmri", mod.check_profile(default_xml, "Plain.1", None))
            node = default_xml.parent / "node-a"
            node.mkdir()
            (node / "profile.properties").write_text("jmri-implementation.user-files=/x/\n", encoding="utf-8")
            # A shared profile: value is not overridden by the node, as in FileLocationsPreferences.
            self.assertEqual(Path(tmp) / "Plain.jmri", mod.check_profile(default_xml, "Plain.1", None))

    def test_node_override_and_unknown_forms(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            xml = _profile(Path(tmp), "N", "N.1", "/shared/")
            for i, value in enumerate(("/node/", "/node/")):
                d = xml.parent / f"node{i}"
                d.mkdir()
                (d / "profile.properties").write_text(f"jmri-implementation.user-files={value}\n", encoding="utf-8")
            self.assertEqual(Path("/node/"), mod.check_profile(xml, "N.1", None))
            (xml.parent / "node1" / "profile.properties").write_text("jmri-implementation.user-files=/other/\n",
                                                                     encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                mod.check_profile(xml, "N.1", None)
            self.assertIn("set JMRI_USER_FILES", str(caught.exception))
            self.assertEqual(Path(f"{tmp}/given"), mod.check_profile(xml, "N.1", f"{tmp}/given"))

    def test_not_a_profile_xml(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            stray = Path(tmp) / "profile.xml"
            stray.write_text("<profile/>", encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                mod.check_profile(stray, "x", None)
            self.assertIn("not a JMRI profile.xml", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
