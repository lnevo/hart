"""tools/hosts/pi/jmri_profile_match.sh, run in bash against made-up command lines and a fake ps: a profile is
named as a whole word in either form (-Dorg.jmri.profile=, --profile=), a JMRI app naming none counts as on every
profile, and its JMRI app pattern is hartlib's."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "tools/hosts/pi/jmri_profile_match.sh"
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib.tables import _JMRI_PROCESS  # noqa: E402

PANELPRO = "java -Djava.awt.headless=false {word} -cp .:jmri.jar apps.PanelPro.PanelPro"


def bash(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run `script` in bash after sourcing the helper, with `args` as $1...; the bash on PATH (3.2 on the Mac)."""
    return subprocess.run(["bash", "-c", f'set -euo pipefail; source "{HELPER}"; {script}', "test", *args],
                          capture_output=True, text=True, timeout=30, env=env)


def holds(function: str, cmd: str, profile: str = "") -> bool:
    done = bash(f'{function} "$1" "$2"', cmd, profile) if profile else bash(f'{function} "$1"', cmd)
    if done.returncode not in (0, 1):
        raise AssertionError(done.stderr)
    return done.returncode == 0


class NamesProfile(unittest.TestCase):
    def test_either_word_names_the_profile(self) -> None:
        for word in ("-Dorg.jmri.profile=TCS_MQTT.3f32a166", "--profile=TCS_MQTT.3f32a166"):
            with self.subTest(word=word):
                self.assertTrue(holds("jmri_cmd_names_profile", PANELPRO.format(word=word), "TCS_MQTT.3f32a166"))
                self.assertTrue(holds("jmri_cmd_names_profile", f"{word} at the end", "TCS_MQTT.3f32a166"))

    def test_a_name_takes_its_id_and_nothing_that_only_starts_the_same(self) -> None:
        cases = {"TCS_MQTT": True, "TCS_MQTT.3f32a166": True, "TCS_MQTT_test": False, "TCS_MQTT_test.0badf00d": False,
                 "TCS_MQTTX": False, "TCS_MQTT.": False, "TCS_MQTT.3f32-a1": False, "TCS": False}
        for value, want in cases.items():
            with self.subTest(value=value):
                cmd = PANELPRO.format(word=f"-Dorg.jmri.profile={value}")
                self.assertEqual(holds("jmri_cmd_names_profile", cmd, "TCS_MQTT"), want)

    def test_a_full_id_takes_only_that_id(self) -> None:
        for value, want in (("TCS_MQTT.3f32a166", True), ("TCS_MQTT.3f32a166x", False), ("TCS_MQTT", False)):
            with self.subTest(value=value):
                self.assertEqual(holds("jmri_cmd_names_profile", f"--profile={value}", "TCS_MQTT.3f32a166"), want)

    def test_a_path_id_is_taken_literally(self) -> None:
        path = "/tmp/run.x/Rehearsal.jmri"
        self.assertTrue(holds("jmri_cmd_names_profile", f"java -Dorg.jmri.profile={path} apps.PanelPro.PanelPro", path))
        self.assertFalse(holds("jmri_cmd_names_profile", "java -Dorg.jmri.profile=/tmp/runXx/Rehearsal.jmri", path))
        self.assertFalse(holds("jmri_cmd_names_profile", "java -Dorg.jmri.profile=/tmp/*", "/tmp/*x"))

    def test_text_that_is_not_one_of_the_two_words_names_nothing(self) -> None:
        for cmd in ("grep org.jmri.profile=TCS_MQTT log", "x-Dorg.jmri.profile=TCS_MQTT", "-p TCS_MQTT",
                    "--profile TCS_MQTT", ""):
            with self.subTest(cmd=cmd):
                self.assertFalse(holds("jmri_cmd_names_profile", cmd, "TCS_MQTT"))
        self.assertEqual(bash('jmri_cmd_names_profile "$1" ""', "--profile=").returncode, 1)    # no id names nothing


class OnProfile(unittest.TestCase):
    def test_a_jmri_app_naming_no_profile_is_on_every_profile(self) -> None:
        bare = PANELPRO.format(word="")
        self.assertTrue(holds("jmri_cmd_on_profile", bare, "TCS_MQTT"))
        self.assertTrue(holds("jmri_cmd_on_profile", bare, "Rehearsal.0badf00d"))
        self.assertTrue(holds("jmri_cmd_on_profile", "java -cp cats.jar cats.apps.Crandic x.xml", "TCS_MQTT"))

    def test_a_jmri_app_naming_another_profile_is_not(self) -> None:
        self.assertFalse(holds("jmri_cmd_on_profile", PANELPRO.format(word="-Dorg.jmri.profile=TCS_MQTT_test"),
                               "TCS_MQTT"))

    def test_other_programs_are_not_jmri_apps(self) -> None:
        for cmd in ("java -jar sts.jar", "python3 apps.PanelPro.PanelPro.py", "bash -s -- TCS_MQTT"):
            with self.subTest(cmd=cmd):
                self.assertFalse(holds("jmri_cmd_on_profile", cmd, "TCS_MQTT"))

    def test_the_jmri_app_pattern_is_hartlibs(self) -> None:
        self.assertEqual(bash('printf %s "$HART_JMRI_APP"').stdout, _JMRI_PROCESS)


class ProcessList(unittest.TestCase):
    """jmri_profile_pids and jmri_app_running against a fake ps and pgrep on PATH."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.bin = Path(tmp.name)
        self.calls = self.bin / "calls.log"

    def fake(self, name: str, body: str) -> None:
        (self.bin / name).write_text(f'#!/bin/bash\necho "{name} $*" >>"{self.calls}"\n{body}\n', encoding="utf-8")
        (self.bin / name).chmod(0o755)

    def run_helper(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        return bash(script, *args, env={**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}"})

    def test_pids_of_this_users_processes_on_the_profile_in_ps_order(self) -> None:
        self.fake("ps", "printf '%s\\n' '  101 /bin/bash ./cats.csh --profile=TCS_MQTT.3f32a166 CTC.xml' "
                        "'  102 java -Dorg.jmri.profile=TCS_MQTT_test -cp jmri.jar apps.PanelPro.PanelPro' "
                        "'  103 java -Dorg.jmri.profile=TCS_MQTT.3f32a166 -cp jmri.jar cats.apps.Crandic CTC.xml' "
                        "'  104 java -jar sts.jar'")
        done = self.run_helper('jmri_profile_pids "$1"', "TCS_MQTT")
        self.assertEqual((done.returncode, done.stdout.split()), (0, ["101", "103"]), done.stderr)
        uid = str(os.getuid())
        self.assertEqual(self.calls.read_text(encoding="utf-8").split(), ["ps", "-u", uid, "-o", "pid=,args="])

    def test_the_panelpro_jvm_is_picked_over_a_cats_shell_with_a_lower_pid(self) -> None:
        self.fake("ps", "printf '%s\\n' '  101 /bin/bash ./cats.csh --profile=TCS_MQTT.3f32a166 CTC.xml' "
                        "'  102 python3 tool.py' "
                        "'  103 java -Dorg.jmri.profile=TCS_MQTT.3f32a166 -cp jmri.jar apps.PanelPro.PanelPro'")
        done = self.run_helper('jmri_profile_panelpro_pid "$1"', "TCS_MQTT")
        self.assertEqual((done.returncode, done.stdout.split()), (0, ["103"]), done.stderr)
        self.fake("ps", "echo '  101 /bin/bash ./cats.csh --profile=TCS_MQTT.3f32a166 CTC.xml'")
        done = self.run_helper('jmri_profile_panelpro_pid "$1"', "TCS_MQTT")
        self.assertEqual((done.returncode, done.stdout.split()), (0, ["101"]), done.stderr)
        self.fake("ps", "echo '  7 java -Dorg.jmri.profile=Other -cp jmri.jar apps.PanelPro.PanelPro'")
        done = self.run_helper('jmri_profile_panelpro_pid "$1" || echo "rc=$?"', "TCS_MQTT")
        self.assertEqual(done.stdout.split(), ["rc=1"], done.stderr)

    def test_none_on_the_profile_is_exit_1_and_a_failed_ps_is_exit_2(self) -> None:
        self.fake("ps", "echo '  7 java -Dorg.jmri.profile=Other -cp jmri.jar apps.PanelPro.PanelPro'")
        done = self.run_helper('jmri_profile_pids "$1" || echo "rc=$?"', "TCS_MQTT")
        self.assertEqual(done.stdout.split(), ["rc=1"])
        self.fake("ps", "exit 1")
        for function in ("jmri_profile_pids", "jmri_profile_running"):
            with self.subTest(function=function):
                done = self.run_helper(f'{function} "$1" || echo "rc=$?"', "TCS_MQTT")
                self.assertEqual(done.stdout.split(), ["rc=2"])

    def test_any_jmri_app_asks_pgrep_with_hartlibs_pattern(self) -> None:
        for code, want in (("0", "rc=0"), ("1", "rc=1"), ("2", "rc=2")):
            self.fake("pgrep", f"exit {code}")
            with self.subTest(code=code):
                done = self.run_helper('rc=0; jmri_app_running || rc=$?; echo "rc=$rc"')
                self.assertEqual(done.stdout.split(), [want], done.stderr)
        last = self.calls.read_text(encoding="utf-8").splitlines()[-1]
        self.assertEqual(last, f"pgrep -u {os.getuid()} -f {_JMRI_PROCESS}")


if __name__ == "__main__":
    unittest.main()
