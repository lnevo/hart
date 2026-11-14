"""Shell scripts read host settings from load_env.sh in the same order as hartlib/hosts.py.

Order: the environment, then hart.env, then the default. Older names follow the new one.
No ssh, no MQTT: the shell only prints what it resolved.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOAD_ENV = ROOT / "tools/env/load_env.sh"
EXAMPLE = ROOT / "tools/env/hart.env.example"
NAMES = ("HART_MQTT_BROKER", "HART_MQTT_PORT", "HART_JMRI_JSON", "HART_PI_SSH", "HART_PI_USERFILES",
         "HART_PI_WEB_HOST", "HART_WIN_SSH", "HART_WIN_SSH_PORT", "HART_WIN_USERFILES")
DEFAULTS = {
    "HART_MQTT_BROKER": "10.0.0.150",
    "HART_MQTT_PORT": "1883",
    "HART_JMRI_JSON": "http://10.0.0.150:12080/json",
    "HART_PI_SSH": "pi",
    "HART_PI_USERFILES": "/home/pi/JMRI_UserFiles",
    "HART_PI_WEB_HOST": "RPi-JMRI.local",
    "HART_WIN_SSH": "lnevo@minipc-e5h6x.local",
    "HART_WIN_SSH_PORT": "2222",
    "HART_WIN_USERFILES": "C:/Users/lnevo/JMRI_UserFiles",
}
# Every name load_env.sh or hartlib/hosts.py reads, so the caller's environment cannot leak in.
CLEAR = NAMES + ("MQTT_HOST", "HART_MQTT_HOST", "JMRI_JSON", "PI_HOST", "HART_ENV_FILE", "HART_REPO_ROOT")


def load_hartlib_hosts():
    path = ROOT / "tools/hartlib/src/hartlib/hosts.py"
    spec = importlib.util.spec_from_file_location("hartlib_hosts_for_shell_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def resolve(env: dict[str, str], file_text: str | None) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / "hart.env"
        if file_text is not None:
            env_file.write_text(file_text, encoding="utf-8")
        base = {k: v for k, v in os.environ.items() if k not in CLEAR}
        base.update(env, HART_ENV_FILE=str(env_file))
        script = f'set -euo pipefail; source "{LOAD_ENV}"; ' + "; ".join(
            f'printf "%s=%s\\n" {n} "${{{n}}}"' for n in NAMES)
        for shell in ("/bin/bash", "bash"):
            done = subprocess.run([shell, "-c", script], env=base, capture_output=True, text=True,
                                  check=True)
            values = dict(line.split("=", 1) for line in done.stdout.splitlines())
        return values


class Defaults(unittest.TestCase):
    def test_no_settings_gives_todays_values(self) -> None:
        self.assertEqual(resolve({}, None), DEFAULTS)

    def test_example_file_changes_nothing(self) -> None:
        self.assertEqual(resolve({}, EXAMPLE.read_text(encoding="utf-8")), DEFAULTS)

    def test_example_documents_every_host_setting(self) -> None:
        text = EXAMPLE.read_text(encoding="utf-8")
        for name in NAMES:
            self.assertIn(name, text)


class Order(unittest.TestCase):
    def test_environment_beats_file(self) -> None:
        got = resolve({"HART_PI_SSH": "envpi", "HART_WIN_SSH_PORT": "22"},
                      "HART_PI_SSH=filepi\nHART_WIN_SSH_PORT=2200\nHART_WIN_SSH=me@filewin\n")
        self.assertEqual(got["HART_PI_SSH"], "envpi")
        self.assertEqual(got["HART_WIN_SSH_PORT"], "22")
        self.assertEqual(got["HART_WIN_SSH"], "me@filewin")

    def test_stale_pi_host_never_moves_the_deploy(self) -> None:
        """Deploy and pi_quit/pi_start never read PI_HOST; an exported one must not change their target."""
        self.assertEqual(resolve({"PI_HOST": "oldpi"}, None)["HART_PI_SSH"], "pi")
        self.assertEqual(resolve({"PI_HOST": "oldpi"}, "HART_PI_SSH=filepi\n")["HART_PI_SSH"], "filepi")

    def test_sts_helpers_still_put_pi_host_first(self) -> None:
        for name in ("pi_docker_static.sh", "pi_sts_update.sh", "pi_sts_pull_backups.sh"):
            text = (ROOT / "tools/hosts" / name).read_text(encoding="utf-8")
            self.assertIn('HOST="${PI_HOST:-$HART_PI_SSH}"', text, name)
        for name in ("sync_hart_package.sh", "pi_quit_panelpro.sh", "pi_start_panelpro.sh"):
            self.assertNotIn("PI_HOST:-", (ROOT / "tools/hosts" / name).read_text(encoding="utf-8"), name)

    def test_hart_env_with_forward_reference_under_set_u(self) -> None:
        """A hart.env line naming a variable set only later must not abort a set -u caller."""
        got = resolve({}, "STS_BACKUPS_DIR=$STS_DATA_ROOT/backups\nHART_PI_SSH=filepi\n")
        self.assertEqual(got["HART_PI_SSH"], "filepi")

    def test_nounset_is_restored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "hart.env"
            env_file.write_text("X=$UNSET_LATER\n", encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k not in CLEAR}
            env["HART_ENV_FILE"] = str(env_file)
            done = subprocess.run(["bash", "-c", f'set -u; source "{LOAD_ENV}"; echo "[$-]"'],
                                  env=env, capture_output=True, text=True, check=True)
            self.assertIn("u", done.stdout.strip().strip("[]"))

    def test_same_answers_as_hartlib_hosts(self) -> None:
        hosts = load_hartlib_hosts()
        cases = [
            ({}, None),
            ({}, "HART_MQTT_BROKER=192.0.2.1   # comment\nHART_MQTT_PORT=1884\n"),
            ({"MQTT_HOST": "192.0.2.9"}, "HART_MQTT_BROKER=192.0.2.1\n"),
            ({"HART_MQTT_HOST": "192.0.2.8"}, None),
            ({"HART_MQTT_BROKER": "192.0.2.7", "MQTT_HOST": "192.0.2.9"}, None),
            ({}, "MQTT_HOST=192.0.2.5\n"),
            ({"JMRI_JSON": "http://192.0.2.4:12080/json"}, "HART_JMRI_JSON=http://192.0.2.3:12080/json\n"),
            ({"HART_MQTT_PORT": "1885"}, "HART_MQTT_PORT=1886\n"),
        ]
        for env, text in cases:
            with self.subTest(env=env, file=text):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "hart.env"
                    file_values = {}
                    if text is not None:
                        path.write_text(text, encoding="utf-8")
                        file_values = hosts.read_env_file(path)
                    want = {
                        "HART_MQTT_BROKER": hosts.mqtt_broker(env, file_values),
                        "HART_MQTT_PORT": str(hosts.mqtt_port(env, file_values)),
                        "HART_JMRI_JSON": hosts.jmri_json_url(env, file_values),
                    }
                got = resolve(env, text)
                self.assertEqual({k: got[k] for k in want}, want)


class NoHardCodedHosts(unittest.TestCase):
    """Mac-side shell scripts take hosts from load_env.sh, not their own literals."""

    MAC_SIDE = sorted(ROOT.glob("tools/hosts/*.sh")) + [ROOT / "tools/ops/pull_ops.sh"]
    LITERALS = ("minipc-e5h6x", "10.0.0.150", "10.0.0.28", "/home/pi", "C:/Users/lnevo")

    def test_scripts_source_load_env(self) -> None:
        for path in self.MAC_SIDE:
            if path.name in ("pack_roster_stage.sh", "profile_tables_guard.sh"):
                continue  # local packing, and a sourced Mac-only helper: no host
            self.assertIn("load_env.sh", path.read_text(encoding="utf-8"), path.name)

    def test_no_host_literals(self) -> None:
        for path in self.MAC_SIDE:
            text = path.read_text(encoding="utf-8")
            for literal in self.LITERALS:
                self.assertNotIn(literal, text, f"{path.name}: {literal}")

    def test_pi_scripts_use_home(self) -> None:
        for path in sorted((ROOT / "tools/hosts/pi").glob("*.sh")) + [ROOT / "tools/hosts/pi/JMRI_CATS"]:
            lines = [l for l in path.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#")]
            self.assertNotIn("/home/pi", "\n".join(lines), path.name)


if __name__ == "__main__":
    unittest.main()
