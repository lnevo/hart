"""The three apply paths (Mac, Pi, Windows) install what the package ships and delete nothing by a retired
name: the hosts hold none of these files, so a deploy has nothing of them to clean up. The one exception is
the Start Up entries of three retired scripts, which an old profile.xml can still hold (a Windows per-computer
profile did on 2026-11-26): each apply path strips them, and Windows covers every profile\<node id>\profile.xml.

The stock xml/signals/C&O-1980 of the JMRI install is never removed either; its name is in the list so no
apply path deletes it."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APPLY = (
    ROOT / "tools/hosts/deploy/ship_mac.sh",
    ROOT / "tools/hosts/pi/apply_hart_package_local.sh",
    ROOT / "tools/hosts/windows/apply_hart_package_local.ps1",
)
STARTUP_STRIP = ("apply_maintain_mqtt.py", "apply_mqtt_retain_at_startup.py", "prepare_nx_sml_paths.py")
RETIRED = (
    "hart_dispatcher_startup.py", "patch_dispatcher_facing.py",
    "sync_turnout_buttons.py", "sync_yard_ladder_buttons.py", "apply_dispatcher_roster_profiles.py",
    "SetBlockPreviewValues.py", "sync_layout_button.py", "mqtt_signalhead_publisher.py",
    "linear5_panel_bg.jpg",
    "cats-masts", "hart-aar", "C&O-1980", "install_cats_masts.ps1", "HART_Master", "launch_hart_master",
)


class NoRetiredNames(unittest.TestCase):
    def test_no_apply_path_names_a_retired_file(self) -> None:
        for path in APPLY:
            text = path.read_text(encoding="utf-8")
            for name in RETIRED:
                with self.subTest(script=path.name, name=name):
                    self.assertNotIn(name, text)
            with self.subTest(script=path.name, name="jmri patches"):
                self.assertNotRegex(text, r"tools[/\\]jmri[/\\]patches")

    def test_start_up_names_appear_only_to_strip_them(self) -> None:
        for path in APPLY:
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
        names = re.search(r"\$retiredStartup = @\(([^)]*)\)", self.text).group(1)
        self.assertEqual(sorted(re.findall(r"'([^']+)'", names)), sorted(STARTUP_STRIP))
        pattern = re.search(r"\[regex\]::Replace\(\$txt, \('([^']+)' \+ \[regex\]::Escape\(\$name\) \+ '([^']+)'\)",
                            self.text)
        out = DIRTY
        for name in STARTUP_STRIP:
            out = re.sub(pattern.group(1) + re.escape(name) + pattern.group(2), "", out)
        self.assertNotIn("apply_maintain_mqtt.py", out)
        self.assertIn("panel_status.py", out)
        self.assertEqual(out.count("<perform"), 1)


if __name__ == "__main__":
    unittest.main()
