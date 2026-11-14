"""The Mac MQTT scripts take the broker from hartlib.hosts, not a literal.

The lookup order itself is tested in tools/hartlib/tests/test_hosts.py.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

SCRIPTS = (
    "jmri/layouts/hart/scripts/seed_default_thrown_turnouts.py",
    "tools/mqtt/sync_mqtt_turnouts_from_fb.py",
    "tools/mqtt/clear_mqtt_cmd_sensor_retain.py",
    "tools/mqtt-mimic/lcos_mqtt_mimic.py",
    "tools/mqtt-mimic/sim_hart_train_mqtt.py",
    "tools/mqtt-mimic/qa/run_native_sml_qa.py",
)


class ScriptsUseHelperTest(unittest.TestCase):
    def test_no_literal_pi_address_left(self):
        for rel in SCRIPTS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertTrue("hartlib" in text, rel)
            self.assertIsNone(re.search(r"10\.0\.0\.150", text), rel)
            self.assertNotIn('environ.get("MQTT_HOST"', text, rel)


if __name__ == "__main__":
    unittest.main()
