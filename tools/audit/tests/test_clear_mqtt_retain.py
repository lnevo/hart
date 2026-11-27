"""clear_mqtt_cmd_sensor_retain: what it clears and what it counts as left over agree.

A fake broker stands in for mosquitto_sub and mosquitto_pub; nothing connects to a broker.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/mqtt/clear_mqtt_cmd_sensor_retain.py"
sys.path.insert(0, str(SCRIPT.parent))      # its sibling mosquitto_cli, as when the script runs


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("clear_mqtt_cmd_sensor_retain", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _matches(sub: str, topic: str) -> bool:
    if sub == "+":
        return "/" not in topic
    return sub.endswith("/#") and topic.startswith(sub[:-1])


class FakeBroker:
    """Retained topics; a clear removes one unless it is listed as stuck."""

    def __init__(self, retained: dict[str, str], stuck: frozenset[str] = frozenset()) -> None:
        self.retained = dict(retained)
        self.stuck = stuck
        self.cleared: list[str] = []

    def sub(self, topic: str, wait: str = "1") -> list[tuple[str, str]]:
        return [(t, p) for t, p in self.retained.items() if _matches(topic, t)]

    def clear(self, topic: str) -> None:
        self.cleared.append(topic)
        if topic not in self.stuck:
            self.retained.pop(topic, None)


class ClearRetain(unittest.TestCase):
    def _run(self, broker: FakeBroker, err: io.StringIO | None = None) -> tuple[int, str]:
        mod = _load()
        setattr(mod, "_sub", broker.sub)       # the broker calls, replaced by the fake
        setattr(mod, "_clear", broker.clear)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err or io.StringIO()):
            code = mod.main()
        return code, out.getvalue()

    def test_a_failed_clear_stops_the_run_and_exits_1(self) -> None:
        import mosquitto_cli

        class Refusing(FakeBroker):
            def clear(self, topic: str) -> None:
                raise mosquitto_cli.MosquittoError(f"clear of {topic} exited 5: not authorised")

        err = io.StringIO()
        code, out = self._run(Refusing({"track/cmd/sensor/1": "ACTIVE"}), err)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("cleared=0 then stopped: clear of track/cmd/sensor/1 exited 5", err.getvalue())

    def test_an_unreadable_broker_exits_1_not_0(self) -> None:
        import mosquitto_cli

        class Down(FakeBroker):
            def sub(self, topic: str, wait: str = "1") -> list[tuple[str, str]]:
                raise mosquitto_cli.MosquittoError("connection refused")

        err = io.StringIO()
        code, _ = self._run(Down({}), err)
        self.assertEqual(code, 1)
        self.assertIn("connection refused", err.getvalue())

    def test_a_non_digit_ih_leaf_is_neither_cleared_nor_left_over(self) -> None:
        broker = FakeBroker({
            "track/signalhead/IHfoo": "x",
            "track/signalhead/IH12": "Green",
            "track/signalhead/12": "Green",
        })
        code, out = self._run(broker)
        self.assertEqual(code, 0, out)
        self.assertEqual(broker.cleared, ["track/signalhead/IH12"])
        self.assertIn("remaining_ih_leaf=0", out)

    def test_each_kind_is_cleared_and_live_topics_are_kept(self) -> None:
        live = {"track/sensor/100": "ACTIVE", "track/turnout/7": "CLOSED", "track/signalhead/5": "Red"}
        junk = {
            "track/cmd/sensor/100": "ACTIVE",
            "100": "INACTIVE",
            "_discard/cmd/sensor/3": "ACTIVE",
            "track/signalhead/ih4": "Red",
            "track/sensor/Block 1-1": "ACTIVE",
        }
        broker = FakeBroker({**live, **junk})
        code, out = self._run(broker)
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(broker.cleared), sorted(junk))
        self.assertEqual(broker.retained, live)
        self.assertTrue(out.startswith("cleared=5 remaining_cmd=0 "), out)

    def test_junk_that_stays_after_the_clear_exits_1(self) -> None:
        broker = FakeBroker({"track/sensor/Block 1-1": "ACTIVE"}, stuck=frozenset({"track/sensor/Block 1-1"}))
        code, out = self._run(broker)
        self.assertEqual(code, 1)
        self.assertIn("remaining_nondigit_sensor=1", out)


if __name__ == "__main__":
    unittest.main()
