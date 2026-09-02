from __future__ import annotations

import ast
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


class SyncLayoutButtonBootContractTest(unittest.TestCase):
    def test_boot_reload_skips_plant_turnouts(self) -> None:
        src = (SCRIPTS / "sync_layout_button.py").read_text(encoding="utf-8")
        self.assertIn("paint_turnouts=False", src)
        self.assertIn('("IT:HART:YL:R1", (("M2T1211", CLOSED), ("M2T1213", CLOSED)))', src)
        self.assertIn("unknown_sensors_only=True", src)
        self.assertIn("route.setEnabled(False)", src)
        self.assertIn("_paint_indicators_without_commanding", src)
        self.assertNotIn("setCommandedState(", src)
        self.assertIn("TRACK_POWER_SENSOR", src)
        self.assertIn("toggle_track_power", src)
        self.assertIn("_sync_track_power_sensor", src)
        self.assertIn("Track Power", src)
        boot = src.split("def _reload_mqtt_retain_at_boot")[1].split("def _arm_listeners")[0]
        self.assertNotIn("turnout_delay_ms=0,\n            settle_secs=0,\n            log_prefix=", boot)

    def test_apply_turnout_does_not_call_new_known_state(self) -> None:
        src = (SCRIPTS / "apply_maintain_mqtt.py").read_text(encoding="utf-8")
        start = src.index("def _apply_turnout")
        rest = src[start + 1 :]
        end = rest.index("\ndef ")
        body = src[start : start + 1 + end]
        self.assertNotIn(".newKnownState(", body)
        self.assertNotIn("provideTurnout", body)
        self.assertIn("setInitialKnownStateFromFeedback", body)

    def test_reload_mqtt_retain_accepts_sensor_only(self) -> None:
        src = (SCRIPTS / "apply_maintain_mqtt.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "reload_mqtt_retain":
                fn = node
                break
        self.assertIsNotNone(fn)
        names = [a.arg for a in fn.args.args]
        self.assertIn("paint_turnouts", names)
        self.assertIn("unknown_sensors_only", names)


if __name__ == "__main__":
    unittest.main()
