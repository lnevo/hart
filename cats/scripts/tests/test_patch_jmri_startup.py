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


if __name__ == "__main__":
    unittest.main()
