"""tools/mqtt/watch_discard.py only subscribes to _discard/#, labels stored and new writes, and stops
clearly when mosquitto_sub is missing. The hooks keep make mqtt-clean from subagents and from
operating sessions."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


WD = load("watch_discard", "tools/mqtt/watch_discard.py")


class WatchDiscard(unittest.TestCase):
    def test_it_only_subscribes_to_discard(self) -> None:
        cmd = WD.command("broker.example.invalid")
        self.assertEqual(cmd[0], "mosquitto_sub")
        self.assertEqual(cmd[cmd.index("-t") + 1], "_discard/#")
        self.assertEqual(cmd[cmd.index("-h") + 1], "broker.example.invalid")
        self.assertEqual(cmd[cmd.index("-V") + 1], "mqttv311")
        self.assertNotIn("mosquitto_pub", " ".join(cmd))

    def test_a_stored_message_is_told_from_a_new_write(self) -> None:
        self.assertIn("stored", WD.describe("2026-11-21T19:00:00\t1\t_discard/cmd/sensor/102\tINACTIVE\n"))
        new = WD.describe("2026-11-21T19:00:05\t0\t_discard/cmd/sensor/102\tINACTIVE\n")
        self.assertIn("NEW", new)
        self.assertIn("_discard/cmd/sensor/102", new)

    def test_a_line_it_cannot_split_is_shown_as_it_came(self) -> None:
        self.assertEqual(WD.describe("odd line\n"), "odd line")

    def test_it_stops_clearly_without_mosquitto_sub(self) -> None:
        with mock.patch.object(WD.shutil, "which", return_value=None), \
                mock.patch.object(WD.subprocess, "Popen") as popen:
            self.assertEqual(WD.main(), 2)
        popen.assert_not_called()


class CleanIsGuarded(unittest.TestCase):
    def test_subagents_may_not_run_it(self) -> None:
        guard = load("subagent_guard", ".claude/hooks/subagent_guard.py")
        self.assertIn("mqtt-clean", guard.BLOCKED_MAKE)

    def test_it_is_a_host_action_while_operating(self) -> None:
        guard = load("main_guard", ".claude/hooks/main_guard.py")
        self.assertIn("broker", guard.host_control("make mqtt-clean", {"by": "owner"}) or "")
        self.assertIsNone(guard.host_control("make mqtt-watch", {"by": "owner"}))


if __name__ == "__main__":
    unittest.main()
