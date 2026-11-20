"""signal_coordinator.py behaviour (jmri/scripts), run against an in-memory JMRI (jmri_fake).

Covers the decisions that reach the field: when the Digicon hand-off sends a head SET or
Unheld, when a field report repaints a head and mast, and how sml_mode messages are
answered. The MQTT adapter here only records what the script would send; nothing
reaches a broker. The source-text checks stay in cats/scripts/tests/test_signal_coordinator.py.
"""
from __future__ import annotations

import contextlib
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
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "enabled rpi-jmri %d" % T0, True)])

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
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling minipc-e5h6x %d force" % T0)
        jf.run_threads()
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "aborting", True),
                                       ("track/bridge/sml_mode", "aborted", True)])
        self.assertEqual(self.bulk, [False])
        self.assertFalse(self.c._global_enabled)

    def test_own_enabling_does_not_abort(self) -> None:
        self.c._host = "rpi-jmri"
        self.c._stamp_claim()
        jf.Thread.started.clear()
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling rpi-jmri %d" % self.c._claim[0])
        self.assertEqual(jf.Thread.started, [])  # no abort worker
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
        self.assertEqual(gone, {"track/bridge/sml_mode", "track/signalmast/#", "track/signalhead/#"})
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
        sent = [p for t, p, r in self.layout.adapter.published if t == SML]
        self.assertEqual(sent, [])
        self.assertFalse(self.mast.held)

    def test_rerun_on_an_idle_host_boots_as_before(self) -> None:
        first = self.load_running()  # still in its boot read: not owning
        self.assertIsNone(self.sc["_owned_claim"](first))
        self.assertIsNone(self.sc["_owned_claim"](object()))  # a controller from an older copy


# --- two hosts racing for Digicon (owner decision 2026-11-19) -------------------------

SML = "track/bridge/sml_mode"
T0 = 1_763_590_000_000  # epoch ms; the hosts compare stamps only with each other


class _Broker:
    """One broker for the sml_mode topic: every host gets every message, in one order.

    A publish is queued; `deliver()` hands each message to every host (the publisher too,
    as a broker echoes to a subscribed client) and keeps the last retained one. A
    sleeping thread lets time pass and delivers what is queued, unless `hold` is set:
    claims made while held are "at once". Nothing here touches a network.
    """

    def __init__(self):
        self.queue, self.log, self.hosts = [], [], []
        self.retained = None
        self.hold = False
        self.now = T0  # real time; each host adds its own clock skew
        self._delivering = False

    def adapter(self):
        broker = self

        class _Adapter(jf.RecordingAdapter):
            def publish(self, topic, payload, retain=True):
                super().publish(topic, payload, retain)
                if topic == SML:
                    broker.queue.append((payload, retain))

        return _Adapter()

    def bridge(self, *payloads):
        """The LCOS bridge publishes each payload; each is delivered before the next."""
        for p in payloads:
            self.queue.append((p, p != "query"))
            self.deliver()

    def deliver(self):
        if self._delivering:
            return
        self._delivering = True
        try:
            while self.queue:
                payload, retain = self.queue.pop(0)
                self.log.append(payload)
                if retain:
                    self.retained = payload
                for host in list(self.hosts):
                    host.notifyMqttMessage(SML, payload)
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
        self.assertEqual(self.broker.retained.split()[:2], ["enabled", who._host])

    def claims_at_once(self, *hosts):
        """Boot the hosts so each claims before it hears the other."""
        self.broker.hold = True
        self.boot(*hosts)
        self.run_named("_Boot")
        self.assertEqual(sum(1 for p, _ in self.broker.queue if p.startswith("enabling")), len(hosts))
        self.settle()

    # payload -------------------------------------------------------------------------------

    def test_enabling_and_enabled_carry_host_and_stamp(self) -> None:
        self.boot(self.pi)
        self.settle()
        stamp = T0 + 1000  # after the boot read wait
        self.assertIn("enabling rpi-jmri %d" % stamp, self.broker.log)
        self.assertEqual(self.broker.retained, "enabled rpi-jmri %d" % stamp)

    def test_the_first_word_is_the_bridge_token(self) -> None:
        # The bridge reads the mode from the payload; with this change it must take the
        # first word (see the PR body). Every payload sent starts with a bridge token.
        self.claims_at_once(self.pi, self.win)
        for p in self.broker.log:
            self.assertIn(p.split()[0], ("enabling", "enabled", "aborting", "aborted",
                                         "disabling", "disabled", "query"))

    def test_parse_old_and_new_payloads(self) -> None:
        parse = self.sc["_parse_sml_mode"]
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
        self.win.notifyMqttMessage(SML, self.broker.retained)  # the retained value at subscribe
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
            c.notifyMqttMessage(SML, "enabled rpi-jmri %d" % (T0 - 60000))
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
        self.broker.queue.append(("query", False))
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
        self.pi.notifyMqttMessage(SML, "enabled rpi-jmri %d" % (T0 - 60000))
        self.boot(self.pi)
        self.settle()
        self.assert_one_owner(self.pi)

    def test_other_hosts_stale_enabled_keeps_boot_disabled(self) -> None:
        self.pi.notifyMqttMessage(SML, "enabled minipc-e5h6x %d" % (T0 - 60000))
        self.boot(self.pi)
        self.settle()
        self.assertEqual(self.owners(), [])

    # stored-Enabled tables -----------------------------------------------------------------------

    def test_stored_dests_claim_beats_a_stale_retained_claim(self) -> None:
        c = self.pi
        c.logic.enabled["Mast 8RA"] = True
        c._stamp_claim(force=True)  # start() stamps before subscribe
        c.notifyMqttMessage(SML, "enabling minipc-e5h6x %d" % (T0 - 1000))  # stale, not forced
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
        self.assertNotEqual(self.broker.retained, "disabled")


if __name__ == "__main__":
    unittest.main()
