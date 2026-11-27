r"""The three apply paths (Mac, Pi, Windows) install what the package ships and delete nothing by a retired
name: the hosts hold none of these files, so a deploy has nothing of them to clean up. The one exception is
the Start Up entries of three retired scripts, which an old profile.xml can still hold (a Windows per-computer
profile can): each apply path strips them, and Windows covers every profile\<node id>\profile.xml.

The stock xml/signals/C&O-1980 of the JMRI install is never removed either; its name is in the list so no
apply path deletes it.

The Pi's apply step runs here on a made-up drop (pi_drop) holding the retired names. The Mac's step (ship_mac.sh)
installs on this machine and the Windows step is PowerShell, so for those two the tests read the script text."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pi_drop import applied, files_under, profile_scripts, start_up  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
APPLY = (
    ROOT / "tools/hosts/deploy/ship_mac.sh",
    ROOT / "tools/hosts/pi/apply_hart_package_local.sh",
    ROOT / "tools/hosts/windows/apply_hart_package_local.ps1",
)
NOT_RUN = (APPLY[0], APPLY[2])      # the Mac's and Windows' steps: these tests read their text
STARTUP_STRIP = ("apply_maintain_mqtt.py", "apply_mqtt_retain_at_startup.py", "prepare_nx_sml_paths.py")
RETIRED = (
    "hart_dispatcher_startup.py", "patch_dispatcher_facing.py",
    "sync_turnout_buttons.py", "sync_yard_ladder_buttons.py", "apply_dispatcher_roster_profiles.py",
    "SetBlockPreviewValues.py", "sync_layout_button.py", "mqtt_signalhead_publisher.py",
    "linear5_panel_bg.jpg",
    "cats-masts", "hart-aar", "C&O-1980", "install_cats_masts.ps1", "HART_Master", "launch_hart_master",
)


class PiKeepsRetiredNames(unittest.TestCase):
    """The Pi's apply step, given a package and a host that both hold every retired name, installs none of them and
    deletes none: only the one retired Start Up entry it strips goes."""

    def test_nothing_by_a_retired_name_is_installed_or_deleted(self) -> None:
        planted = {f"{where}/{name}": "retired\n" for name in RETIRED
                   for where in ("JMRI_UserFiles", "JMRI_UserFiles/jython", "JMRI/xml/signals")}
        package = {**profile_scripts(),
                   **{f"jmri/layouts/hart/scripts/{name}": "retired\n" for name in RETIRED}}
        kept = ("preference:jython/panel_status.py", "preference:jython/signal_coordinator.py",
                "preference:jython/jmri_cmd_watcher.py")
        with applied(package, installed=planted, profile=start_up(*kept, "home:prepare_nx_sml_paths.py")) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            left = files_under(pi.home)
            for rel in planted:
                with self.subTest(kept=rel):
                    self.assertIn(rel, left)
            installed = [rel for rel in left if rel not in planted]
            self.assertFalse([rel for rel in installed if any(name in rel for name in RETIRED)], installed)
            profile = pi.profile.read_text(encoding="utf-8")
        self.assertNotIn("prepare_nx_sml_paths.py", profile)
        self.assertEqual(re.findall(r'name="([^"]+)"', profile),
                         [*kept, "preference:jython/sts_car_sync.py", "preference:jython/mimic_relay.py"])


class NoRetiredNames(unittest.TestCase):
    """The Mac and Windows steps cannot run here: their text names no retired file. No step installs a JMRI patch
    (only the ADR-034 overlay, from tools/jmri/mqtt_overlay)."""

    def test_no_apply_path_names_a_retired_file(self) -> None:
        for path in NOT_RUN:
            text = path.read_text(encoding="utf-8")
            for name in RETIRED:
                with self.subTest(script=path.name, name=name):
                    self.assertNotIn(name, text)

    def test_no_apply_path_installs_a_jmri_patch(self) -> None:
        for path in APPLY:
            text = path.read_text(encoding="utf-8")
            with self.subTest(script=path.name):
                self.assertNotRegex(text, r"tools[/\\]jmri[/\\]patches")

    def test_start_up_names_appear_only_to_strip_them(self) -> None:
        for path in NOT_RUN:
            for line in path.read_text(encoding="utf-8").splitlines():
                if any(name in line for name in STARTUP_STRIP):
                    with self.subTest(script=path.name, line=line.strip()):
                        self.assertRegex(line, r"--script |\$retiredStartup = ")
                        self.assertNotRegex(line, r"\brm\b|Remove-Item")


WINDOWS = APPLY[2]
DIRTY = """<startup>
  <perform class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="home:hart/jmri/layouts/hart/scripts/apply_maintain_mqtt.py" type="ScriptFile"/>
  <perform class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/panel_status.py" type="ScriptFile"/>
</startup>
"""


class WindowsStartUpStrip(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WINDOWS.read_text(encoding="utf-8")

    def test_every_per_computer_profile_is_stripped_too(self) -> None:
        block = self.text[self.text.index("$retiredStartup = "):]
        block = block[:block.index("Set-Content")]
        self.assertIn("profile\\profile.xml", block)
        self.assertRegex(block, r"Get-ChildItem \(Join-Path \$r 'profile'\) -Directory")
        self.assertIn("Join-Path $_.FullName 'profile.xml'", block)

    def test_the_pattern_removes_only_the_retired_entry(self) -> None:
        found = re.search(r"\$retiredStartup = @\(([^)]*)\)", self.text)
        assert found is not None, "no $retiredStartup list"
        names = found.group(1)
        self.assertEqual(sorted(re.findall(r"'([^']+)'", names)), sorted(STARTUP_STRIP))
        self.assertIn("[regex]::Replace($txt, ($retiredEntry -f [regex]::Escape($name)), '')", self.text)
        entry = re.search(r"^\$retiredEntry = '([^']+)'$", self.text, re.MULTILINE)
        assert entry is not None, "no $retiredEntry pattern"
        # the same file name inside a longer one, or with more after it, is another script and stays
        kept = ['  <perform class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" '
                f'name="{name}" type="ScriptFile"/>'
                for name in ("preference:jython/old_apply_maintain_mqtt.py", "C:\\jython\\apply_maintain_mqtt.py.bak",
                             "xprepare_nx_sml_paths.py")]
        dirty = DIRTY.replace("</startup>", "\n".join(kept) + "\n</startup>")
        dirty = dirty.replace("</startup>", '  <perform class="jmri.util.startup.configurexml.PerformScriptModelXml" '
                              'name="C:\\jython\\prepare_nx_sml_paths.py" type="ScriptFile"/>\n</startup>')
        out = dirty
        for name in STARTUP_STRIP:
            # .NET -f fills {0}; the pattern uses no other braces
            out = re.sub(entry.group(1).replace("{0}", re.escape(name)), "", out)
        self.assertEqual(out.splitlines(), [line for line in dirty.splitlines()
                                            if "scripts/apply_maintain_mqtt.py" not in line
                                            and "jython\\prepare_nx_sml_paths.py" not in line])
        self.assertIn("panel_status.py", out)
        self.assertEqual(out.count("<perform"), 1 + len(kept))


if __name__ == "__main__":
    unittest.main()
