"""signal_coordinator.py behaviour (jmri/scripts), run against an in-memory JMRI (jmri_fake).

Covers the decisions that reach the field: when the Digicon hand-off sends a head SET or
Unheld, when a field report repaints a head and mast, and how sml_mode messages are
answered. The MQTT adapter here only records what the script would send; nothing
reaches a broker. The source-text checks stay in cats/scripts/tests/test_signal_coordinator.py.
"""
from __future__ import annotations

import contextlib
import io
import sys
import types
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

    def setEnabled(self, dest):
        self.enabled[dest.getSystemName()] = True

    def setDisabled(self, dest):
        self.enabled[dest.getSystemName()] = False

    def addPropertyChangeListener(self, listener):
        pass

    def removePropertyChangeListener(self, listener):
        pass


class _Space:
    """Apps.buttonSpace(): the main-window button strip, inside a frame."""

    def __init__(self):
        self.components = []
        self.frame = _Frame()

    def getComponentCount(self):
        return len(self.components)

    def getComponent(self, i):
        return self.components[i]

    def add(self, c):
        self.components.append(c)
        c.parent = self

    def remove(self, c):
        self.components = [x for x in self.components if x is not c]

    def revalidate(self):
        pass

    def repaint(self):
        pass

    def getTopLevelAncestor(self):
        return self.frame


class _Frame:
    def __init__(self):
        self.listeners = []

    def getTitle(self):
        return "PanelPro"

    def addWindowListener(self, listener):
        self.listeners.append(listener)

    def removeWindowListener(self, listener):
        self.listeners = [l for l in self.listeners if l is not listener]


class _QueuedSwing:
    """SwingUtilities whose invokeLater queues: shows what a worker thread does off the EDT."""

    queue = []

    @staticmethod
    def isEventDispatchThread():
        return False

    @staticmethod
    def invokeLater(runnable):
        _QueuedSwing.queue.append(runnable)

    @staticmethod
    def drain():
        while _QueuedSwing.queue:
            _QueuedSwing.queue.pop(0).run()


class Coordinator(unittest.TestCase):
    def setUp(self) -> None:
        # The script keeps its controller on __main__ so a re-run can find it; keep tests apart.
        import __main__

        saved = getattr(__main__, "digicon_sml_controller", None)
        if saved is not None:
            del __main__.digicon_sml_controller

        def restore():
            if saved is not None:
                __main__.digicon_sml_controller = saved
            elif hasattr(__main__, "digicon_sml_controller"):
                del __main__.digicon_sml_controller

        self.addCleanup(restore)
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

    def test_appearance_names(self) -> None:
        # JMRI's names are the standard; the LCOS firmware's FlashRed tokens are accepted too.
        f = self.sc["_appearance_constant"]
        self.assertEqual(f("Flashing Red"), H.FLASHRED)
        self.assertEqual(f("Flashing Lunar"), H.FLASHLUNAR)
        self.assertEqual(f("FlashRed"), H.FLASHRED)
        self.assertEqual(f("flashyellow"), H.FLASHYELLOW)
        self.assertEqual(f("off"), H.DARK)
        self.assertIsNone(f("Purple"))

    def test_flashing_set_uses_the_jmri_name(self) -> None:
        self.enroll()
        self.own_by_sml()
        self.head.appearance = H.FLASHRED
        self.c._publish_head_set(self.head)
        self.assertEqual(self.sent(), [("track/signalhead/432", "Flashing Red", True)])

    def test_field_report_in_jmri_spelling_paints_the_head(self) -> None:
        self.enroll()
        self.c.notifyMqttMessage("track/signalmast/432", "Flashing Yellow")
        self.assertEqual(self.head.appearance, H.FLASHYELLOW)

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
        self.c._host = "rpi-jmri"
        self.c.notifyMqttMessage("track/bridge/sml_mode", "query")
        self.assertEqual(self.sent(), [])
        self.c._global_enabled = True
        self.c._claim = (T0, False)
        self.c.notifyMqttMessage("track/bridge/sml_mode", "query")
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "enabled", True),
                                       ("track/bridge/sml_claim", "enabled rpi-jmri %d" % T0, True)])

    def test_enable_probe_query_is_not_retained(self) -> None:
        # A retained "query" would replace the retained mode on the broker and replay to every
        # later subscriber. JMRI's two-argument publish retains, so the flag must be False.
        self.c._retained_mode = None
        self.assertEqual(self.c._probe_and_confirm_override(), "ok")
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "query", False)])
        self.assertFalse(self.c._probe_active)

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
        jf.run_threads()
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "aborting", True),
                                       ("track/bridge/sml_mode", "aborted", True)])
        self.assertEqual(self.bulk, [False])
        self.assertFalse(self.c._global_enabled)

    def test_own_enabling_does_not_abort(self) -> None:
        self.c._host = "rpi-jmri"
        self.c._stamp_claim()
        jf.Thread.started.clear()
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
        self.c.notifyMqttMessage("track/bridge/sml_claim", "enabling rpi-jmri %d" % self.c._claim[0])
        self.assertEqual(jf.Thread.started, [])  # no abort worker
        self.assertEqual(self.bulk, [])
        self.assertTrue(self.c._enabling_originator)
        self.assertEqual(self.sent(), [])

    # --- abort runs off the MQTT callback thread ---------------------------------------

    def test_abort_does_not_wait_on_the_mqtt_thread(self) -> None:
        # The bulk uncheck waits on the layout thread; on JMRI's one MQTT callback thread that
        # wait stalls every inbound message, so the abort work goes to a worker thread.
        self.enroll()
        self.own_by_sml()
        jf.Thread.started.clear()
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.bulk, [])
        self.assertEqual(len(jf.Thread.started), 1)
        self.assertFalse(self.c._global_enabled)  # stops SET at once
        # A second enabling or a query while the abort is queued: no second abort, no ACK.
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
        self.c.notifyMqttMessage("track/bridge/sml_mode", "query")
        self.assertEqual(len(jf.Thread.started), 1)
        self.assertEqual(self.sent(), [])
        jf.run_threads()
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "aborting", True),
                                       ("track/bridge/sml_mode", "aborted", True)])
        self.assertEqual(self.bulk, [False])

    # --- abort during a running Disable or Enable worker -------------------------------

    def test_abort_during_disable_keeps_the_controller_busy(self) -> None:
        self.enroll()
        self.own_by_sml()
        jf.Thread.started.clear()
        self.c._enter_disabled(release=True)
        disable_worker = jf.Thread.started.pop(0)
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
        jf.run_threads()  # the abort finishes while the Disable worker is still in its Hold
        self.c._on_toggle()  # operator click: must wait for the Disable worker
        self.assertEqual(jf.Thread.started, [])
        self.adapter.published.clear()
        disable_worker.runnable.run()
        # Another agent owns Digicon now: no Unheld of its heads, no disabled over its enabling.
        self.assertEqual(self.sent(), [])
        self.assertFalse(self.mast.held)
        self.c._on_toggle()
        self.assertEqual(len(jf.Thread.started), 1)  # free again once the worker ends

    def test_abort_during_enable_probe_does_not_take(self) -> None:
        self.enroll()
        c = self.c

        def probe():
            c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
            jf.run_threads()
            return "ok"

        c._probe_and_confirm_override = probe
        jf.Thread.started.clear()
        c._enter_enabled(force=False, from_boot=False)
        jf.run_threads()
        self.assertNotIn(("track/bridge/sml_mode", "enabled", True), self.sent())
        self.assertNotIn(True, self.bulk)
        self.assertFalse(c._global_enabled)
        self.assertFalse(c._enabling_originator)
        self.assertFalse(self.mast.held)

    def test_abort_during_override_dialog_sends_no_enabling(self) -> None:
        self.enroll()
        c = self.c

        def probe():
            c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
            jf.run_threads()
            return "force"  # the operator answers Yes after the other agent began taking

        c._probe_and_confirm_override = probe
        jf.Thread.started.clear()
        c._enter_enabled(force=False, from_boot=False)
        jf.run_threads()
        self.assertNotIn(("track/bridge/sml_mode", "enabling", True), self.sent())
        self.assertFalse(c._enabling_originator)
        self.assertFalse(c._should_ack_sml_alive())

    def test_abort_while_unheld_goes_out_stops_the_disable(self) -> None:
        self.enroll()
        self.own_by_sml()
        c = self.c
        record = self.adapter.publish

        def publish(topic, payload, retain=True):
            record(topic, payload, retain)
            if payload == "Unheld":
                c._abort_gen += 1  # another agent's enabling lands mid-burst

        self.adapter.publish = publish
        jf.Thread.started.clear()
        c._enter_disabled(release=True)
        jf.run_threads()
        self.assertEqual(self.sent(), [("track/signalhead/432", "Unheld", True)])

    def test_quit_release_stands_down_after_an_abort_in_its_hold(self) -> None:
        self.enroll()
        self.own_by_sml()
        c = self.c

        class AbortingThread(jf.Thread):
            @staticmethod
            def sleep(ms):
                c._abort_gen += 1

        self.sc["Thread"] = AbortingThread
        c._on_jmri_shutdown()
        self.assertEqual(self.sent(), [])
        self.assertFalse(self.mast.held)

    def test_abort_leaves_the_button_to_a_running_worker(self) -> None:
        labels = []
        self.c._set_button_label = lambda: labels.append(1)
        self.c._busy = True  # a Disable worker is in its Hold
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
        jf.run_threads()
        self.assertEqual(labels, [])

    # --- stale retained enabled -----------------------------------------------------------

    def test_bridge_release_with_a_probe_query_between(self) -> None:
        taken = self.take_calls()
        self.logic.enabled["Mast 8RA"] = False
        for mode in ("enabled", "query", "disabling", "query", "disabled"):
            self.c.notifyMqttMessage("track/bridge/sml_mode", mode)
        self.assertEqual(taken, [(True, True)])

    def take_calls(self):
        taken = []
        self.c._enter_enabled = lambda force, from_boot: taken.append((force, from_boot))
        return taken

    def test_bridge_release_of_a_stale_enabled_lets_an_idle_host_take(self) -> None:
        # Power cut: both hosts boot, read the stale retained enabled and stay Disabled. The
        # bridge finds no owner (query, then disabling, then disabled); an idle host takes.
        taken = self.take_calls()
        self.logic.enabled["Mast 8RA"] = False  # boot held the dests off
        for mode in ("enabled", "query", "disabling", "disabled"):
            self.c.notifyMqttMessage("track/bridge/sml_mode", mode)
        self.assertEqual(taken, [(True, True)])
        self.assertEqual(self.sent(), [])

    def test_operator_disable_elsewhere_is_not_taken_over(self) -> None:
        taken = self.take_calls()
        self.logic.enabled["Mast 8RA"] = False
        for mode in ("enabled", "disabled"):
            self.c.notifyMqttMessage("track/bridge/sml_mode", mode)
        self.assertEqual(taken, [])

    def test_bridge_release_while_busy_or_booting_is_left_alone(self) -> None:
        taken = self.take_calls()
        self.logic.enabled["Mast 8RA"] = False
        for attr in ("_busy", "_boot_pending", "_shutting_down", "_enabling_originator"):
            setattr(self.c, attr, True)
            self.c.notifyMqttMessage("track/bridge/sml_mode", "disabling")
            self.c.notifyMqttMessage("track/bridge/sml_mode", "disabled")
            setattr(self.c, attr, False)
        self.assertEqual(taken, [])

    # --- second run of the script -------------------------------------------------------

    def load_running(self):
        """Load the script with MQTT and a main window, as Start Up does."""
        self.layout.memo = jf.FakeMemo(self.layout.adapter)
        if self.layout.button_space is None:
            self.layout.button_space = _Space()
        self.env = jf.load_script(SCRIPT, self.layout)
        return self.env["controller"]

    def test_second_run_detaches_the_first(self) -> None:
        first = self.load_running()
        second = self.load_running()
        self.assertIsNot(first, second)
        space = self.layout.button_space
        self.assertNotIn(first, self.mast.listeners)
        self.assertIn(second, self.mast.listeners)
        gone = {t for t, l in self.layout.adapter.unsubscribed if l is first}
        self.assertEqual(gone, {"track/bridge/sml_mode", "track/bridge/sml_claim",
                                "track/signalmast/#", "track/signalhead/#"})
        self.assertFalse([t for t, l in self.layout.adapter.unsubscribed if l is second])
        self.assertEqual([t._controller for t in self.layout.shutdown.tasks], [second])
        self.assertEqual(len(space.frame.listeners), 1)
        # The one visible button drives the new instance.
        self.assertEqual(space.components, [second._button])
        clicks = []
        second._on_toggle = lambda: clicks.append(1)
        space.components[0].click()
        self.assertEqual(clicks, [1])
        # The old instance no longer acts on a quit.
        self.assertTrue(first._shutdown_released)

    def test_button_left_by_an_older_run_is_replaced(self) -> None:
        # A run without the detach step left its button on the strip.
        space = _Space()
        stale = jf.FakeButton("SML Enabled")
        space.add(stale)
        self.layout.button_space = space
        c = self.load_running()
        self.assertEqual(space.components, [c._button])

    def test_detached_controllers_button_retry_does_nothing(self) -> None:
        space = _Space()
        self.layout.button_space = space
        self.c._button = jf.FakeButton("SML Disabled")
        self.c._shutting_down = True  # what _detach_controller sets
        jf.Thread.started.clear()
        self.c._add_toggle_button(attempt=1)
        jf.run_threads()
        self.assertEqual(space.components, [])

    def test_quit_task_releases_its_own_controller(self) -> None:
        c = self.load_running()
        task = self.layout.shutdown.tasks[0]
        calls = []
        c._on_jmri_shutdown = lambda: calls.append(1)
        self.env["controller"] = None  # the script's global may name a later run's controller
        task.call()
        self.assertEqual(calls, [1])

    # --- Swing thread ----------------------------------------------------------------------

    def test_window_close_releases_off_the_swing_thread(self) -> None:
        self.enroll()
        self.own_by_sml()
        self.layout.button_space = _Space()
        self.c._add_quit_window_hook()
        jf.Thread.started.clear()
        self.c._set_all_digicon_sml_destinations = lambda on: None
        self.layout.button_space.frame.listeners[0].windowClosing(None)
        self.assertEqual(self.sent(), [])  # the 3 s Hold does not run on the Swing thread
        self.assertEqual(len(jf.Thread.started), 1)
        jf.run_threads()
        self.assertEqual(self.sent()[-1], ("track/bridge/sml_mode", "disabled", True))
        n = len(self.sent())
        self.c._on_jmri_shutdown()  # the ShutDownTask after it: already released
        self.assertEqual(len(self.sent()), n)

    def test_button_is_changed_only_on_the_swing_thread(self) -> None:
        self.sc["SwingUtilities"] = _QueuedSwing
        self.addCleanup(_QueuedSwing.queue.clear)
        for start in (lambda: self.c._enter_enabled(force=True, from_boot=True),
                      lambda: self.c._enter_disabled(release=False)):
            self.c._busy = False
            self.c._button = jf.FakeButton("SML Disabled")
            start()
            self.assertTrue(self.c._button.enabled)  # not touched from this thread
            _QueuedSwing.drain()
            self.assertFalse(self.c._button.enabled)

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

    # --- re-run on the owning host -------------------------------------------------------

    def test_rerun_on_the_owning_host_keeps_digicon_quietly(self) -> None:
        # A re-run while this host owns Digicon finds the dests on. It keeps ownership with the
        # same claim: no stored-Enabled popup, no enabling, no Hold.
        layout_logic = FakeLogic(self.mast, "Mast 8RA")
        layout_logic.enabled["Mast 8RA"] = False  # stored Disabled; the first run takes
        real = self.layout.instance
        manager = types.SimpleNamespace(getSignalMastLogicList=lambda: [layout_logic])
        self.layout.instance = lambda cls: (
            manager if getattr(cls, "__name__", "") == "SignalMastLogicManager" else real(cls))
        first = self.load_running()
        jf.run_threads()
        first._claim = (T0, False)
        first._global_enabled = True
        layout_logic.enabled["Mast 8RA"] = True  # the earlier run left the dests on
        self.layout.adapter.published.clear()
        second = self.load_running()
        jf.run_threads()
        self.assertTrue(second._global_enabled)
        self.assertEqual(second._claim, (T0, False))
        self.assertEqual(second._host, first._host)
        sent = [p for t, p, r in self.layout.adapter.published if t in (SML, CLAIM)]
        self.assertEqual(sent, [])
        self.assertFalse(self.mast.held)

    def test_rerun_on_an_idle_host_boots_as_before(self) -> None:
        first = self.load_running()  # still in its boot read: not owning
        self.assertIsNone(self.sc["_owned_claim"](first))
        self.assertIsNone(self.sc["_owned_claim"](object()))  # a controller from an older copy


# --- two hosts racing for Digicon (owner decision 2026-11-19) -------------------------

SML = "track/bridge/sml_mode"
CLAIM = "track/bridge/sml_claim"
T0 = 1_763_590_000_000  # epoch ms; the hosts compare stamps only with each other


class _Broker:
    """One broker for sml_mode and sml_claim: every host gets every message, in one order.

    A publish is queued; `deliver()` hands each message to every host (the publisher too,
    as a broker echoes to a subscribed client) and keeps the last retained one per topic.
    One order across both topics is what mosquitto does for one client's publishes. A
    sleeping thread lets time pass and delivers what is queued, unless `hold` is set:
    claims made while held are "at once". Nothing here touches a network.
    """

    def __init__(self):
        self.queue, self.log, self.hosts = [], [], []
        self.retained = {}
        self.hold = False
        self.now = T0  # real time; each host adds its own clock skew
        self._delivering = False

    def adapter(self):
        broker = self

        class _Adapter(jf.RecordingAdapter):
            def publish(self, topic, payload, retain=True):
                super().publish(topic, payload, retain)
                if topic in (SML, CLAIM):
                    broker.queue.append((topic, payload, retain))

        return _Adapter()

    def bridge(self, *payloads):
        """The LCOS bridge publishes each payload; each is delivered before the next."""
        for p in payloads:
            self.queue.append((SML, p, p != "query"))
            self.deliver()

    def deliver(self):
        if self._delivering:
            return
        self._delivering = True
        try:
            while self.queue:
                topic, payload, retain = self.queue.pop(0)
                self.log.append(payload)
                if retain:
                    self.retained[topic] = payload
                for host in list(self.hosts):
                    host.notifyMqttMessage(topic, payload)
        finally:
            self._delivering = False

    def sleep(self, ms):
        # While held, the claims are "at once": no delivery and no time passes.
        if not self.hold:
            self.now += ms
            self.deliver()


class TwoHosts(unittest.TestCase):
    """The Pi and Windows each run the coordinator against one shared broker."""

    def setUp(self) -> None:
        import __main__

        saved = getattr(__main__, "digicon_sml_controller", None)

        def restore():
            if saved is not None:
                __main__.digicon_sml_controller = saved

        self.addCleanup(restore)
        self.layout = jf.Layout(mqtt=False)
        self.sc = jf.load_script(SCRIPT, self.layout)
        stack = contextlib.ExitStack()
        stack.enter_context(jf.running(self.layout))
        self.addCleanup(stack.close)
        self.broker = _Broker()
        broker = self.broker

        class BrokerThread(jf.Thread):
            @staticmethod
            def sleep(ms):
                broker.sleep(ms)

            def start(self):
                # An abort takes milliseconds on a host, well inside another host's Hold.
                if type(self.runnable).__name__ == "_Abort":
                    self.runnable.run()
                else:
                    jf.Thread.start(self)

        self.sc["Thread"] = BrokerThread
        jf.Thread.started.clear()
        self.pi = self.host("rpi-jmri")
        self.win = self.host("minipc-e5h6x")

    def host(self, name, skew_ms=0):
        c = self.sc["DigiconMqttSml"]()
        c._host = name
        c._skew_ms = skew_ms
        c._now_ms = lambda: self.broker.now + c._skew_ms
        c.mqtt = self.broker.adapter()
        mast = jf.FakeMast("IF$shsm:basic:one-searchlight(IH432)", "Mast 6LB")
        logic = FakeLogic(mast, "Mast 8RA")
        logic.enabled["Mast 8RA"] = False  # stored Disabled, as the tables are
        c._masts = [mast]
        c._head_to_mast = {"IH432": mast}
        c._sml_by_mast = {mast: logic}
        c._smls = [logic]
        c._set_button_label = lambda: None

        def bulk(on):
            for d in logic.enabled:
                logic.enabled[d] = on

        c._set_all_digicon_sml_destinations = bulk
        c.logic, c.mast_bean = logic, mast
        self.broker.hosts.append(c)
        return c

    # helpers -----------------------------------------------------------------------------

    def run_named(self, *names):
        """Run the queued threads whose runnable class is named (not threads they start)."""
        for t in [t for t in jf.Thread.started if type(t.runnable).__name__ in names]:
            jf.Thread.started.remove(t)
            t.runnable.run()

    def settle(self):
        self.broker.hold = False
        for _ in range(50):
            self.broker.deliver()
            if not jf.Thread.started and not self.broker.queue:
                return
            jf.Thread.started.pop(0).runnable.run()
        self.fail("hosts did not settle")

    def boot(self, *hosts):
        for c in hosts:
            c._boot_hold_sml_off()
            c._schedule_boot_check()

    def owners(self):
        return [c for c in (self.pi, self.win) if c._global_enabled]

    def assert_one_owner(self, who):
        self.assertEqual([c._host for c in self.owners()], [who._host])
        other = self.win if who is self.pi else self.pi
        self.assertTrue(all(who.logic.enabled.values()))
        self.assertFalse(any(other.logic.enabled.values()))
        self.assertFalse(other._enabling_originator)
        self.assertIsNone(other._claim)
        self.assertFalse(other.mast_bean.held)
        self.assertFalse(who.mast_bean.held)
        self.assertEqual(self.broker.retained[SML], "enabled")
        self.assertEqual(self.broker.retained[CLAIM].split()[:2], ["enabled", who._host])

    def stale(self, c, claim):
        """What a host reads at subscribe: the bare retained word, then the claim."""
        c.notifyMqttMessage(SML, claim.split()[0])
        c.notifyMqttMessage(CLAIM, claim)

    def claims_at_once(self, *hosts):
        """Boot the hosts so each claims before it hears the other."""
        self.broker.hold = True
        self.boot(*hosts)
        self.run_named("_Boot")
        self.assertEqual(sum(1 for t, p, _ in self.broker.queue if t == CLAIM), len(hosts))
        self.settle()

    # payload -------------------------------------------------------------------------------

    def test_enabling_and_enabled_carry_host_and_stamp(self) -> None:
        self.boot(self.pi)
        self.settle()
        stamp = T0 + 1000  # after the boot read wait
        self.assertIn("enabling rpi-jmri %d" % stamp, self.broker.log)
        self.assertEqual(self.broker.retained[CLAIM], "enabled rpi-jmri %d" % stamp)
        self.assertEqual(self.broker.retained[SML], "enabled")

    def test_sml_mode_payloads_stay_the_bridge_words(self) -> None:
        # The LCOS bridge compares the whole sml_mode payload; it never sees sml_claim.
        self.claims_at_once(self.pi, self.win)
        for c in (self.pi, self.win):
            for t, p, r in c.mqtt.published:
                if t == SML:
                    self.assertIn(p, ("enabling", "enabled", "aborting", "aborted",
                                      "disabling", "disabled", "query"))
        # The bare word goes out before the claim, so an idle host stands back first.
        pi = [(t, p.split()[0]) for t, p, r in self.pi.mqtt.published]
        self.assertEqual(pi[:2], [(SML, "enabling"), (CLAIM, "enabling")])

    def test_parse_old_and_new_payloads(self) -> None:
        parse = self.sc["_parse_claim"]
        self.assertEqual(parse("enabled"), ("enabled", None, None, False))
        self.assertEqual(parse(" Enabled "), ("enabled", None, None, False))
        self.assertEqual(parse("enabling rpi-jmri 5 force"), ("enabling", "rpi-jmri", 5, True))
        self.assertEqual(parse("enabled RPi-JMRI 5"), ("enabled", "rpi-jmri", 5, False))
        self.assertEqual(parse("enabled rpi-jmri x"), ("enabled", None, None, False))
        self.assertEqual(parse(""), ("", None, None, False))

    def test_host_token(self) -> None:
        tok = self.sc["_host_token"]
        self.assertEqual(tok("RPi-JMRI.local"), "rpi-jmri")
        self.assertEqual(tok("MINIPC E5H6X"), "minipc-e5h6x")
        self.assertEqual(tok(""), "unknown")
        self.assertEqual(tok(None), "unknown")

    # simultaneous boot -----------------------------------------------------------------------

    def test_simultaneous_boot_tie_goes_to_the_first_host_name(self) -> None:
        self.claims_at_once(self.pi, self.win)
        self.assert_one_owner(self.win)  # same millisecond: "minipc-e5h6x" < "rpi-jmri"

    def test_simultaneous_boot_earlier_stamp_wins(self) -> None:
        self.pi._skew_ms = -3  # the Pi's clock reads 3 ms earlier
        self.claims_at_once(self.win, self.pi)
        self.assert_one_owner(self.pi)

    def test_loser_cancels_its_hold_without_turning_pairs_on(self) -> None:
        # #704: another host's enabling during this host's Hold stops the hand-off.
        self.claims_at_once(self.pi, self.win)
        pi_sent = [p.split()[0] for t, p, r in self.pi.mqtt.published if t == SML]
        self.assertEqual(pi_sent, ["enabling"])  # no enabled, no aborting
        self.assertEqual(self.pi.logic.enabled, {"Mast 8RA": False})

    def test_own_announced_echo_is_not_a_rival(self) -> None:
        # #704 known gap: once announced, a later enabling was taken as this host's echo.
        self.boot(self.pi)
        self.run_named("_Boot")
        self.broker.deliver()  # own echo: keep taking
        self.assertIsNotNone(self.pi._claim)
        self.win._skew_ms = -50  # a rival claim with an earlier stamp, before enabled
        self.win._enter_enabled(force=True, from_boot=True)
        self.settle()
        self.assert_one_owner(self.win)

    # skewed clocks -----------------------------------------------------------------------------

    def test_skewed_clocks_still_give_one_owner(self) -> None:
        for skew in (-120000, -5000, -1, 0, 1, 5000, 120000):
            with self.subTest(skew=skew):
                self.setUp()
                self.pi._skew_ms = skew
                self.claims_at_once(self.pi, self.win)
                self.assert_one_owner(self.pi if skew < 0 else self.win)

    def test_owner_yields_to_an_earlier_stamp_that_came_late(self) -> None:
        # The Windows clock runs 10 s behind; it claims after the Pi already owns (its probe
        # missed the ACK). Its stamp is earlier, so the Pi stands down: still one owner.
        self.boot(self.pi)
        self.settle()
        self.assert_one_owner(self.pi)
        self.win._skew_ms = -10000
        self.win._probe_and_confirm_override = lambda: "ok"
        self.win._enter_enabled(force=False, from_boot=False)
        self.settle()
        self.assert_one_owner(self.win)

    def test_owner_keeps_against_a_later_stamp_and_says_so(self) -> None:
        self.boot(self.pi)
        self.settle()
        self.win._probe_and_confirm_override = lambda: "ok"
        self.win._enter_enabled(force=False, from_boot=False)
        self.settle()
        self.assert_one_owner(self.pi)
        self.assertEqual(self.broker.log[-1].split()[:2], ["enabled", "rpi-jmri"])

    def test_force_override_still_takes_over(self) -> None:
        self.boot(self.pi)
        self.settle()
        self.win._probe_and_confirm_override = lambda: "force"
        self.win._enter_enabled(force=False, from_boot=False)
        self.settle()
        self.assert_one_owner(self.win)
        self.assertIn("enabling minipc-e5h6x %d force" % self.win._claim[0], self.broker.log)
        self.assertIn("aborted", self.broker.log)

    # one host late ---------------------------------------------------------------------------------

    def test_late_host_sees_enabled_and_stays_disabled(self) -> None:
        self.boot(self.pi)
        self.settle()
        self.stale(self.win, self.broker.retained[CLAIM])  # the retained values at subscribe
        self.boot(self.win)
        self.settle()
        self.assert_one_owner(self.pi)

    def test_late_host_during_the_claim_stays_disabled(self) -> None:
        self.boot(self.pi)
        self.run_named("_Boot")  # the Pi claimed; its Hold has not run yet
        self.broker.deliver()
        self.boot(self.win)
        self.settle()
        self.assert_one_owner(self.pi)

    def test_claim_heard_between_boot_read_and_claim(self) -> None:
        # Windows' boot thread reads the mode and claims as one step under the claim lock, so
        # a Pi claim landing then is either heard first (no claim) or compared after.
        self.boot(self.pi, self.win)
        self.run_named("_Boot")
        self.settle()
        self.assertEqual(len(self.owners()), 1)

    # bridge release ------------------------------------------------------------------------------

    def test_bridge_release_with_both_hosts_idle_gives_one_owner(self) -> None:
        # Power cut: both boot on the stale retained enabled; nobody answers the bridge.
        for c in (self.pi, self.win):
            self.stale(c, "enabled rpi-jmri %d" % (T0 - 60000))
        self.boot(self.win)
        self.settle()
        self.assertEqual(self.owners(), [])
        self.broker.bridge("query", "disabling", "disabled")
        self.settle()
        self.assert_one_owner(self.win)  # both claimed at the same ms on "disabled"

    def test_bridge_query_during_the_race(self) -> None:
        self.broker.hold = True
        self.boot(self.pi, self.win)
        self.run_named("_Boot")
        self.broker.queue.append((SML, "query", False))
        self.settle()
        self.assert_one_owner(self.win)

    # old retained payloads ------------------------------------------------------------------------

    def test_old_retained_enabled_keeps_both_hosts_disabled_until_the_bridge_releases(self) -> None:
        for c in (self.pi, self.win):
            c.notifyMqttMessage(SML, "enabled")  # retained from before the deploy
        self.assertEqual(self.pi._retained_mode, "enabled")
        self.boot(self.pi, self.win)
        self.settle()
        self.assertEqual(self.owners(), [])
        self.broker.bridge("query", "disabling", "disabled")
        self.settle()
        self.assertEqual(len(self.owners()), 1)

    def test_old_retained_enabling_is_not_a_rival_for_a_claimant(self) -> None:
        self.boot(self.pi)
        self.run_named("_Boot")
        self.pi.notifyMqttMessage(SML, "enabling")  # no host: from before the deploy
        self.pi.notifyMqttMessage(SML, "enabled")
        self.settle()
        self.assert_one_owner(self.pi)

    def test_own_stale_enabled_lets_this_host_take_at_boot(self) -> None:
        # The Pi died while owning; its own retained enabled is not another host's.
        self.stale(self.pi, "enabled rpi-jmri %d" % (T0 - 60000))
        self.boot(self.pi)
        self.settle()
        self.assert_one_owner(self.pi)

    def test_other_hosts_stale_enabled_keeps_boot_disabled(self) -> None:
        self.stale(self.pi, "enabled minipc-e5h6x %d" % (T0 - 60000))
        self.boot(self.pi)
        self.settle()
        self.assertEqual(self.owners(), [])

    # stored-Enabled tables -----------------------------------------------------------------------

    def test_stored_dests_claim_beats_a_stale_retained_claim(self) -> None:
        c = self.pi
        c.logic.enabled["Mast 8RA"] = True
        c._stamp_claim(force=True)  # start() stamps before subscribe
        self.stale(c, "enabling minipc-e5h6x %d" % (T0 - 1000))  # stale, not forced
        self.assertIsNotNone(c._claim)
        c._announce_enabling("stored dests", force=True)
        c._schedule_enabled_after_enabling()
        self.settle()
        self.assert_one_owner(c)

    def test_two_stored_dests_boots_give_one_owner(self) -> None:
        self.win._skew_ms = -1
        for c in (self.pi, self.win):
            c.logic.enabled["Mast 8RA"] = True
            c._announce_enabling("stored dests", force=True)
            c._schedule_enabled_after_enabling()
        self.settle()
        self.assert_one_owner(self.win)

    def test_forced_owner_is_ranked_the_same_on_both_hosts(self) -> None:
        # Review: the owner ranked itself as forced while its enabled dropped " force", so
        # the other host saw a larger key and both kept taking.
        self.boot(self.pi)
        self.settle()
        self.win._probe_and_confirm_override = lambda: "force"
        self.win._enter_enabled(force=False, from_boot=False)
        self.settle()
        self.assert_one_owner(self.win)
        self.assertTrue(self.broker.retained[CLAIM].endswith(" force"))
        self.pi._skew_ms = -5000  # a normal take with an earlier stamp, probe missed
        self.pi._probe_and_confirm_override = lambda: "ok"
        n = len(self.broker.log)
        self.pi._enter_enabled(force=False, from_boot=False)
        self.settle()
        self.assert_one_owner(self.win)
        self.assertLess(len(self.broker.log) - n, 10)  # no endless re-announce

    def test_no_enabled_without_a_claim(self) -> None:
        self.pi._publish_mode("enabled")
        self.assertEqual(self.pi.mqtt.published, [])

    def test_quit_release_failure_clears_releasing(self) -> None:
        self.boot(self.pi)
        self.settle()

        def boom(on):
            raise RuntimeError("layout")

        self.pi._set_all_digicon_sml_destinations = boom
        with self.assertRaises(RuntimeError):
            self.pi._release_on_quit()
        self.assertFalse(self.pi._releasing)

    def test_owner_disabling_yields_to_a_later_claim(self) -> None:
        self.boot(self.pi)
        self.settle()
        self.pi._enter_disabled(release=True)
        disable = jf.Thread.started.pop(0)
        self.win._probe_and_confirm_override = lambda: "ok"
        self.win._enter_enabled(force=False, from_boot=False)
        self.broker.hold = True
        self.run_named("_Run")  # Windows claims (its Hold sleeps without delivery)
        self.broker.hold = False
        disable.runnable.run()  # the Pi's Disable hears the claim during its Hold
        self.settle()
        self.assertEqual([c._host for c in self.owners()], ["minipc-e5h6x"])
        self.assertNotEqual(self.broker.retained[SML], "disabled")


class _Latch:
    """CountDownLatch: await_ answers as the test set it (True once counted down)."""

    times_out = False
    made = []

    def __init__(self, n):
        self.n = n
        self.waited = None
        _Latch.made.append(self)

    def countDown(self):
        self.n -= 1

    def await_(self, amount, unit):
        self.waited = (amount, unit)
        return self.n <= 0 and not _Latch.times_out


class _Sleeps(jf.Thread):
    """Thread whose sleep() records what the layout looks like at that moment."""

    log = []
    probe = staticmethod(lambda: None)

    @staticmethod
    def sleep(ms):
        _Sleeps.log.append((ms, _Sleeps.probe()))


class Sequences(unittest.TestCase):
    """Hold, wait, then act: the Enable, Disable and quit releases, and the bulk SML set."""

    enroll = Coordinator.enroll
    sent = Coordinator.sent

    def setUp(self) -> None:
        Coordinator.setUp(self)
        c = self.c
        del c._set_all_digicon_sml_destinations  # the real bulk set, not the recorder
        self.real_bulk = c._set_all_digicon_sml_destinations
        self.bulk = []

        def bulk(on):
            self.bulk.append((on, self.mast.held))
            self.logic.enabled["Mast 8RA"] = on

        c._set_all_digicon_sml_destinations = bulk
        _Sleeps.log = []
        _Sleeps.probe = staticmethod(lambda: (self.mast.held, list(self.sent()), list(self.bulk)))
        _Latch.made = []
        _Latch.times_out = False
        self.sc["Thread"] = _Sleeps
        self.out = io.StringIO()
        stack = contextlib.ExitStack()
        stack.enter_context(contextlib.redirect_stdout(self.out))
        self.addCleanup(stack.close)

    def own(self):
        self.enroll()
        self.c._global_enabled = True
        self.c._snapshot_mast_sml_state()
        self.logic.enabled["Mast 8RA"] = True

    def hold_probe(self, fn):
        _Sleeps.probe = staticmethod(fn)

    # --- quit ----------------------------------------------------------------------------

    def test_quit_holds_waits_then_unhelds_and_disables(self) -> None:
        self.own()
        self.c._on_jmri_shutdown()
        self.assertEqual(_Sleeps.log, [(self.sc["HOLD_WAIT_MS"], (True, [], []))])
        self.assertEqual(self.sent(), [("track/signalhead/432", "Unheld", True),
                                       ("track/bridge/sml_mode", "disabled", True)])
        self.assertEqual(self.bulk, [(False, True)])  # pairs off while still held
        self.assertFalse(self.mast.held)
        c = self.c
        self.assertEqual((c._global_enabled, c._enabling_originator, c._claim), (False, False, None))
        self.assertEqual((c._busy, c._releasing, c._shutting_down, c._shutdown_released),
                         (False, False, True, True))

    def test_hold_wait_is_three_seconds(self) -> None:
        self.assertEqual(self.sc["HOLD_WAIT_MS"], 3000)

    def test_quit_skips_when_digicon_is_not_enabled(self) -> None:
        self.enroll()
        self.logic.enabled["Mast 8RA"] = False
        self.c._on_jmri_shutdown()
        self.assertEqual((self.sent(), _Sleeps.log, self.bulk), ([], [], []))
        self.assertTrue(self.c._shutdown_released)
        self.assertIn("shutdown skip (SML not enabled)", self.out.getvalue())

    def test_quit_skips_while_another_agent_is_taking_digicon(self) -> None:
        self.own()
        self.c._abort_in_progress = True
        self.c._on_jmri_shutdown()
        self.assertEqual((self.sent(), _Sleeps.log, self.bulk), ([], [], []))
        self.assertTrue(self.c._shutdown_released)

    def test_quit_runs_once_for_the_window_and_the_shutdown_task(self) -> None:
        self.own()
        self.c._on_jmri_shutdown()
        n = len(self.sent())
        self.c._on_jmri_shutdown()
        self.assertEqual((len(self.sent()), len(_Sleeps.log)), (n, 1))

    def test_a_failed_quit_release_is_printed_not_raised_and_can_be_retried(self) -> None:
        self.own()

        def boom(on):
            raise RuntimeError("layout hung")

        self.c._set_all_digicon_sml_destinations = boom
        self.c._on_jmri_shutdown()
        self.assertIn("shutdown task failed: layout hung", self.out.getvalue())
        self.assertEqual((self.c._busy, self.c._releasing, self.c._shutdown_released),
                         (False, False, False))
        # Unheld and disabled go out before the pairs are touched, so a hang cannot skip them.
        self.assertEqual(self.sent()[-1], ("track/bridge/sml_mode", "disabled", True))
        before = list(self.sent())
        self.c._set_all_digicon_sml_destinations = lambda on: self.bulk.append((on, self.mast.held))
        self.c._on_jmri_shutdown()
        self.assertFalse(self.mast.held)
        self.assertTrue(self.c._shutdown_released)
        # The head's Unheld is not sent again; only the mode word repeats.
        self.assertEqual(self.sent()[len(before):], [("track/bridge/sml_mode", "disabled", True)])

    def test_quit_release_goes_on_when_a_mast_cannot_hold(self) -> None:
        self.own()

        def broken(value):
            raise RuntimeError("no hold")

        self.mast.setHeld = broken
        self.c._on_jmri_shutdown()
        self.assertEqual(self.sent()[-1], ("track/bridge/sml_mode", "disabled", True))

    def test_shutdown_task_call_and_run_both_ask_the_controller(self) -> None:
        c = self.c
        task = self.sc["DigiconSmlQuitTask"]("Digicon SML quit")
        task._controller = c
        calls = []
        c._on_jmri_shutdown = lambda: calls.append(1)
        self.assertTrue(task.call())
        task.run()
        self.assertEqual(calls, [1, 1])

        def boom():
            raise RuntimeError("gone")

        c._on_jmri_shutdown = boom
        self.assertTrue(task.call())  # a failing release never stops JMRI quitting
        task.run()
        self.assertIn("ShutDownTask call failed: gone", self.out.getvalue())
        self.assertIn("ShutDownTask run failed: gone", self.out.getvalue())

    def test_shutdown_task_without_its_own_controller_uses_the_global(self) -> None:
        calls = []
        self.sc["controller"] = types.SimpleNamespace(_on_jmri_shutdown=lambda: calls.append(1))
        task = self.sc["DigiconSmlQuitTask"]("Digicon SML quit")
        task.call()
        self.assertEqual(calls, [1])

    def test_registering_the_task_and_the_window_hook(self) -> None:
        self.layout.button_space = _Space()
        self.c._register_shutdown_task()
        self.assertEqual(self.layout.shutdown.tasks, [self.c._shutdown_task])
        self.assertIs(self.c._shutdown_task._controller, self.c)
        self.assertEqual(len(self.layout.button_space.frame.listeners), 1)
        self.assertIs(self.c._close_frame, self.layout.button_space.frame)

    def test_window_closing_starts_the_quit_worker_without_sleeping_inline(self) -> None:
        self.own()
        self.layout.button_space = _Space()
        self.c._add_quit_window_hook()
        jf.Thread.started.clear()
        self.layout.button_space.frame.listeners[0].windowClosing(None)
        self.assertEqual(len(jf.Thread.started), 1)
        self.assertEqual((_Sleeps.log, self.sent()), ([], []))
        jf.run_threads()
        self.assertEqual(len(_Sleeps.log), 1)
        self.assertEqual(self.sent()[-1], ("track/bridge/sml_mode", "disabled", True))

    def test_no_main_window_means_no_close_hook(self) -> None:
        self.layout.button_space = None
        self.c._add_quit_window_hook()
        self.assertIsNone(self.c._close_frame)
        self.assertIn("no main frame", self.out.getvalue())

    # --- Disable --------------------------------------------------------------------------

    def run_disable(self, release):
        self.c._enter_disabled(release=release)
        self.assertTrue(self.c._busy)  # the worker is queued, not run
        jf.run_threads()

    def test_disable_holds_waits_pairs_off_unhelds_then_publishes_disabled(self) -> None:
        self.own()
        self.run_disable(True)
        self.assertEqual(_Sleeps.log, [(self.sc["HOLD_WAIT_MS"], (True, [], []))])
        self.assertEqual(self.bulk, [(False, True)])
        self.assertEqual(self.sent(), [("track/signalhead/432", "Unheld", True),
                                       ("track/bridge/sml_mode", "disabled", True)])
        self.assertFalse(self.mast.held)
        self.assertFalse(self.c._global_enabled)
        self.assertEqual((self.c._busy, self.c._releasing), (False, False))

    def test_disable_without_release_sends_no_unheld(self) -> None:
        self.own()
        self.run_disable(False)
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "disabled", True)])

    def test_disable_aborted_in_the_hold_sends_nothing(self) -> None:
        self.own()
        c = self.c
        self.hold_probe(lambda: setattr(c, "_abort_gen", c._abort_gen + 1))
        self.run_disable(True)
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.bulk, [(False, True)])  # pairs still go off, then the abort is seen
        self.assertFalse(self.mast.held)
        self.assertIn("aborted during Disable", self.out.getvalue())

    def test_disable_is_ignored_while_a_worker_runs(self) -> None:
        self.own()
        self.c._busy = True
        self.c._enter_disabled(release=True)
        self.assertEqual(jf.Thread.started, [])

    # --- Enable ---------------------------------------------------------------------------

    def run_enable(self):
        self.enroll()
        self.c._enter_enabled(force=True, from_boot=True)
        jf.run_threads()

    def test_enable_holds_waits_pairs_on_then_publishes_enabled(self) -> None:
        self.run_enable()
        self.assertEqual(_Sleeps.log[0][0], self.sc["HOLD_WAIT_MS"])
        self.assertTrue(_Sleeps.log[0][1][0])  # held during the wait
        self.assertEqual(self.bulk, [(True, True)])  # pairs go on while still held
        self.assertFalse(self.mast.held)
        self.assertTrue(self.c._global_enabled)
        self.assertIn(("track/bridge/sml_mode", "enabled", True), self.sent())
        self.assertEqual((self.c._busy, self.c._enabling_originator), (False, False))

    def test_enable_loses_to_a_claim_dropped_in_the_hold(self) -> None:
        c = self.c
        self.hold_probe(lambda: setattr(c, "_claim", None))
        self.run_enable()
        self.assertEqual(self.bulk, [])
        self.assertFalse(c._global_enabled)
        self.assertFalse(self.mast.held)
        self.assertNotIn(("track/bridge/sml_mode", "enabled", True), self.sent())

    def test_enable_aborted_in_the_hold_leaves_the_pairs(self) -> None:
        c = self.c
        self.hold_probe(lambda: setattr(c, "_abort_gen", c._abort_gen + 1))
        self.run_enable()
        self.assertEqual(self.bulk, [])
        self.assertFalse(c._global_enabled)
        self.assertFalse(c._enabling_originator)
        self.assertFalse(self.mast.held)

    def test_enable_taken_over_while_the_pairs_go_on_puts_them_off(self) -> None:
        c = self.c
        record = c._set_all_digicon_sml_destinations

        def bulk(on):
            record(on)
            if on:
                c._abort_gen += 1

        c._set_all_digicon_sml_destinations = bulk
        self.run_enable()
        self.assertEqual([on for on, _ in self.bulk], [True, False])
        self.assertFalse(self.mast.held)
        self.assertNotIn(("track/bridge/sml_mode", "enabled", True), self.sent())

    def test_enable_does_nothing_while_busy_or_shutting_down(self) -> None:
        self.enroll()
        for attr in ("_busy", "_shutting_down"):
            setattr(self.c, attr, True)
            self.c._enter_enabled(force=True, from_boot=True)
            setattr(self.c, attr, False)
        self.assertEqual((jf.Thread.started, self.sent(), _Sleeps.log), ([], [], []))

    def test_enable_resume_without_its_claim_takes_nothing(self) -> None:
        self.enroll()
        self.c._enter_enabled(force=True, from_boot=True, resume=True)
        self.assertEqual(jf.Thread.started, [])
        self.assertIn("enabling lost to another host", self.out.getvalue())

    def test_enable_after_a_shutdown_began_is_skipped_in_the_worker(self) -> None:
        self.enroll()
        self.c._enter_enabled(force=True, from_boot=True)
        self.c._shutting_down = True
        jf.run_threads()
        self.assertEqual((_Sleeps.log, self.bulk), ([], []))

    # --- bulk SML set ----------------------------------------------------------------------

    def fake_layout_thread(self, on_layout, times_out=False, run_on_layout=None):
        """jmri.util.ThreadingUtil and java.util.concurrent as the script imports them."""
        ran = []

        class ThreadAction:
            pass

        def default_run(action):
            ran.append(1)
            action.run()

        _Latch.times_out = times_out
        concurrent = types.ModuleType("java.util.concurrent")
        concurrent.CountDownLatch = _Latch
        concurrent.TimeUnit = types.SimpleNamespace(SECONDS="s")
        util = types.ModuleType("java.util")
        util.concurrent = concurrent
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(jf.fake_modules({"java.util": util, "java.util.concurrent": concurrent}))
        jutil = sys.modules["jmri.util"]
        saved = jutil.ThreadingUtil
        jutil.ThreadingUtil = types.SimpleNamespace(
            ThreadAction=ThreadAction,
            isLayoutThread=lambda: on_layout,
            runOnLayout=run_on_layout or default_run,
        )
        self.addCleanup(setattr, jutil, "ThreadingUtil", saved)
        return ran

    def two_dests(self):
        logic = FakeLogic(self.mast, "Mast 8RA", "Mast 9RA")
        logic.enabled["Mast 9RA"] = False
        self.c._smls = [logic]
        return logic

    def test_bulk_set_flips_only_the_pairs_that_differ(self) -> None:
        logic = self.two_dests()
        self.c._shutting_down = True  # runs on this thread, no layout hop
        self.real_bulk(False)
        self.assertEqual(logic.enabled, {"Mast 8RA": False, "Mast 9RA": False})
        self.assertIn("SML pairs disabled (1)", self.out.getvalue())
        self.real_bulk(True)
        self.assertEqual(logic.enabled, {"Mast 8RA": True, "Mast 9RA": True})
        self.assertIn("SML pairs enabled (2)", self.out.getvalue())
        self.real_bulk(True)
        self.assertIn("SML pairs enabled (0)", self.out.getvalue())

    def test_bulk_set_skips_a_source_or_pair_that_fails(self) -> None:
        good = self.two_dests()

        class Broken:
            def getDestinationList(self):
                raise RuntimeError("no list")

        class NoDests:
            def getDestinationList(self):
                return None

        class Empty:
            def getDestinationList(self):
                return _List([])

        bad_pair = FakeLogic(self.mast, "Mast 1RA", "Mast 2RA")

        def refuse(dest):
            raise RuntimeError("one pair")

        bad_pair.setDisabled = refuse
        self.c._smls = [Broken(), NoDests(), Empty(), bad_pair, good]
        self.c._shutting_down = True
        self.real_bulk(False)
        self.assertEqual(good.enabled, {"Mast 8RA": False, "Mast 9RA": False})
        self.assertIn("getDestinationList: no list", self.out.getvalue())
        self.assertIn("one pair", self.out.getvalue())

    def test_bulk_set_without_the_java_classes_runs_on_the_calling_thread(self) -> None:
        logic = self.two_dests()
        self.real_bulk(False)
        self.assertEqual(logic.enabled, {"Mast 8RA": False, "Mast 9RA": False})
        self.assertIn("SML bulk set fallback", self.out.getvalue())

    def test_bulk_set_on_the_layout_thread_runs_inline(self) -> None:
        ran = self.fake_layout_thread(on_layout=True)
        logic = self.two_dests()
        self.real_bulk(False)
        self.assertEqual((ran, logic.enabled["Mast 8RA"]), ([], False))

    def test_bulk_set_hops_to_the_layout_thread_and_waits_30_seconds(self) -> None:
        ran = self.fake_layout_thread(on_layout=False)
        logic = self.two_dests()
        self.real_bulk(False)
        self.assertEqual((ran, logic.enabled["Mast 8RA"]), ([1], False))
        self.assertEqual(_Latch.made[0].waited, (30, "s"))
        self.assertNotIn("timed out", self.out.getvalue())

    def test_bulk_set_reports_a_timeout_and_does_not_run_it_twice(self) -> None:
        queued = []
        self.fake_layout_thread(on_layout=False, times_out=True,
                                run_on_layout=queued.append)  # the layout thread is stuck
        logic = self.two_dests()
        self.real_bulk(False)
        self.assertIn("SML bulk set timed out on layout thread", self.out.getvalue())
        self.assertEqual(logic.enabled["Mast 8RA"], True)  # nothing ran on this thread
        self.assertEqual(len(queued), 1)

    def test_bulk_set_falls_back_when_the_hop_fails_before_running(self) -> None:
        def refuse(action):
            raise RuntimeError("no layout thread")

        self.fake_layout_thread(on_layout=False, run_on_layout=refuse)
        logic = self.two_dests()
        self.real_bulk(False)
        self.assertEqual(logic.enabled["Mast 8RA"], False)
        self.assertIn("SML bulk set fallback: no layout thread", self.out.getvalue())

    def test_bulk_set_does_not_repeat_work_that_already_ran(self) -> None:
        def run_then_fail(action):
            action.run()
            raise RuntimeError("late")

        self.fake_layout_thread(on_layout=False, run_on_layout=run_then_fail)
        logic = self.two_dests()
        self.real_bulk(False)
        self.assertEqual(self.out.getvalue().count("SML pairs disabled"), 1)
        self.assertIn("SML bulk set fallback: late", self.out.getvalue())
        self.assertEqual(logic.enabled["Mast 8RA"], False)


    # --- failures that must still unhold the masts and release ---------------------------------

    def test_quit_release_unholds_and_resets_when_the_bulk_set_raises(self) -> None:
        self.own()

        def boom(on):
            raise RuntimeError("layout hung")

        self.c._set_all_digicon_sml_destinations = boom
        self.c._on_jmri_shutdown()
        self.assertFalse(self.mast.held)
        self.assertEqual((self.c._global_enabled, self.c._claim), (False, None))

    def test_disable_unholds_and_publishes_disabled_when_the_bulk_set_raises(self) -> None:
        self.own()

        def boom(on):
            raise RuntimeError("attach failed")

        self.c._set_all_digicon_sml_destinations = boom
        self.run_disable(True)
        self.assertFalse(self.mast.held)
        self.assertFalse(self.c._global_enabled)
        self.assertIn(("track/bridge/sml_mode", "disabled", True), self.sent())

    def test_disable_aborted_in_the_hold_stays_silent_even_when_the_bulk_set_raises(self) -> None:
        self.own()
        c = self.c

        def boom(on):
            raise RuntimeError("attach failed")

        c._set_all_digicon_sml_destinations = boom
        self.hold_probe(lambda: setattr(c, "_abort_gen", c._abort_gen + 1))
        self.run_disable(True)
        self.assertEqual(self.sent(), [])
        self.assertFalse(self.mast.held)

    def test_timed_out_bulk_set_does_nothing_when_the_layout_thread_gets_to_it(self) -> None:
        # After the 30 s wait gives up, the queued work must not re-check pairs later.
        queued = []
        self.fake_layout_thread(on_layout=False, times_out=True, run_on_layout=queued.append)
        logic = self.two_dests()
        self.real_bulk(False)
        logic.enabled["Mast 8RA"] = True  # another host took Digicon since
        for action in queued:
            action.run()  # the layout thread gets to it late
        self.assertTrue(logic.enabled["Mast 8RA"])


if __name__ == "__main__":
    unittest.main()
