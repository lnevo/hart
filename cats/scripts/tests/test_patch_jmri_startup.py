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
        <perform name="/Users/lnevo/hart/jmri/layouts/hart/scripts/sync_layout_button.py" type="ScriptFile" enabled="yes" class="jmri.util.startup.configurexml.PerformScriptModelXml"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="/home/pi/hart/jmri/scripts/mqtt_signalhead_publisher.py" type="ScriptFile"/>
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
                    "sync_layout_button.py",
                    "mqtt_signalhead_publisher.py",
                    "hide_cats_desk_windows.py",
                ],
            )
            txt = profile.read_text(encoding="utf-8")
        self.assertEqual(
            notes,
            [
                "/Users/lnevo/hart/jmri/layouts/hart/scripts/sync_layout_button.py -> preference:jython/sync_layout_button.py",
                "/home/pi/hart/jmri/scripts/mqtt_signalhead_publisher.py -> preference:jython/mqtt_signalhead_publisher.py",
            ],
        )
        self.assertIn('name="preference:jython/sync_layout_button.py"', txt)
        self.assertIn('name="preference:jython/mqtt_signalhead_publisher.py"', txt)
        self.assertIn('name="preference:jython/hide_cats_desk_windows.py"', txt)
        self.assertIn("program:jython/RaspberryPiRestart.py", txt)
        self.assertIn('name="preference:tables.xml"', txt)
        self.assertIn('name="Restart RPi"', txt)

    def test_idempotent(self) -> None:
        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td) / "profile.xml"
            profile.write_text(PROFILE, encoding="utf-8")
            mod.retarget_to_preference_jython(profile, ["sync_layout_button.py"])
            notes = mod.retarget_to_preference_jython(
                profile, ["sync_layout_button.py"]
            )
        self.assertEqual(notes, [])

    def test_renames_retired_yard_ladder_basename(self) -> None:
        mod = _load()
        profile_txt = PROFILE.replace(
            "sync_layout_button.py", "sync_yard_ladder_buttons.py"
        )
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td) / "profile.xml"
            profile.write_text(profile_txt, encoding="utf-8")
            notes = mod.retarget_to_preference_jython(
                profile, ["sync_layout_button.py"]
            )
            txt = profile.read_text(encoding="utf-8")
        self.assertTrue(any("sync_yard_ladder_buttons.py -> sync_layout_button.py" in n for n in notes))
        self.assertIn('name="preference:jython/sync_layout_button.py"', txt)
        self.assertNotIn("sync_yard_ladder_buttons.py", txt)

    def test_renames_retired_turnout_buttons_basename(self) -> None:
        mod = _load()
        profile_txt = PROFILE.replace(
            "sync_layout_button.py", "sync_turnout_buttons.py"
        )
        with tempfile.TemporaryDirectory() as td:
            profile = Path(td) / "profile.xml"
            profile.write_text(profile_txt, encoding="utf-8")
            notes = mod.retarget_to_preference_jython(
                profile, ["sync_layout_button.py"]
            )
            txt = profile.read_text(encoding="utf-8")
        self.assertTrue(any("sync_turnout_buttons.py -> sync_layout_button.py" in n for n in notes))
        self.assertIn('name="preference:jython/sync_layout_button.py"', txt)
        self.assertNotIn("sync_turnout_buttons.py", txt)


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
        self.assertNotIn('JMenuItem("Quit")', text)
        self.assertIn("CTC Panel", text)
        self.assertIn("decorate_dispatcher_panel", text)
        self.assertNotIn("HART: CATS Help/Quit on Dispatcher Panel", text)
        self.assertIn("HelpUtil.displayHelpRef", text)
        self.assertNotIn("\u2014", text)


class DiscardSensorPublish(unittest.TestCase):
    def test_overlay_skips_discard_topics(self) -> None:
        src = (
            Path(__file__).resolve().parents[3]
            / "tools"
            / "jmri"
            / "patches"
            / "PatchMqttCme.java"
        )
        text = src.read_text(encoding="utf-8")
        self.assertIn("track/signalhead/IH", text)
        self.assertIn("_discard", text)
        self.assertIn("insertBefore", text)


if __name__ == "__main__":
    unittest.main()
