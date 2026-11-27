"""mimic_bus.py: the mimic's mosquitto clients and the state it hears. Popen and the client lookup are faked and
publish is a mock: nothing runs, nothing reaches a broker."""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mimic_bus as MB  # noqa: E402

LAYOUT = {"blocks": [], "heads": [],
          "turnouts": [{"addr": "7", "label": "Switch 7", "plant": "Barn", "feedback": "TWOSENSOR", "n_addr": "100",
                        "r_addr": "101", "tip": "", "level": "staging", "name": "M2T7"}]}


def fake_bus() -> tuple[MB.Bus, list[dict[str, object]]]:
    """A Bus on an unreachable host whose events are collected; the first one stops its subscriber loop."""
    with mock.patch.object(MB, "_which", lambda name: f"/bin/{name}"):
        bus = MB.Bus("broker.invalid", 1883)
    events: list[dict[str, object]] = []

    def emit(e: dict[str, object]) -> None:
        events.append(e)
        bus._stop.set()
    bus.emit = emit  # type: ignore[method-assign]
    return bus, events


class Clients(unittest.TestCase):
    def test_a_missing_client_is_a_bus_error_naming_it(self) -> None:
        with mock.patch.object(MB.shutil, "which", return_value=None), mock.patch.object(MB, "_MOSQUITTO", ()):
            with self.assertRaisesRegex(MB.BusError, "mosquitto_sub not found"):
                MB._which("mosquitto_sub")

    def test_the_subscriber_follows_sensors_turnouts_and_heads_on_the_bus_port(self) -> None:
        bus, _ = fake_bus()
        self.assertEqual(bus.sub_command(), ["/bin/mosquitto_sub", "-h", "broker.invalid", "-p", "1883", "-v",
                                             "-t", "track/sensor/#", "-t", "track/turnout/#",
                                             "-t", "track/signalhead/#"])

    def test_a_host_that_refuses_is_not_a_broker(self) -> None:
        with mock.patch.object(MB.socket, "create_connection", side_effect=ConnectionRefusedError()):
            self.assertFalse(MB.probe("broker.invalid", 1883))

    def test_head_leaves_are_packed_digits(self) -> None:
        self.assertEqual(MB.head_leaf("IH432"), "432")
        self.assertEqual(MB.head_leaf(" 432 "), "432")
        self.assertEqual(MB.head_leaf("IH:HART:C1:1"), "IH:HART:C1:1")


class Requests(unittest.TestCase):
    """A request the bus cannot carry out is a ValueError before anything is sent."""

    def setUp(self) -> None:
        self.bus, _ = fake_bus()
        self.sent = mock.patch.object(self.bus, "publish").start()
        self.addCleanup(mock.patch.stopall)

    def test_a_bad_state_or_an_unknown_turnout_sends_nothing(self) -> None:
        with self.assertRaisesRegex(ValueError, "occupancy must be ACTIVE or INACTIVE"):
            self.bus.set_occupancy("100", "on")
        with self.assertRaisesRegex(ValueError, "turnout must be CLOSED or THROWN"):
            self.bus.set_turnout(LAYOUT, "7", "open")
        with self.assertRaisesRegex(ValueError, "unknown turnout 8"):
            self.bus.set_turnout(LAYOUT, "8", "closed")
        self.sent.assert_not_called()

    def test_a_twosensor_turnout_sets_both_feedback_sensors_then_its_status(self) -> None:
        self.bus.set_turnout(LAYOUT, "7", "thrown")
        self.assertEqual([c.args[0].rsplit("/", 1)[-1] for c in self.sent.call_args_list], ["100", "101", "7"])


class Heard(unittest.TestCase):
    def test_each_kind_of_line_sets_its_state_and_is_passed_on(self) -> None:
        bus, events = fake_bus()
        for line in ("track/sensor/100 ACTIVE\n", "track/turnout/7 THROWN", "track/signalhead/IH432 RED",
                     "track/other/1 X", "Timed out", "", "nospace"):
            bus._on_line(line)
        state = bus.snapshot()
        self.assertEqual((state["sensors"], state["turnouts"], state["heads"]),
                         ({"100": "ACTIVE"}, {"7": "THROWN"}, {"432": "RED"}))
        self.assertEqual([e["type"] for e in events], ["sensor", "turnout", "head"])
        self.assertEqual(state["mqtt"], {"host": "broker.invalid", "connected": False})

    def test_a_full_stream_is_dropped(self) -> None:
        with mock.patch.object(MB, "_which", lambda name: f"/bin/{name}"):
            bus = MB.Bus("broker.invalid", 1883)
        full, live = bus.add_sub(), bus.add_sub()
        for _ in range(200):
            full.put_nowait("x")
        bus.emit({"type": "hello"})
        self.assertEqual(bus.subs, [live])
        self.assertEqual(live.get_nowait(), '{"type": "hello"}')
        bus.drop_sub(live)
        self.assertEqual(bus.subs, [])


class Reconnect(unittest.TestCase):
    """The subscriber loop reports a missing client and does not hide bugs."""

    def test_a_client_that_cannot_start_is_a_disconnected_event(self) -> None:
        bus, events = fake_bus()
        with mock.patch.object(MB.subprocess, "Popen", side_effect=FileNotFoundError("mosquitto_sub")):
            bus.loop_sub()
        self.assertEqual(events, [{"type": "mqtt", "connected": False, "error": "mosquitto_sub"}])
        self.assertFalse(bus.connected)

    def test_a_line_that_cannot_be_read_is_a_warning_and_reading_goes_on(self) -> None:
        bus, events = fake_bus()

        def emit(e: dict[str, object]) -> None:
            events.append(e)
            if e.get("connected") is False:
                bus._stop.set()
        bus.emit = emit  # type: ignore[method-assign]
        proc = mock.Mock(stdout=iter(["bad line\n", "track/sensor/1 ACTIVE\n"]))
        read = []

        def on_line(line: str) -> None:
            if line.startswith("bad"):
                raise KeyError("addr")
            read.append(line)
        err = io.StringIO()
        with mock.patch.object(MB.subprocess, "Popen", side_effect=[proc, FileNotFoundError("gone")]), \
                mock.patch.object(bus, "_on_line", side_effect=on_line), mock.patch.object(MB.time, "sleep"), \
                mock.patch.object(MB.sys, "stderr", err):
            bus.loop_sub()
        self.assertEqual(read, ["track/sensor/1 ACTIVE\n"])
        self.assertIn({"type": "warning", "line": "bad line", "error": "KeyError('addr')"}, events)
        self.assertIn("cannot read 'bad line'", err.getvalue())
        self.assertEqual(events[-1], {"type": "mqtt", "connected": False, "error": "gone"})

    def test_a_thread_that_ends_on_an_error_says_disconnected(self) -> None:
        bus, events = fake_bus()
        bus.emit = events.append  # type: ignore[method-assign]

        def broken():
            raise RuntimeError("pipe")
            yield ""
        proc = mock.Mock(stdout=broken())
        with mock.patch.object(MB.subprocess, "Popen", return_value=proc):
            with self.assertRaises(RuntimeError):
                bus.loop_sub()
        self.assertFalse(bus.connected)
        self.assertEqual(events[-1], {"type": "mqtt", "connected": False, "error": "the subscriber stopped"})


if __name__ == "__main__":
    unittest.main()
