"""patch_windows_mqtt.ps1 against a temporary profile tree. Needs pwsh or Windows PowerShell; skips otherwise."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "windows" / "patch_windows_mqtt.ps1"
SHELL = shutil.which("pwsh") or shutil.which("powershell")

MQTT = 'class="jmri.jmrix.mqtt.configurexml.MqttConnectionConfigXml"'
LCC = 'class="jmri.jmrix.openlcb.configurexml.ConnectionConfigXml"'


def _profile(*connections: str) -> str:
    body = "\n".join(f"    {c}" for c in connections)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<profile>\n  <!-- café -->\n  <connections>\n{body}\n  </connections>\n</profile>\n'


@unittest.skipUnless(SHELL, "no PowerShell on this host")
class PatchWindowsMqttTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.profile = self.tmp / "My_JMRI_Railroad.jmri" / "profile"
        (self.profile / "node-a").mkdir(parents=True)

    def _run(self) -> str:
        out = subprocess.run(
            [SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-Root", str(self.tmp)],
            capture_output=True, text=True, check=True,
        )
        return out.stdout

    def test_patches_shared_and_node_profiles_mqtt_only(self):
        shared = self.profile / "profile.xml"
        node = self.profile / "node-a" / "profile.xml"
        shared.write_text(_profile(f'<connection address="192.168.137.2" {MQTT} reconnectMaxAttempts="99"/>'), encoding="utf-8")
        node.write_text(
            _profile(
                f'<connection {MQTT} address="minipc-e5h6x.local" reconnectMaxInterval="60"/>',
                f'<connection {LCC} address="lcc-hub" reconnectMaxAttempts="3" reconnectMaxInterval="30"/>',
            ),
            encoding="utf-8",
        )

        out = self._run()

        self.assertIn("changes=2", out)
        s, n = shared.read_text(encoding="utf-8"), node.read_text(encoding="utf-8")
        self.assertIn('address="10.0.0.150"', s)
        self.assertIn('reconnectMaxAttempts="10"', s)
        self.assertIn(f'<connection {MQTT} address="10.0.0.150" reconnectMaxInterval="5"/>', n)
        # Other connections keep their own address and reconnect settings.
        self.assertIn(f'<connection {LCC} address="lcc-hub" reconnectMaxAttempts="3" reconnectMaxInterval="30"/>', n)
        # UTF-8 text survives, and no BOM is added.
        self.assertIn("café", n)
        self.assertFalse(node.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertTrue((self.profile / "node-a" / "profile.xml.bak_pre_mqtt_fix").exists())

    def test_second_run_changes_nothing(self):
        node = self.profile / "node-a" / "profile.xml"
        node.write_text(_profile(f'<connection address="192.168.137.2" {MQTT}/>'), encoding="utf-8")
        self._run()
        self.assertIn("changes=0", self._run())

    def test_node_folder_without_mqtt_is_quiet(self):
        (self.profile / "node-a" / "profile.xml").write_text(_profile(f'<connection {LCC} address="x"/>'), encoding="utf-8")
        self.assertNotIn("No MQTT", self._run())


if __name__ == "__main__":
    unittest.main()
