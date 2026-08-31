from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLISHER = ROOT / "jmri/scripts/mqtt_signalhead_publisher.py"
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
        self.assertIn("IS:SML_MODE", text)
        self.assertIn("_sync_sml_mode_sensor", text)
        self.assertIn("setAppearance", text)
        self.assertIn("Unheld", text)
        self.assertIn("_warn_if_stored_sml_enabled", text)
        self.assertIn("showMessageDialog", text)
        self.assertIn("Digicon SML stored Enabled", text)
        self.assertIn('_publish_mode("enabling")', text)
        self.assertNotIn("enabled_on_boot", text)
        self.assertIn("_abort_sml_immediate", text)
        self.assertIn("SML_ABORT_RESUME_MS", text)
        self.assertIn('"aborting"', text)
        self.assertIn('"aborted"', text)
        self.assertIn("_schedule_enabled_after_enabling", text)
        self.assertIn("_announce_enabling", text)
        self.assertIn("AbstractShutDownTask", text)
        self.assertIn("_on_jmri_shutdown", text)
        self.assertIn("DigiconSmlQuitTask", text)
        self.assertIn("setDoRun(True)", text)
        self.assertNotIn("MQTT_HEAD_NAMES", text)
        self.assertNotIn("HEAD_NAMES_BEGIN", text)
        self.assertNotIn("\nHEAD_NAMES =", text)
        self.assertIn("DigiconMqttSml()", text)
        self.assertIn("_is_lcos_ih_sys", text)
        self.assertIn("_enroll_packed", text)
        self.assertIn("_packed_is_lcos_signal", text)
        self.assertIn('MAST_TOPIC_PREFIX + "#"', text)
        self.assertIn('TOPIC_PREFIX + "#"', text)
        self.assertNotIn("mosquitto", text.lower())
        self.assertNotIn("subprocess", text)
        self.assertNotIn("import socket", text)

    def test_global_disable_hold_publishes_then_button_unheld(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        self.assertNotIn("SUPPRESS_SML_DURING_HANDOFF", text)
        self.assertIn("if self._busy or self._boot_pending:", text)
        off = text.index("def _apply_global_disabled")
        chunk = text[off : text.index("def _hand_off_disabled")]
        self.assertIn("mast.setHeld(True)", chunk)
        self.assertNotIn("_suppress_sml", chunk)
        self.assertIn("_publish_unheld(head)", chunk)
        on = text[text.index("def _hand_off_enabled") : text.index("def _mast_for_head")]
        self.assertIn("mast.setHeld(True)", on)
        self.assertNotIn("_suppress_sml", on)
        abort = text[
            text.index("def _abort_sml_immediate") : text.index("def _announce_enabling")
        ]
        self.assertIn("self._suppress_sml = True", abort)
        self.assertLess(
            abort.index("self._suppress_sml = True"),
            abort.index("_set_all_digicon_sml_destinations(False)"),
        )
        self.assertNotIn("setHeld", abort)
        self.assertNotIn("_publish_unheld", abort)

    def test_shutdown_hold_release_then_disabled(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        start = text[text.index("def start") : text.index("def _stored_enabled")]
        self.assertIn("_register_shutdown_task()", start)
        self.assertIn("DigiconSmlQuitTask", start)
        quit = text[
            text.index("def _on_jmri_shutdown") : text.index(
                "def _stored_enabled_source_names"
            )
        ]
        self.assertIn("_release_on_quit()", quit)
        self.assertIn("_publish_unheld(head)", quit)
        self.assertLess(quit.index("_publish_unheld"), quit.index('_publish_mode("disabled")'))
        self.assertIn("HOLD_WAIT_MS", quit)
        self.assertIn("self._abort_in_progress", quit)
        self.assertNotIn("_abort_sml_immediate", quit)
        task = text[text.index("class DigiconSmlQuitTask") :]
        self.assertIn("def call(self):", task)
        self.assertLess(task.index("def call(self):"), task.index("def run(self):"))
        self.assertIn("controller._on_jmri_shutdown()", task)
        enable = text[
            text.index("def _enter_enabled") : text.index("def _enter_disabled")
        ]
        self.assertIn("self._shutting_down", enable)

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
        start = text[text.index("def start") : text.index("def _stored_enabled")]
        self.assertIn('_announce_enabling("stored dests")', start)
        self.assertIn("_schedule_enabled_after_enabling", start)
        self.assertNotIn("_abort_sml_immediate()", start)
        off = text.index("def _abort_sml_immediate")
        chunk = text[off : text.index("def _announce_enabling")]
        self.assertIn('_publish_mode("aborting")', chunk)
        self.assertIn("_set_all_digicon_sml_destinations(False)", chunk)
        self.assertIn('_publish_mode("aborted")', chunk)
        self.assertNotIn("_publish_unheld", chunk)
        self.assertNotIn("HOLD_WAIT", chunk)
        enable = text[text.index("def _enter_enabled") : text.index("def _enter_disabled")]
        self.assertIn('_announce_enabling("force override")', enable)
        self.assertIn('result == "force"', enable)
        on_mode = text[text.index("def _on_sml_mode") :]
        self.assertIn("own enabling", on_mode)
        self.assertIn("if self._enabling_originator:", on_mode)
        self.assertIn('_publish_mode("enabling")', text[text.index("def _announce_enabling") :])

    def test_no_static_head_names_list(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        self.assertNotIn("# HEAD_NAMES_BEGIN", text)
        self.assertNotIn("HEAD_NAMES = [", text)
        self.assertIn("LCOS Virtual IH heads", text)
        collect = text[text.index("def _collect_beans") : text.index("def _attach_bean_listeners")]
        self.assertIn("_is_lcos_ih_sys", collect)
        self.assertNotIn("self.wanted", collect)

    def test_write_publisher_checks_dynamic_roster(self) -> None:
        module = load_build()
        original = PUBLISHER.read_text(encoding="utf-8")
        self.addCleanup(PUBLISHER.write_text, original, "utf-8")
        module.write_publisher([{"system_name": "IH999"}])
        updated = PUBLISHER.read_text(encoding="utf-8")
        self.assertEqual(updated, original)
        self.assertNotIn("HEAD_NAMES_BEGIN", updated)
        self.assertNotIn("\nHEAD_NAMES =", updated)
        self.assertNotIn("MQTT_HEAD_NAMES", updated)

    def test_roster_enrolls_from_signalmast_not_signalhead(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        notify = text[text.index("def notifyMqttMessage") :]
        self.assertIn("_enroll_packed(leaf)", notify)
        enroll_at = notify.index("_enroll_packed(leaf)")
        apply_at = notify.index("_apply_mast_payload_to_head(leaf, message)")
        self.assertLess(enroll_at, apply_at)
        self.assertIn("never enroll from signalhead", notify)
        skip = notify.index("never enroll from signalhead")
        self.assertLess(skip, enroll_at)
        self.assertIn("UID 32-47", text)
        self.assertIn("self.mqtt_wanted = set()", text)

    def test_sml_timing_ack_while_taking_or_holding(self) -> None:
        text = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn("HOLD_WAIT_MS = 3000", text)
        self.assertIn("BOOT_MODE_WAIT_MS = 1000", text)
        self.assertIn("SML_ABORT_RESUME_MS = 1000", text)
        self.assertIn("PROBE_WAIT_MS = 1000", text)
        self.assertIn("def _should_ack_sml_alive", text)
        self.assertIn("Thread.sleep(PROBE_WAIT_MS)", text)
        hand = text[text.index("def _hand_off_enabled") : text.index("def _mast_for_head")]
        self.assertIn("self._enabling_originator = True", hand)
        ack = text[
            text.index("def _should_ack_sml_alive") : text.index("def propertyChange")
        ]
        self.assertIn("self._probe_active", ack)
        self.assertIn("self._abort_in_progress", ack)
        self.assertIn("self._enabling_originator", ack)
        self.assertIn("self._global_enabled", ack)
        self.assertNotIn("not self._busy", ack)


if __name__ == "__main__":
    unittest.main()
