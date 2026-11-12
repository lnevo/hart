"""mimic_relay.py in the JMRI fake: what a memory request publishes, and what it refuses."""
from __future__ import annotations

import unittest
from pathlib import Path

from jmri_fake import Layout, load_script, running

SCRIPT = Path(__file__).resolve().parents[1] / "mimic_relay.py"


class MimicRelay(unittest.TestCase):
    def setUp(self):
        self.layout = Layout()
        self.env = load_script(SCRIPT, self.layout)
        self.memory = self.layout.memories.getMemory("IMHART_MIMIC")
        self.sent = self.layout.adapter.published

    def request(self, seq, *lines):
        with running(self.layout):
            self.memory.setValue("\n".join([str(seq), *lines]))

    def test_install_provides_the_memory(self):
        self.assertIsNotNone(self.memory)
        self.assertEqual(self.memory.getUserName(), "Mimic relay")
        self.assertEqual(len(self.memory.listeners), 1)

    def test_stored_memory_is_reused_not_recreated(self):
        layout = Layout()
        stored = layout.memories.newMemory("IMHART_MIMIC", "Mimic relay (stored)")
        stored.setValue("ack 9")
        load_script(SCRIPT, layout)
        memory = layout.memories.getMemory("IMHART_MIMIC")
        self.assertIs(memory, stored)
        self.assertEqual(memory.getUserName(), "Mimic relay (stored)")
        self.assertEqual(memory.getValue(), "ack 9")
        self.assertEqual(len(memory.listeners), 1)

    def test_rerun_keeps_one_listener(self):
        load_script(SCRIPT, self.layout)
        self.assertEqual(len(self.memory.listeners), 1)

    def test_publishes_lcos_feedback_retained(self):
        self.request(1, "track/sensor/470 INACTIVE", "track/sensor/471 ACTIVE", "track/turnout/408 THROWN")
        self.assertEqual(
            self.sent,
            [
                ("track/sensor/470", "INACTIVE", True),
                ("track/sensor/471", "ACTIVE", True),
                ("track/turnout/408", "THROWN", True),
            ],
        )

    def test_never_publishes_commands_or_other_topics(self):
        self.request(
            1,
            "track/cmd/turnout/408 THROWN",
            "track/signalhead/432 Red",
            "track/bridge/cmd PING",
            "track/sensor/470 THROWN",
            "track/turnout/408 ACTIVE",
            "track/sensor/abc ACTIVE",
            "track/sensor/470/x ACTIVE",
            "track/sensor/470 ACTIVE extra",
        )
        self.assertEqual(self.sent, [])

    def test_mixed_request_keeps_only_valid_lines(self):
        self.request(7, "track/cmd/turnout/1 CLOSED", "track/sensor/405 ACTIVE")
        self.assertEqual(self.sent, [("track/sensor/405", "ACTIVE", True)])

    def test_sequence_line_alone_publishes_nothing(self):
        self.request(3)
        self.assertEqual(self.sent, [])

    def test_every_request_is_acked(self):
        self.request(41, "track/sensor/405 ACTIVE")
        self.assertEqual(self.memory.getValue(), "ack 41")
        self.request(42, "track/cmd/turnout/1 THROWN")  # refused lines are still answered
        self.assertEqual(self.memory.getValue(), "ack 42")
        self.assertEqual(len(self.sent), 1)

    def test_ping_is_acked_and_publishes_nothing(self):
        self.request(9, "ping")
        self.assertEqual(self.memory.getValue(), "ack 9")
        self.assertEqual(self.sent, [])

    def test_a_stored_click_is_never_left_in_the_memory(self):
        self.request(5, "track/sensor/405 ACTIVE", "track/turnout/408 THROWN")
        self.assertNotIn("track/", self.memory.getValue())

    def test_values_that_are_not_requests_are_ignored(self):
        with running(self.layout):
            self.memory.setValue("track/sensor/405 ACTIVE")  # no sequence line
            self.memory.setValue("ack 3")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.memory.getValue(), "ack 3")

    def test_non_ascii_text_is_dropped_not_raised(self):
        self.request(6, "track/sensor/405 ACTIVE —", "café", "track/sensor/406 ACTIVE")
        self.assertEqual(self.sent, [("track/sensor/406", "ACTIVE", True)])
        self.assertEqual(self.memory.getValue(), "ack 6")

    def test_reload_does_not_double_publish(self):
        load_script(SCRIPT, self.layout)
        self.assertEqual(len(self.memory.listeners), 1)
        self.request(1, "track/sensor/405 ACTIVE")
        self.assertEqual(len(self.sent), 1)

    def test_line_limit(self):
        lines = ["track/sensor/%d INACTIVE" % n for n in range(600)]
        self.request(1, *lines)
        self.assertEqual(len(self.sent), self.env["MAX_LINES"])

    def test_no_mqtt_connection_is_quiet(self):
        layout = Layout(mqtt=False)
        load_script(SCRIPT, layout)
        with running(layout):
            layout.memories.getMemory("IMHART_MIMIC").setValue("1\ntrack/sensor/405 ACTIVE")
        self.assertEqual(layout.adapter.published, [])


if __name__ == "__main__":
    unittest.main()
