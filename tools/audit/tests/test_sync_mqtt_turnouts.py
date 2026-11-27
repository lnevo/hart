"""sync_mqtt_turnouts_from_fb.sync and the turnout_feedback helpers, with a fake retain reader and publisher.

Only sync() is called, with fakes passed in; nothing reaches a broker or JMRI.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
MQTT = ROOT / "tools/mqtt"
sys.path.insert(0, str(MQTT))
import mosquitto_cli  # noqa: E402
import turnout_feedback as tf  # noqa: E402


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_mqtt_turnouts_from_fb", MQTT / "sync_mqtt_turnouts_from_fb.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(name: str, user: str, *active: str) -> dict[str, object]:
    sensors = [{"data": {"userName": f"{user} {s}", "state": 4}} for s in active]
    return {"data": {"name": name, "userName": user, "sensor": sensors}}


class FeedbackHelpers(unittest.TestCase):
    def test_fb_state(self) -> None:
        self.assertEqual(tf.fb_state(_row("M2T1", "Switch 1", "FB N")["data"]), "CLOSED")
        self.assertEqual(tf.fb_state(_row("M2T1", "Switch 1", "FB R")["data"]), "THROWN")
        self.assertIsNone(tf.fb_state(_row("M2T1", "Switch 1", "FB N", "FB R")["data"]))
        self.assertIsNone(tf.fb_state({"sensor": [None, {"data": None, "state": 2}]}))

    def test_names(self) -> None:
        self.assertEqual(tf.m2t_address("M2T117"), 117)
        self.assertIsNone(tf.m2t_address("M2Tx"))
        self.assertIsNone(tf.m2t_address("IT5"))
        self.assertEqual(tf.switch_number("Switch 37"), 37)
        self.assertIsNone(tf.switch_number("Engine house"))


class Sync(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load()
        self.table = [
            _row("M2T3", "Switch 3", "FB R"),   # differs: set
            _row("M2T4", "Switch 4", "FB N"),   # matches the retain
            _row("M2T6", "Switch 6"),           # no clear feedback
            _row("M2T117", "Switch 7", "FB N"),  # yard: skipped
            _row("M2T8", "Switch 8", "FB N"),   # differs: publish fails
        ]
        self.retained = {3: "CLOSED", 4: "CLOSED", 8: "THROWN"}
        self.published: list[tuple[int, str]] = []

    def _publish(self, addr: int, msg: str) -> bool:
        self.published.append((addr, msg))
        return addr != 8

    def test_a_failed_publish_counts_as_failed_not_set(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            counts = self.mod.sync(self.table, self.retained.get, self._publish, dry_run=False)
        self.assertEqual(counts, self.mod.SyncCounts(synced=1, unchanged=1, no_clear_fb=1, failed=1))
        self.assertEqual(self.published, [(3, "THROWN"), (8, "CLOSED")])
        self.assertNotIn("M2T8", out.getvalue())
        self.assertIn("FAIL M2T8", err.getvalue())

    def test_dry_run_publishes_nothing(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            counts = self.mod.sync(self.table, self.retained.get, self._publish, dry_run=True)
        self.assertEqual(self.published, [])
        self.assertEqual(counts.synced, 2)
        self.assertEqual(counts.failed, 0)


class Main(unittest.TestCase):
    def test_an_unreadable_broker_exits_1_before_any_publish(self) -> None:
        mod = _load()
        published: list[tuple[int, str]] = []
        err = io.StringIO()
        with unittest.mock.patch.object(mod.tf, "get_json", return_value=[_row("M2T3", "Switch 3", "FB R")]), \
                unittest.mock.patch.object(mod.tf, "mqtt_retain",
                                           side_effect=mosquitto_cli.MosquittoError("connection refused")), \
                unittest.mock.patch.object(mod, "_mqtt_pub", lambda a, m: published.append((a, m)) or True), \
                unittest.mock.patch.object(sys, "argv", ["sync_mqtt_turnouts_from_fb.py"]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = mod.main()
        self.assertEqual(code, 1)
        self.assertEqual(published, [])
        self.assertIn("unreadable: connection refused", err.getvalue())

    def test_a_publish_error_is_reported_and_returns_false(self) -> None:
        mod = _load()
        err = io.StringIO()
        with unittest.mock.patch.object(mod.mosquitto_cli, "set_retained",
                                        side_effect=mosquitto_cli.MosquittoError("exited 5: not authorised")), \
                contextlib.redirect_stderr(err):
            self.assertFalse(mod._mqtt_pub(3, "THROWN"))
        self.assertIn("track/turnout/3: exited 5: not authorised", err.getvalue())


if __name__ == "__main__":
    unittest.main()
