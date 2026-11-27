"""Copies of the host defaults that cannot read tools/env/defaults.env must match it.

The Windows PowerShell scripts and the JMRI operations settings run on a host without
this repo's env, so they keep their own literal. This test is what keeps each one equal
to tools/env/defaults.env; change the value there and here fails until the copy follows.

The card pipeline is imported and load_env.sh sourced with the host variables unset, so
those tests check the default each one uses. The PowerShell scripts do not run here and
launch_cats.sh starts CATS, so for those the test reads the one assignment. No network.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
DEFAULTS_ENV = ROOT / "tools/env/defaults.env"
LOAD_ENV = ROOT / "tools/env/load_env.sh"
CARD_PIPELINE = ROOT / "ops/hart-ops/card_pipeline"


sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib.hosts import read_env_file  # noqa: E402


def defaults() -> dict[str, str]:
    """defaults.env as hartlib reads it, the same parser the Python tools use."""
    return read_env_file(DEFAULTS_ENV)


def bare_env() -> dict[str, str]:
    """This process's environment without the host settings, and with no tools/env/hart.env to read."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HART_")}
    env["HART_ENV_FILE"] = str(ROOT / "tools/env/no-such-hart.env")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run(cmd: list[str], cwd: Path = ROOT) -> list[str]:
    """The lines `cmd` prints, run in bare_env; a failure names the command and its stderr."""
    done = subprocess.run(cmd, cwd=cwd, env=bare_env(), capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise AssertionError(f"{cmd[0]} exited {done.returncode}: {done.stderr.strip()}")
    return done.stdout.splitlines()


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
        settings = json.loads((ROOT / "jmri/layouts/hart/data/sts_jmri_ops_settings.json").read_text(encoding="utf-8"))
        want = urlsplit(self.d["HART_JMRI_JSON"])
        self.assertEqual(urlsplit(settings["connection"]["url"]).netloc, want.netloc)

    def test_card_pipeline_defaults(self) -> None:
        got = run([sys.executable, "-c", "import cars; print(cars.PI_HOST); print(cars.PI_OPS_DIR)"],
                  cwd=CARD_PIPELINE)
        self.assertEqual(got, [self.d["HART_PI_SSH"], f"{self.d['HART_PI_USERFILES']}/operations"])

    def test_pi_launch_cats_profile(self) -> None:
        """The Pi's launch_cats.sh runs without load_env.sh; its default profile is load_env's HART_PI_PROFILE."""
        got = one(r'^JMRI_PROFILE="\$\{JMRI_PROFILE:-([^}]+)\}"$', "tools/hosts/pi/launch_cats.sh")
        want = run(["bash", "-c", f'source "{LOAD_ENV}" && echo "$HART_PI_PROFILE"'])
        self.assertEqual([got], want)

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
