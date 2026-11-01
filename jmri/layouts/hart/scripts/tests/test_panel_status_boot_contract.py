from __future__ import annotations

import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


class SyncLayoutButtonBootContractTest(unittest.TestCase):
    def test_boot_does_not_paint_or_command_plant_turnouts(self) -> None:
        src = (SCRIPTS / "panel_status.py").read_text(encoding="utf-8")
        self.assertIn('("IT:HART:YL:R1", (("M2T1211", CLOSED), ("M2T1213", CLOSED)))', src)
        self.assertIn("route.setEnabled(False)", src)
        self.assertIn("_paint_indicators_without_commanding", src)
        self.assertNotIn("setCommandedState(", src)
        self.assertIn("TRACK_POWER_SENSOR", src)
        self.assertIn("toggle_track_power", src)
        self.assertIn("_sync_track_power_sensor", src)
        self.assertIn("Track Power", src)
        self.assertNotIn("apply_maintain_mqtt", src)
        self.assertNotIn("_reload_mqtt_retain", src)


if __name__ == "__main__":
    unittest.main()
