"""tools/mqtt/watch_discard.py only subscribes to _discard/#, and says so when mosquitto_sub is missing."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("watch_discard", ROOT / "tools/mqtt/watch_discard.py")
WD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WD)


class WatchDiscard(unittest.TestCase):
    def test_it_only_subscribes_to_discard(self) -> None:
        cmd = WD.command("broker.example.invalid")
        self.assertEqual(cmd[0], "mosquitto_sub")
        self.assertEqual(cmd[cmd.index("-t") + 1], "_discard/#")
        self.assertEqual(cmd[cmd.index("-h") + 1], "broker.example.invalid")
        self.assertNotIn("mosquitto_pub", " ".join(cmd))

    def test_it_stops_clearly_without_mosquitto_sub(self) -> None:
        with mock.patch.object(WD.shutil, "which", return_value=None), \
                mock.patch.object(WD.subprocess, "call") as call:
            self.assertEqual(WD.main(), 2)
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
