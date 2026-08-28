from __future__ import annotations

import csv
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLISHER = ROOT / "jmri/scripts/mqtt_signalhead_publisher.py"
WIRING = ROOT / "cats/data/signal_wiring.csv"
BUILD = ROOT / "cats/scripts/build_hart_signal_heads.py"


def load_build():
    spec = importlib.util.spec_from_file_location("build_hart_signal_heads", BUILD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MqttSignalheadPublisherTest(unittest.TestCase):
    def test_uses_jmri_mqtt_not_mosquitto(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn("MqttSystemConnectionMemo", text)
        self.assertIn("getMqttAdapter", text)
        self.assertIn("Aspect", text)
        self.assertIn("track/bridge/sml_mode", text)
        self.assertIn("setAppearance", text)
        self.assertIn("Unheld", text)
        self.assertNotIn("mosquitto", text.lower())
        self.assertNotIn("subprocess", text)
        self.assertNotIn("import socket", text)

    def test_global_disable_does_not_unheld_from_checkbox_and_button(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn("SUPPRESS_SML_DURING_HANDOFF = True", text)
        self.assertIn("if self._busy or self._boot_pending:", text)
        self.assertIn("Always mute checkbox listeners around bulk uncheck", text)
        off = text.index("def _apply_global_disabled")
        chunk = text[off : text.index("def _hand_off_disabled")]
        self.assertLess(
            chunk.index("self._suppress_sml = True"),
            chunk.index("_set_all_digicon_sml_destinations(False)"),
        )
        self.assertIn("_publish_unheld(head)", chunk)

    def test_head_names_match_wiring_csv(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        begin = text.index("# HEAD_NAMES_BEGIN")
        end = text.index("# HEAD_NAMES_END")
        block = text[begin:end]
        listed = [
            line.strip().strip(",").strip("'").strip('"')
            for line in block.splitlines()
            if line.strip().startswith("'IH") or line.strip().startswith('"IH')
        ]
        with WIRING.open(newline="", encoding="utf-8") as handle:
            csv_names = [row["system_name"] for row in csv.DictReader(handle)]
        self.assertEqual(listed, csv_names)

    def test_write_publisher_preserves_script(self) -> None:
        module = load_build()
        original = PUBLISHER.read_text(encoding="utf-8")
        self.addCleanup(PUBLISHER.write_text, original, "utf-8")
        marker = "# KEEP_ME_SENTINEL"
        PUBLISHER.write_text(original.replace("TOPIC_PREFIX", marker, 1), encoding="utf-8")
        module.write_publisher([{"system_name": "IH999"}])
        updated = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn(marker, updated)
        self.assertIn("'IH999'", updated)
        self.assertNotIn("mosquitto", updated.lower())


if __name__ == "__main__":
    unittest.main()
