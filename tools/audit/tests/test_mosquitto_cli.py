"""mosquitto_cli: a read ends when mosquitto_sub's wait runs out; any other failure is MosquittoError.

Every call passes a fake runner; nothing starts a mosquitto client or reaches a broker.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
import unittest.mock
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/mqtt"))
import mosquitto_cli as mc  # noqa: E402
import turnout_feedback as tf  # noqa: E402


class FakeRunner:
    """Records each command and answers with one fixed result."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.result = (returncode, stdout, stderr)
        self.calls: list[list[str]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(cmd))
        code, out, err = self.result
        return subprocess.CompletedProcess(list(cmd), code, out, err)


class Subscribe(unittest.TestCase):
    def test_the_wait_running_out_ends_the_read_with_what_was_printed(self) -> None:
        run = FakeRunner(mc.TIMED_OUT_STATUS, "track/sensor/1 ACTIVE\ntrack/sensor/2  INACTIVE \n", "Timed out\n")
        got = mc.subscribe("broker", "track/sensor/#", run=run)
        self.assertEqual(got, [mc.Message("track/sensor/1", "ACTIVE"), mc.Message("track/sensor/2", "INACTIVE")])
        self.assertEqual(run.calls[0][0], mc.SUB)
        self.assertIn("track/sensor/#", run.calls[0])

    def test_a_timed_out_line_on_stdout_is_no_message(self) -> None:
        self.assertEqual(mc.parse_messages("Timed out\n\nnospace\n"), [])

    def test_a_connection_failure_is_an_error_not_an_empty_read(self) -> None:
        run = FakeRunner(14, "", "Error: Connection refused\n")
        with self.assertRaisesRegex(mc.MosquittoError, "exited 14: Error: Connection refused"):
            mc.subscribe("broker", "+", run=run)

    def test_count_is_passed_only_when_given(self) -> None:
        run = FakeRunner()
        mc.subscribe("broker", "a", run=run)
        mc.subscribe("broker", "a", count=1, run=run)
        self.assertNotIn("-C", run.calls[0])
        self.assertEqual(run.calls[1][-2:], ["-C", "1"])


class SetRetained(unittest.TestCase):
    def test_a_failure_names_the_topic(self) -> None:
        run = FakeRunner(5, "", "Connection error: not authorised\n")
        with self.assertRaisesRegex(mc.MosquittoError, "junk/topic on broker exited 5: Connection error"):
            mc.set_retained("broker", "junk/topic", None, run=run)
        self.assertEqual(run.calls[0][0], mc.PUB)

    def test_a_failure_with_no_output_still_says_so(self) -> None:
        with self.assertRaisesRegex(mc.MosquittoError, "exited 1: no message"):
            mc.set_retained("broker", "junk/topic", "x", run=FakeRunner(1))

    def test_success_returns_none(self) -> None:
        self.assertIsNone(mc.set_retained("broker", "junk/topic", None, run=FakeRunner()))


class RunCommand(unittest.TestCase):
    def test_a_missing_client_is_an_error(self) -> None:
        with unittest.mock.patch.object(mc.subprocess, "run", side_effect=FileNotFoundError("no such file")), \
                self.assertRaisesRegex(mc.MosquittoError, "could not be started"):
            mc.run_command(["mosquitto_sub"])

    def test_a_network_timeout_is_a_failure_not_the_end_of_a_read(self) -> None:
        with self.assertRaisesRegex(mc.MosquittoError, "exited 14: Error: Connection timed out"):
            mc.subscribe("broker", "track/sensor/#", run=FakeRunner(14, "", "Error: Connection timed out\n"))


class TurnoutRetain(unittest.TestCase):
    def test_the_retained_payload_none_when_the_topic_holds_none(self) -> None:
        self.assertEqual(tf.mqtt_retain("broker", 7, run=FakeRunner(0, "track/turnout/7 CLOSED\n")), "CLOSED")
        self.assertIsNone(tf.mqtt_retain("broker", 7, run=FakeRunner(mc.TIMED_OUT_STATUS, "", "Timed out\n")))

    def test_an_unreadable_broker_is_an_error(self) -> None:
        with self.assertRaises(mc.MosquittoError):
            tf.mqtt_retain("broker", 7, run=FakeRunner(14, "", "Error: Connection refused\n"))


if __name__ == "__main__":
    unittest.main()
