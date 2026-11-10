"""signal_coordinator.py behaviour (jmri/scripts), run against an in-memory JMRI (jmri_fake).

Covers the decisions that reach the field: when the Digicon hand-off sends a head SET or
Unheld, when a field report repaints a head and mast, and how sml_mode messages are
answered. The MQTT adapter here only records what the script would send; nothing
reaches a broker. The source-text checks stay in cats/scripts/tests/test_signal_coordinator.py.
"""
from __future__ import annotations

import contextlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[5] / "jmri/scripts/signal_coordinator.py"
H = jf.SignalHead


class _Dest:
    def __init__(self, name):
        self.name = name

    def getSystemName(self):
        return self.name


class _List:
    def __init__(self, items):
        self.items = items

    def isEmpty(self):
        return not self.items

    def iterator(self):
        it = iter(self.items)

        class _It:
            def __init__(self):
                self._next = next(it, None)

            def hasNext(self):
                return self._next is not None

            def next(self):
                value, self._next = self._next, next(it, None)
                return value

        return _It()


class FakeLogic:
    """One source mast's Signal Mast Logic with Enabled checkboxes per destination."""

    def __init__(self, mast, *dests):
        self.mast = mast
        self.dests = [_Dest(d) for d in dests]
        self.enabled = {d: True for d in dests}

    def getSourceMast(self):
        return self.mast

    def getDestinationList(self):
        return _List(self.dests)

    def isEnabled(self, dest):
        return self.enabled[dest.getSystemName()]


class Coordinator(unittest.TestCase):
    def setUp(self) -> None:
        # Loaded with no MQTT connection, so the module-level start() stops early;
        # each test builds its own controller wired to the recorder.
        self.layout = jf.Layout(mqtt=False)
        self.sc = jf.load_script(SCRIPT, self.layout)
        stack = contextlib.ExitStack()
        stack.enter_context(jf.running(self.layout))
        self.addCleanup(stack.close)
        self.adapter = jf.RecordingAdapter()
        self.head = self.layout.heads.add(jf.FakeHead("IH432", H.GREEN))
        self.mast = self.layout.masts.add(jf.FakeMast("IF$shsm:basic:one-searchlight(IH432)", "Mast 6LB"))
        self.logic = FakeLogic(self.mast, "Mast 8RA")
        c = self.sc["DigiconMqttSml"]()
        c.mqtt = self.adapter
        c._masts = [self.mast]
        c._head_to_mast = {"IH432": self.mast}
        c._sml_by_mast = {self.mast: self.logic}
        c._smls = [self.logic]
        c._set_button_label = lambda: None
        self.bulk = []
        c._set_all_digicon_sml_destinations = self.bulk.append
        self.c = c

    def enroll(self):
        """Field reports the head (that report also paints it Red), then JMRI shows Green."""
        self.c.notifyMqttMessage("track/signalmast/432", "Stop")
        self.head.appearance = H.GREEN
        self.adapter.published.clear()

    def own_by_sml(self):
        """Global SML Enabled and this source's destination checked: Digicon owns the heads."""
        self.c._global_enabled = True
        self.c._snapshot_mast_sml_state()

    def sent(self):
        return list(self.adapter.published)

    # --- topic names and LCOS signal ids --------------------------------------------

    def test_topic_leaf_is_packed_digits(self) -> None:
        f = self.sc["_topic_suffix"]
        self.assertEqual(f("IH432"), "432")
        self.assertEqual(f("ih1047"), "1047")
        self.assertEqual(f("IH9990x"), "IH9990x")

    def test_lcos_signal_ids(self) -> None:
        f = self.sc["_packed_is_lcos_signal"]
        self.assertTrue(f("432"))   # node 4, signal UID 32
        self.assertTrue(f("1047"))  # node 10 (octal-legal), UID 47
        self.assertFalse(f("431"))  # UID 31 is below the signal range
        self.assertFalse(f("448"))  # UID 48 is a crossing
        self.assertFalse(f("832"))  # node 8 is not octal
        self.assertFalse(f("x32"))
        self.assertTrue(self.sc["_is_lcos_ih_sys"]("IH432"))
        self.assertFalse(self.sc["_is_lcos_ih_sys"]("IH9990"))

    def test_heads_named_on_a_mast(self) -> None:
        mast = jf.FakeMast("IF$shsm:aar-1946:two-searchlight(IH440)(IH441)")
        self.assertEqual(self.sc["_head_names_on_mast"](mast), ["IH440", "IH441"])

    def test_appearance_names_from_the_bridge(self) -> None:
        # The LCOS bridge spells flashing aspects FlashRed / FlashYellow (serial_to_mqtt.py).
        f = self.sc["_appearance_constant"]
        self.assertEqual(f("FlashRed"), H.FLASHRED)
        self.assertEqual(f("flashyellow"), H.FLASHYELLOW)
        self.assertEqual(f("off"), H.DARK)
        self.assertIsNone(f("Purple"))

    def test_loading_without_mqtt_sends_nothing(self) -> None:
        self.assertIsNone(self.sc["controller"].mqtt)
        self.assertEqual(self.layout.adapter.published, [])

    # --- enrolment from field reports -----------------------------------------------

    def test_signalmast_report_enrols_the_head(self) -> None:
        self.c.notifyMqttMessage("track/signalmast/432", "Stop")
        self.assertIn("IH432", self.c.mqtt_wanted)

    def test_channel_relative_topic_enrols_too(self) -> None:
        self.c.notifyMqttMessage("signalmast/432", "Stop")
        self.assertIn("IH432", self.c.mqtt_wanted)

    def test_signalhead_topics_never_enrol(self) -> None:
        self.c.notifyMqttMessage("track/signalhead/432", "Green")
        self.assertEqual(self.c.mqtt_wanted, set())

    def test_non_signal_ids_and_missing_beans_are_skipped(self) -> None:
        self.c.notifyMqttMessage("track/signalmast/431", "Stop")
        self.c.notifyMqttMessage("track/signalmast/433", "Stop")  # LCOS id, but no IH433 bean
        self.assertEqual(self.c.mqtt_wanted, set())

    # --- field reports repaint head and mast when the field owns them ---------------

    def test_field_report_paints_head_and_mast(self) -> None:
        self.enroll()
        self.c.notifyMqttMessage("track/signalmast/432", "Approach;Held")
        self.assertEqual(self.head.appearance, H.YELLOW)
        self.assertEqual(self.mast.aspect, "Approach")
        self.assertTrue(self.mast.held)
        self.c.notifyMqttMessage("track/signalmast/432", "clear;unheld")
        self.assertEqual((self.head.appearance, self.mast.aspect, self.mast.held), (H.GREEN, "Clear", False))
        self.assertEqual(self.sent(), [])

    def test_field_report_ignored_while_digicon_owns(self) -> None:
        self.enroll()
        self.own_by_sml()
        self.c.notifyMqttMessage("track/signalmast/432", "Approach")
        self.assertEqual(self.head.appearance, H.GREEN)
        self.assertEqual(self.mast.aspect, "Stop")

    # --- Digicon SET and Unheld -----------------------------------------------------

    def test_set_only_when_digicon_owns(self) -> None:
        self.enroll()
        self.c._publish_head_set(self.head)
        self.assertEqual(self.sent(), [])  # global SML Disabled: the field owns
        self.own_by_sml()
        self.c._publish_head_set(self.head)
        self.assertEqual(self.sent(), [("track/signalhead/432", "Green", True)])

    def test_unchanged_set_is_not_repeated_unless_forced(self) -> None:
        self.enroll()
        self.own_by_sml()
        self.c._publish_head_set(self.head)
        self.c._publish_head_set(self.head)
        self.assertEqual(len(self.sent()), 1)
        self.c._publish_head_set(self.head, force=True)
        self.assertEqual(len(self.sent()), 2)

    def test_unenrolled_head_is_never_set(self) -> None:
        self.own_by_sml()
        self.c._publish_head_set(self.head)
        self.assertEqual(self.sent(), [])

    def test_unchecking_a_destination_unhelds_once(self) -> None:
        self.enroll()
        self.own_by_sml()
        self.logic.enabled["Mast 8RA"] = False
        self.c._on_sml_property(self.logic)
        self.c._on_sml_property(self.logic)
        self.assertEqual(self.sent(), [("track/signalhead/432", "Unheld", True)])
        self.c._publish_head_set(self.head)  # field owns this source now
        self.assertEqual(len(self.sent()), 1)

    def test_unheld_is_sent_once_per_head(self) -> None:
        self.enroll()
        self.c._publish_unheld(self.head)
        self.c._publish_unheld(self.head)
        self.assertEqual(self.sent(), [("track/signalhead/432", "Unheld", True)])

    def test_rechecking_a_destination_sets_again(self) -> None:
        self.enroll()
        self.own_by_sml()
        self.logic.enabled["Mast 8RA"] = False
        self.c._on_sml_property(self.logic)
        self.logic.enabled["Mast 8RA"] = True
        self.c._on_sml_property(self.logic)
        self.assertEqual(self.sent()[-1], ("track/signalhead/432", "Green", True))

    def test_appearance_change_sets_through_the_listener(self) -> None:
        self.enroll()
        self.own_by_sml()
        self.head.appearance = H.RED

        class Event:
            propertyName, source = "Appearance", self.head

        self.c.propertyChange(Event())
        self.assertEqual(self.sent(), [("track/signalhead/432", "Red", True)])

    # --- sml_mode ---------------------------------------------------------------------

    def test_query_is_answered_only_while_owning(self) -> None:
        self.c.notifyMqttMessage("track/bridge/sml_mode", "query")
        self.assertEqual(self.sent(), [])
        self.c._global_enabled = True
        self.c.notifyMqttMessage("track/bridge/sml_mode", "query")
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "enabled", True)])

    def test_own_probe_is_not_answered(self) -> None:
        self.c._global_enabled = True
        self.c._probe_active = True
        self.c._retained_mode = "enabled"
        self.c.notifyMqttMessage("bridge/sml_mode", "query")
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.c._retained_mode, "enabled")

    def test_another_agents_enabling_aborts_without_unheld(self) -> None:
        self.enroll()
        self.own_by_sml()
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "aborting", True),
                                       ("track/bridge/sml_mode", "aborted", True)])
        self.assertEqual(self.bulk, [False])
        self.assertFalse(self.c._global_enabled)

    def test_own_enabling_does_not_abort(self) -> None:
        self.c._enabling_originator = True
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.bulk, [])

    # --- boot -------------------------------------------------------------------------

    def boot(self, retained):
        taken = []
        self.c._enter_enabled = lambda force, from_boot: taken.append((force, from_boot))
        self.c._retained_mode = retained
        jf.Thread.started.clear()
        self.c._schedule_boot_check()
        jf.run_threads()
        return taken

    def test_boot_takes_digicon_when_nobody_owns_it(self) -> None:
        for mode in (None, "disabled", "query", "disabling"):
            self.assertEqual(self.boot(mode), [(True, True)], mode)

    def test_boot_stays_disabled_when_another_agent_owns_it(self) -> None:
        for mode in ("enabled", "enabling", "aborting", "aborted"):
            self.assertEqual(self.boot(mode), [], mode)
            self.assertFalse(self.c._global_enabled)
        self.assertEqual(self.sent(), [])

    def test_boot_check_skipped_while_shutting_down(self) -> None:
        self.c._shutting_down = True
        self.assertEqual(self.boot(None), [])


if __name__ == "__main__":
    unittest.main()
