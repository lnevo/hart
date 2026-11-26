"""The three apply paths (Mac, Pi, Windows) install what the package ships and delete nothing by a retired
name: the hosts hold none of these files, so a deploy has nothing of them to clean up.

The stock xml/signals/C&O-1980 of the JMRI install is never removed either; its name is in the list so no
apply path deletes it."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APPLY = (
    ROOT / "tools/hosts/deploy/ship_mac.sh",
    ROOT / "tools/hosts/pi/apply_hart_package_local.sh",
    ROOT / "tools/hosts/windows/apply_hart_package_local.ps1",
)
RETIRED = (
    "hart_dispatcher_startup.py", "patch_dispatcher_facing.py", "prepare_nx_sml_paths.py",
    "sync_turnout_buttons.py", "sync_yard_ladder_buttons.py", "apply_dispatcher_roster_profiles.py",
    "SetBlockPreviewValues.py", "sync_layout_button.py", "mqtt_signalhead_publisher.py",
    "apply_maintain_mqtt.py", "apply_mqtt_retain_at_startup.py", "linear5_panel_bg.jpg",
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


if __name__ == "__main__":
    unittest.main()
