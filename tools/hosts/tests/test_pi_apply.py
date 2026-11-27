"""The Pi keeps one tables.xml, in JMRI_UserFiles, and its profile's saved panel windows take that file's sizes."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pi_drop import PiHost, applied, profile_scripts, start_up  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[3] / "tools/hosts/pi/apply_hart_package_local.sh"

class PiTablesTest(unittest.TestCase):
    def test_deploy_moves_tables_out_of_hart(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('mv -f "$HART/tables.xml" "$UF/tables.xml"', source)
        self.assertNotIn('cp -f "$HART/tables.xml"', source)

    def test_hosts_have_no_hart_folder(self) -> None:
        for folder in (SCRIPT.parent, SCRIPT.parent.parent / "windows"):
            for path in folder.iterdir():
                if path.suffix in {".sh", ".bat", ".ps1", ".desktop", ".txt"} or path.name == "JMRI_CATS":
                    source = path.read_text(encoding="utf-8", errors="replace")
                    self.assertNotIn("/home/pi/hart", source, path.name)
                    self.assertNotIn("USERPROFILE%\\hart", source, path.name)
                    self.assertNotIn("USERPROFILE 'hart", source, path.name)

    def test_windows_deploy_writes_only_to_user_files(self) -> None:
        source = (SCRIPT.parent.parent / "windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
        self.assertNotIn("$dests.Add((Join-Path $_.FullName 'tables.xml'))", source)
        self.assertNotIn("$roots.Add($_.FullName)", source)

    def test_windows_apply_finds_user_python_and_checks_it(self) -> None:
        source = (SCRIPT.parent.parent / "windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
        path_merge = source.index("GetEnvironmentVariable('Path', 'User')")
        find = source.index("$python = Find-Python")
        call = source.index("& $python.Exe @pyArgs")
        self.assertLess(path_merge, find, "user PATH must be loaded before Python is looked up")
        self.assertLess(find, call)
        self.assertIn("$env:Path = (@($first) + @($rest)) -join ';'", source, "user PATH goes first")
        after = source[call:call + 300]
        self.assertLess(after.index("$LASTEXITCODE"), after.index("Start Up retargeted"),
                        "a failed retarget must not report success")

    def test_windows_scripts_find_jmri_by_command_line_from_one_shared_file(self) -> None:
        """No PowerShell on the Mac: the scripts are read as text. A bare java process (the STS or another tool) must
        not block the deploy, so both steps ask jmri_processes.ps1, which holds kill_cats.ps1's patterns."""
        win = SCRIPT.parent.parent / "windows"
        apply = (win / "apply_hart_package_local.ps1").read_text(encoding="utf-8")
        kill = (win / "kill_cats.ps1").read_text(encoding="utf-8")
        shared = (win / "jmri_processes.ps1").read_text(encoding="utf-8")
        self.assertNotIn("Get-Process java", apply)
        self.assertEqual(apply.count("Get-JmriProcesses"), 4)    # the Operations step and the window-size step
        self.assertIn(". (Join-Path $hart 'cats\\scripts\\windows\\jmri_processes.ps1')", apply)
        self.assertIn(". (Join-Path $PSScriptRoot 'jmri_processes.ps1')", kill)
        self.assertNotIn("$rx", kill)
        self.assertIn("Get-CimInstance Win32_Process", shared)
        self.assertIn("cats\\.apps\\.Crandic", shared)
        self.assertIn("Format-JmriProcesses", apply)    # the skip messages name what was found
        self.assertIn("'jmri_processes.ps1'", (win / "create_cats_desktop.ps1").read_text(encoding="utf-8"))

    def test_windows_window_size_step_takes_an_empty_result_as_an_empty_array(self) -> None:
        source = (SCRIPT.parent.parent / "windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
        self.assertIn("$uis = @(@(foreach ($root in $uiRoots) {", source)
        self.assertIn("}) | Select-Object -Unique)", source)

    def test_windows_apply_python_order_and_missing_python(self) -> None:
        """py -3, then python, then python3; Store stubs skipped; no Python warns and skips."""
        source = (SCRIPT.parent.parent / "windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
        self.assertIn("foreach ($c in @(@('py', '-3'), @('python'), @('python3')))", source)
        self.assertIn("-notmatch '\\\\WindowsApps\\\\'", source)
        self.assertNotIn("& python @pyArgs", source)
        finder = source[source.index("function Find-Python"):source.index("$python = Find-Python")]
        self.assertIn("sys.version_info[0] == 3", finder, "each candidate must start a Python 3")
        self.assertLess(finder.index("$LASTEXITCODE -eq 0"), finder.index("return [pscustomobject]"))
        block = source[source.index("if (Test-Path $patchPy)"):source.index("& $python.Exe @pyArgs")]
        self.assertIn("if (-not $python)", block)
        self.assertIn("Write-Warning", block)
        self.assertNotIn("throw", block, "a missing Python warns instead of failing the deploy")

    def test_pi_drop_stays_in_tmp_and_is_removed(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("/tmp/hart-deploy.*)", source)
        self.assertIn("""trap 'rm -rf "$HART"' EXIT""", source)


TABLES = """<?xml version="1.0" encoding="UTF-8"?>
<layout-config>
  <LayoutEditor class="x" name="HART Railroad" windowwidth="1920" windowheight="{main}"/>
  <LayoutEditor class="x" name="Main Level" windowwidth="1920" windowheight="385"/>
</layout-config>
"""
WINDOWS = """<?xml version="1.0" encoding="UTF-8"?>
<auxiliary-configuration>
    <windowDetails xmlns="http://jmri.org/xml/schema/auxiliary-configuration/window-details-4-3-5.xsd">
        <window xmlns="" class="jmri.jmrit.display.layoutEditor.LayoutEditor:HART Railroad" height="{saved}" locX="0.0" locY="26.0" width="1920.0"/>
    </windowDetails>
</auxiliary-configuration>
"""
UI = ".jmri/TCS_MQTT.jmri/profile/0badf00d/user-interface.xml"
# A PanelPro JVM as ps shows it on the Pi (PanelPro -p <profile>).
JAVA = "java -Djava.awt.headless=false -Dorg.jmri.profile={profile} -cp .:jmri.jar apps.PanelPro.PanelPro"
CTC = "/home/pi/JMRI_UserFiles/cats/panels/HART_CTC.xml"
PROFILE = start_up("preference:jython/jmri_cmd_watcher.py")     # the Start Up list the apply step edits first


class PiPanelWindowSizes(unittest.TestCase):
    """After it installs tables.xml, the apply step sets the profile's saved panel window sizes to the installed
    tables' (panel_window_sizes.py from the package, over the hartlib modules the package carries)."""

    def apply(self, saved: str = "1018.0", ui: str = UI, **kw):
        package = {**profile_scripts(), "tables.xml": TABLES.format(main="1032"), "cats/deploy_stamp.txt": "x\n"}
        installed = {"JMRI_UserFiles/tables.xml": TABLES.format(main="900")}     # the last deploy's tables
        if ui:
            installed[ui] = WINDOWS.format(saved=saved)
        return applied(package, installed=installed, profile=PROFILE, **kw)

    @staticmethod
    def backups(pi: PiHost) -> list[Path]:
        return sorted(pi.home.glob(".jmri/*/profile/*/user-interface.xml.hart-*.bak"))

    def test_saved_sizes_take_the_tables_just_installed_and_the_old_file_is_kept(self) -> None:
        with self.apply() as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertIn('LayoutEditor:HART Railroad" height="1032.0"', (pi.home / UI).read_text(encoding="utf-8"))
            self.assertIn("HART Railroad: 1920.0x1018.0 -> 1920.0x1032.0", pi.out)
            self.assertIn("Main Level: no saved window (JMRI opens it at the tables' size)", pi.out)
            [backup] = self.backups(pi)
            self.assertEqual(backup.read_text(encoding="utf-8"), WINDOWS.format(saved="1018.0"))

    def test_nothing_to_change_writes_nothing_and_keeps_no_copy(self) -> None:
        with self.apply(saved="1032.0") as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertEqual((pi.home / UI).read_text(encoding="utf-8"), WINDOWS.format(saved="1032.0"))
            self.assertEqual(self.backups(pi), [])
            self.assertIn("every saved panel window already has the tables' size", pi.out)

    def test_a_running_jmri_leaves_the_file_alone(self) -> None:
        for java in (JAVA.format(profile="TCS_MQTT.3f32a166"), JAVA.format(profile="TCS_MQTT")):
            with self.subTest(java=java), self.apply(processes=[java]) as pi:
                self.assertEqual(pi.code, 0, pi.out)
                self.assertEqual((pi.home / UI).read_text(encoding="utf-8"), WINDOWS.format(saved="1018.0"))
                self.assertIn("Panel window sizes NOT set: JMRI runs on the profile TCS_MQTT", pi.out)

    def test_jmri_on_a_profile_that_only_starts_the_same_is_not_this_profile(self) -> None:
        others = [JAVA.format(profile="TCS_MQTT_test"), JAVA.format(profile="TCS_MQTT_test.0badf00d"),
                  JAVA.format(profile="TCS_MQTTX")]
        with self.apply(processes=others) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertNotIn("NOT set", pi.out)
            self.assertIn('height="1032.0"', (pi.home / UI).read_text(encoding="utf-8"))

    def test_a_full_profile_id_matches_only_that_id(self) -> None:
        env = {"HART_PI_PROFILE": "TCS_MQTT.3f32a166"}
        with self.apply(processes=[JAVA.format(profile="TCS_MQTT.3f32a166x")], env=env) as pi:
            self.assertNotIn("NOT set", pi.out)
        with self.apply(processes=[JAVA.format(profile="TCS_MQTT.3f32a166")], env=env) as pi:
            self.assertIn("Panel window sizes NOT set: JMRI runs on the profile TCS_MQTT.3f32a166", pi.out)

    def test_a_profile_id_that_is_not_an_id_is_refused(self) -> None:
        with self.apply(env={"HART_PI_PROFILE": "TCS MQTT|x"}) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertIn("Panel window sizes NOT set: HART_PI_PROFILE='TCS MQTT|x' is not a JMRI profile id.", pi.out)
            self.assertFalse(any(call.startswith(("pgrep", "ps")) for call in pi.calls), pi.calls)

    def test_a_running_cats_leaves_the_file_alone_by_either_profile_word(self) -> None:
        """CATS starts as cats.csh --profile=<id>; cats.csh hands java -Dorg.jmri.profile=<id>. Each counts alone."""
        wrapper = f"/bin/bash ./cats.csh -Dcats.folder=/home/pi/JMRI_UserFiles/cats/panels --profile={{}} {CTC}"
        cats_java = f"java -Dorg.jmri.profile={{}} -cp .:jmri.jar:cats.jar cats.apps.Crandic {CTC}"
        for line in (wrapper.format("TCS_MQTT.3f32a166"), cats_java.format("TCS_MQTT.3f32a166")):
            with self.subTest(line=line), self.apply(processes=[line]) as pi:
                self.assertEqual(pi.code, 0, pi.out)
                self.assertIn("Panel window sizes NOT set: JMRI runs on the profile TCS_MQTT", pi.out)
                self.assertEqual((pi.home / UI).read_text(encoding="utf-8"), WINDOWS.format(saved="1018.0"))
        with self.apply(processes=[wrapper.format("TCS_MQTT_test"), "vim notes--profile=TCS_MQTT"]) as pi:
            self.assertNotIn("NOT set", pi.out)

    def test_a_jmri_app_that_names_no_profile_counts_as_on_it(self) -> None:
        """PanelPro started with no -p opens the profile JMRI picks; on the Pi that is the one profile."""
        with self.apply(processes=["java -Djava.awt.headless=false -cp .:jmri.jar apps.PanelPro.PanelPro"]) as pi:
            self.assertIn("Panel window sizes NOT set: JMRI runs on the profile TCS_MQTT", pi.out)
        with self.apply(processes=["java -jar sts.jar", "python3 apps.PanelPro.PanelPro.py"]) as pi:
            self.assertNotIn("NOT set", pi.out)

    def test_a_process_list_it_cannot_read_sets_nothing(self) -> None:
        with self.apply(env={"PI_DROP_PS_FAILS": "1"}) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertIn("Panel window sizes NOT set: cannot tell whether JMRI runs on the profile TCS_MQTT", pi.out)
            self.assertEqual((pi.home / UI).read_text(encoding="utf-8"), WINDOWS.format(saved="1018.0"))

    def test_a_profile_with_no_saved_windows_is_one_line(self) -> None:
        with self.apply(ui="") as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertIn("Panel window sizes: no user-interface.xml in ~/.jmri/TCS_MQTT.jmri", pi.out)

    def test_the_profile_is_the_one_the_deploy_names(self) -> None:
        other = ".jmri/Rehearsal.jmri/profile/0badf00d/user-interface.xml"
        with self.apply(ui=other, env={"HART_PI_PROFILE": "Rehearsal.0badf00d"}) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertIn('height="1032.0"', (pi.home / other).read_text(encoding="utf-8"))
        with self.apply(ui=other, env={"HART_PI_PROFILE": "Rehearsal.0badf00d"},
                        processes=[JAVA.format(profile="Rehearsal.0badf00d")]) as pi:
            self.assertIn("JMRI runs on the profile Rehearsal.0badf00d", pi.out)

    def test_a_file_it_cannot_read_warns_and_the_deploy_goes_on(self) -> None:
        package = {**profile_scripts(), "tables.xml": TABLES.format(main="1032"), "cats/deploy_stamp.txt": "x\n"}
        with applied(package, installed={UI: "<other/>"}, profile=PROFILE) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertIn("no <windowDetails>", pi.out)
            self.assertIn("WARN: panel window sizes not set in", pi.out)
            self.assertTrue((pi.user_files / "cats/deploy_stamp.txt").is_file(), pi.out)


if __name__ == "__main__":
    unittest.main()
