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

    def test_repeated_click_needs_a_new_sequence(self):
        self.request(1, "track/sensor/405 ACTIVE")
        self.request(1, "track/sensor/405 ACTIVE")  # same value: JMRI fires no change
        self.request(2, "track/sensor/405 ACTIVE")
        self.assertEqual(len(self.sent), 2)

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
