"""The deploy carries the panel background and retires old host scripts."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SYNC = (ROOT / "tools/hosts/sync_hart_package.sh").read_text(encoding="utf-8")
PI = (ROOT / "tools/hosts/pi/apply_hart_package_local.sh").read_text(encoding="utf-8")
WIN = (ROOT / "tools/hosts/windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
OLD = (
    "sync_turnout_buttons.py",
    "sync_yard_ladder_buttons.py",
    "apply_dispatcher_roster_profiles.py",
    "SetBlockPreviewValues.py",
    "sync_layout_button.py",
    "mqtt_signalhead_publisher.py",
)


class PanelBackground(unittest.TestCase):
    def test_source_is_in_resources(self):
        self.assertTrue((ROOT / "jmri/resources/misc/hart_panel_bg.jpg").is_file())

    def test_tables_path_matches_install_folder(self):
        tables = (ROOT / "jmri/layouts/hart/output/tables.xml").read_text(encoding="utf-8")
        self.assertIn("preference:resources/misc/hart_panel_bg.jpg", tables)

    def test_every_host_installs_it(self):
        self.assertIn('"$stage/cats/resources/misc"', SYNC)
        self.assertIn("_install_misc_into", SYNC)
        self.assertIn('"resources/misc"', PI)
        self.assertIn("resources\\misc", WIN)


class UssSensorIcons(unittest.TestCase):
    """HART's yellow USS icons install into the profile only, never the JMRI install."""

    def test_tables_use_the_profile_copy(self):
        tables = (ROOT / "jmri/layouts/hart/output/tables.xml").read_text(encoding="utf-8")
        self.assertIn("preference:resources/icons/USS/sensor/yellow-on.gif", tables)
        self.assertNotIn("program:resources/icons/USS/sensor/yellow", tables)

    def test_hosts_install_into_the_profile(self):
        self.assertIn('"resources/icons/USS/sensor"', PI)
        self.assertIn("'resources\\icons\\USS\\sensor'", WIN)

    def test_windows_never_copies_into_program_files(self):
        for line in WIN.splitlines():
            if "Copy-Item" in line or "New-Item" in line:
                self.assertNotIn("Program Files", line)
        install = WIN[WIN.index("$ussSrc ="):WIN.index("$ctcSrc =")]
        self.assertNotIn("Program Files", install)


class RetiredScripts(unittest.TestCase):
    def test_every_host_removes_them(self):
        for name in OLD:
            for text in (SYNC, PI, WIN):
                self.assertIn(name, text)

    def test_copies_are_kept(self):
        self.assertTrue((ROOT / "archive/jmri-scripts/sync_turnout_buttons.py").is_file())
        self.assertTrue((ROOT / "archive/jmri-scripts/sync_yard_ladder_buttons.py").is_file())
        self.assertTrue((ROOT / "archive/layouts/linear6/SetBlockPreviewValues.py").is_file())
        self.assertTrue((ROOT / "jmri/layouts/hart/scripts/apply_dispatcher_roster_profiles.py").is_file())


if __name__ == "__main__":
    unittest.main()
