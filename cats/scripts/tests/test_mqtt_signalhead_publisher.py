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
        self.assertIn("_warn_if_stored_sml_enabled", text)
        self.assertIn("showMessageDialog", text)
        self.assertIn("Digicon SML stored Enabled", text)
        self.assertIn("enabled_on_boot", text)
        self.assertIn("_abort_sml_immediate", text)
        self.assertIn("SML_ABORT_RESUME_MS", text)
        self.assertIn('"aborting"', text)
        self.assertIn('"aborted"', text)
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

    def test_per_mast_dest_uncheck_unhelds_immediately(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn("def _hand_source_to_field", text)
        self.assertIn("def _hand_source_to_sml", text)
        self.assertIn("def _dest_enable_map", text)
        self.assertIn("mast.setAspect", text)
        self.assertIn("owned[mast] = not on", text)
        self.assertNotIn("owned[mast] = (not self._global_enabled)", text)
        off = text.index("def _on_sml_property")
        chunk = text[off:]
        self.assertIn("if not self._global_enabled:", chunk)
        self.assertIn("_hand_source_to_field(mast)", chunk)
        self.assertIn("_hand_source_to_sml(mast)", chunk)
        self.assertNotIn("last dest is off", chunk)

    def test_boot_abort_unchecks_without_hold_or_unheld(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        off = text.index("def _abort_sml_immediate")
        chunk = text[off : text.index("def _schedule_resume_after_abort")]
        self.assertIn('_publish_mode("aborting")', chunk)
        self.assertIn("_set_all_digicon_sml_destinations(False)", chunk)
        self.assertIn('_publish_mode("aborted")', chunk)
        self.assertNotIn("_publish_unheld", chunk)
        self.assertNotIn("HOLD_WAIT", chunk)
        self.assertIn("from_boot=True", text[text.index("def _schedule_resume_after_abort") :])

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
