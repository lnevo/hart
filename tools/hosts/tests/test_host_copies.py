"""Copies of the host defaults that cannot read tools/env/defaults.env must match it.

The Windows PowerShell scripts and the JMRI operations settings run on a host without
this repo's env, so they keep their own literal. This test is what keeps each one equal
to tools/env/defaults.env; change the value there and here fails until the copy follows.
No network: it only reads files.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
DEFAULTS_ENV = ROOT / "tools/env/defaults.env"


def defaults() -> dict[str, str]:
    values = {}
    for line in DEFAULTS_ENV.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def one(pattern: str, rel: str) -> str:
    text = (ROOT / rel).read_text(encoding="utf-8")
    found = re.findall(pattern, text, flags=re.MULTILINE)
    if len(found) != 1:
        raise AssertionError(f"{rel}: expected one match for {pattern!r}, found {len(found)}")
    return found[0]


class HostCopiesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.d = defaults()
        self.pi_ip = self.d["HART_MQTT_BROKER"]

    def test_windows_broker(self) -> None:
        got = one(r"^\$Broker = '([^']+)'", "tools/hosts/windows/patch_windows_mqtt.ps1")
        self.assertEqual(got, self.d["HART_MQTT_BROKER"])

    def test_windows_pi_web_host(self) -> None:
        got = one(r"^\$PiHost = '([^']+)'", "tools/hosts/windows/apply_hart_package_local.ps1")
        self.assertEqual(got, self.d["HART_PI_WEB_HOST"])

    def test_jmri_ops_settings_url(self) -> None:
        got = one(r'"url": "([^"]+)"', "jmri/layouts/hart/data/sts_jmri_ops_settings.json")
        want = urlsplit(self.d["HART_JMRI_JSON"])
        self.assertEqual(urlsplit(got).netloc, want.netloc)

    def test_card_pipeline_defaults(self) -> None:
        rel = "ops/hart-ops/card_pipeline/cars.py"
        self.assertEqual(one(r'environ\.get\("HART_PI_SSH", "([^"]+)"\)', rel), self.d["HART_PI_SSH"])
        self.assertEqual(one(r'environ\.get\("HART_PI_USERFILES", "([^"]+)"\)', rel),
                         self.d["HART_PI_USERFILES"])

    def test_host_side_files_name_only_the_pi_address(self) -> None:
        """Any 10.0.0.x address in the files that ship to the hosts is the Pi's."""
        for folder in ("tools/hosts/windows", "tools/hosts/pi", "ops/packages"):
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or path.suffix in (".png", ".jpg", ".gif", ".zip", ".jar"):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for ip in re.findall(r"\b10\.0\.0\.\d+\b", text):
                    self.assertEqual(ip, self.pi_ip, f"{path.relative_to(ROOT)}: {ip}")


if __name__ == "__main__":
    unittest.main()
