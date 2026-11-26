"""The deploy carries the panel background; the retired host scripts are kept in the repo."""

import sys
import unittest
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
STEPS = ROOT / "tools/hosts/deploy"
# The deploy is the entry point and its steps (gate, stage, ship_mac, ship_pi, ship_win, common): the text any of them holds.
SYNC = "\n".join(p.read_text(encoding="utf-8")
                  for p in [ROOT / "tools/hosts/sync_hart_package.sh", *sorted(STEPS.glob("*.sh"))])
STAGE = (STEPS / "stage.sh").read_text(encoding="utf-8")
MAC = (STEPS / "ship_mac.sh").read_text(encoding="utf-8")
PI = (ROOT / "tools/hosts/pi/apply_hart_package_local.sh").read_text(encoding="utf-8")
WIN = (ROOT / "tools/hosts/windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")


class PanelBackground(unittest.TestCase):
    def test_source_is_in_resources(self):
        self.assertTrue((ROOT / "jmri/resources/misc/hart_panel_bg_plain.jpg").is_file())

    def test_tables_path_matches_install_folder(self):
        # the generated panel's backdrop: the picture without the compass rose (panel_items.json)
        tables = paths.TABLES_XML.read_text(encoding="utf-8")
        self.assertIn("preference:resources/misc/hart_panel_bg_plain.jpg", tables)

    def test_every_host_installs_it(self):
        self.assertIn('"$stage/cats/resources/misc"', SYNC)
        self.assertIn("_install_misc_into", SYNC)
        self.assertIn('"resources/misc"', PI)
        self.assertIn("resources\\misc", WIN)


class UssSensorIcons(unittest.TestCase):
    """HART's yellow USS icons install into the profile only, never the JMRI install."""

    def test_tables_use_the_profile_copy(self):
        tables = paths.TABLES_XML.read_text(encoding="utf-8")
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
    """No apply path deletes them any more (test_apply_no_retired_names.py); their copies are kept."""

    def test_copies_are_kept(self):
        self.assertTrue((ROOT / "archive/code/jmri-scripts/sync_turnout_buttons.py").is_file())
        self.assertTrue((ROOT / "archive/code/jmri-scripts/sync_yard_ladder_buttons.py").is_file())
        self.assertTrue((ROOT / "archive/data/layouts/linear6/SetBlockPreviewValues.py").is_file())
        self.assertTrue((ROOT / "jmri/layouts/hart/scripts/apply_dispatcher_roster_profiles.py").is_file())


class ParkedFeatures(unittest.TestCase):
    """While a feature is parked (hartlib.parked) the deploy ships none of its files, and nothing removes the copies
    already installed on a host (owner, 2026-11-17: they stay until removed by hand)."""

    def test_the_deploy_reads_the_parked_setting(self):
        self.assertIn("python3 -m hartlib.parked dirs", SYNC)
        self.assertIn("python3 -m hartlib.parked jython", SYNC)
        from hartlib import parked
        self.assertEqual(parked.shipped_dirs(frozenset({"dispatcher", "uss"})),
                         ["jmri/layouts/hart/dispatcher", "jmri/layouts/hart/ctc"])
        self.assertEqual(parked.shipped_jython(frozenset({"dispatcher"})), ["repair_dispatcher_traininfo.py"])
        self.assertEqual(parked.shipped_dirs(frozenset()), [])

    def test_parked_folders_are_only_staged_when_unparked(self):
        stage = STAGE[STAGE.index("stage_package() {"):STAGE.index("# stage_host_finish")]
        self.assertIn("if ! parked_dir jmri/layouts/hart/dispatcher; then", stage)
        self.assertIn("if ! parked_dir jmri/layouts/hart/ctc &&", stage)
        self.assertNotIn('"$stage/ctc/icons" \\', stage)          # no empty folder made up front

    def test_hosts_mirror_traininfo_only_from_the_package(self):
        # the mirror that deletes (rsync --delete, robocopy /PURGE) runs only when the package holds the traininfo
        pi = PI[PI.index('TRAININFO="$HART'):]
        self.assertLess(pi.index('if [[ ! -d "$HART/jmri/layouts/hart/dispatcher" ]]'), pi.index("rsync -a --delete"))
        win = WIN[WIN.index("$trainInfoSrc = "):]
        self.assertLess(win.index("if (Test-Path $trainInfoSrc)"), win.index("/PURGE"))
        mac = MAC[MAC.index("install_jython_scripts() {"):]
        self.assertLess(mac.index("if parked_dir jmri/layouts/hart/dispatcher; then"), mac.index("rsync -a --delete"))


if __name__ == "__main__":
    unittest.main()
