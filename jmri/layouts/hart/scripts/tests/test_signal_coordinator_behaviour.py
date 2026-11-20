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
        self.c.notifyMqttMessage("track/bridge/sml_mode", "query")
        self.assertEqual(self.sent(), [])
        self.c._global_enabled = True
        self.c.notifyMqttMessage("track/bridge/sml_mode", "query")
        self.assertEqual(self.sent(), [("track/bridge/sml_mode", "enabled", True)])

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
        self.c._enabling_originator = True
        self.c.notifyMqttMessage("track/bridge/sml_mode", "enabling")
        self.assertEqual(self.sent(), [])
        self.assertEqual(self.bulk, [])

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


if __name__ == "__main__":
    unittest.main()
