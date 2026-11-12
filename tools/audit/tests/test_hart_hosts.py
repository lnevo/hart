"""One broker setting for the Mac tools: hart_hosts lookup order and the scripts that use it."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/ops/lib"))

import hart_hosts  # noqa: E402

NO_FILE: dict = {}

SCRIPTS = (
    "jmri/layouts/hart/scripts/seed_default_thrown_turnouts.py",
    "tools/mqtt/sync_mqtt_turnouts_from_fb.py",
    "tools/mqtt/clear_mqtt_cmd_sensor_retain.py",
    "tools/mqtt-mimic/lcos_mqtt_mimic.py",
    "tools/mqtt-mimic/sim_hart_train_mqtt.py",
    "tools/mqtt-mimic/qa/run_native_sml_qa.py",
)


class LookupTest(unittest.TestCase):
    def test_defaults_to_the_pi(self):
        self.assertEqual(hart_hosts.mqtt_broker({}, NO_FILE), "10.0.0.150")
        self.assertEqual(hart_hosts.mqtt_port({}, NO_FILE), 1883)
        self.assertEqual(hart_hosts.jmri_json_url({}, NO_FILE), "http://10.0.0.150:12080/json")

    def test_new_name_beats_old_names(self):
        env = {"HART_MQTT_BROKER": "a.example.invalid", "MQTT_HOST": "b.example.invalid",
               "HART_MQTT_HOST": "c.example.invalid"}
        self.assertEqual(hart_hosts.mqtt_broker(env, NO_FILE), "a.example.invalid")

    def test_old_names_still_honoured(self):
        self.assertEqual(hart_hosts.mqtt_broker({"MQTT_HOST": "b.example.invalid"}, NO_FILE),
                         "b.example.invalid")
        self.assertEqual(hart_hosts.mqtt_broker({"HART_MQTT_HOST": "c.example.invalid"}, NO_FILE),
                         "c.example.invalid")
        self.assertEqual(
            hart_hosts.jmri_json_url({"JMRI_JSON": "http://j.example.invalid:12080/json/"}, NO_FILE),
            "http://j.example.invalid:12080/json")

    def test_blank_value_is_unset(self):
        self.assertEqual(hart_hosts.mqtt_broker({"HART_MQTT_BROKER": "  "}, NO_FILE), "10.0.0.150")

    def test_environment_beats_env_file(self):
        file_values = {"HART_MQTT_BROKER": "file.example.invalid"}
        self.assertEqual(hart_hosts.mqtt_broker({}, file_values), "file.example.invalid")
        self.assertEqual(hart_hosts.mqtt_broker({"MQTT_HOST": "env.example.invalid"}, file_values),
                         "env.example.invalid")

    def test_bad_port_stops(self):
        with self.assertRaises(SystemExit):
            hart_hosts.mqtt_port({"HART_MQTT_PORT": "x"}, NO_FILE)


class EnvFileTest(unittest.TestCase):
    def test_reads_the_example_format(self):
        example = (ROOT / "tools/env/hart.env.example").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hart.env"
            path.write_text(example.replace("10.0.0.150", "file.example.invalid", 1) + "\nexport X='q'\n",
                            encoding="utf-8")
            values = hart_hosts.read_env_file(path)
        self.assertEqual(values["HART_MQTT_BROKER"], "file.example.invalid")
        self.assertEqual(values["HART_MQTT_PORT"], "1883")
        self.assertEqual(values["X"], "q")
        self.assertNotIn("# HART_REPO_ROOT", values)

    def test_reads_like_source(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hart.env"
            path.write_text(
                "HART_MQTT_BROKER=b.example.invalid\n"
                "HART_JMRI_JSON=http://${HART_MQTT_BROKER}:12080/json  # comment\n"
                'QUOTED="a # b"\n'
                "LITERAL='$HART_MQTT_BROKER'\n",
                encoding="utf-8")
            values = hart_hosts.read_env_file(path)
        self.assertEqual(values["HART_JMRI_JSON"], "http://b.example.invalid:12080/json")
        self.assertEqual(values["QUOTED"], "a # b")
        self.assertEqual(values["LITERAL"], "$HART_MQTT_BROKER")

    def test_path_follows_repo_root(self):
        saved = {k: os.environ.pop(k, None) for k in ("HART_ENV_FILE", "HART_REPO_ROOT")}
        try:
            self.assertEqual(hart_hosts.env_file_path(), ROOT / "tools/env/hart.env")
            os.environ["HART_REPO_ROOT"] = "/x"
            self.assertEqual(hart_hosts.env_file_path(), Path("/x/tools/env/hart.env"))
            os.environ["HART_ENV_FILE"] = "/y/h.env"
            self.assertEqual(hart_hosts.env_file_path(), Path("/y/h.env"))
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_missing_file_is_empty(self):
        self.assertEqual(hart_hosts.read_env_file(Path("/nonexistent/hart.env")), {})


class ScriptsUseHelperTest(unittest.TestCase):
    def test_no_literal_pi_address_left(self):
        for rel in SCRIPTS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("hart_hosts", text, rel)
            self.assertIsNone(re.search(r"10\.0\.0\.150", text), rel)
            self.assertNotIn('environ.get("MQTT_HOST"', text, rel)


if __name__ == "__main__":
    unittest.main()
