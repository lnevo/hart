# JMRI jython -- Digicon MQTT <-> SML hand-off (publisher + receiver + global toggle).
#
# Global toggle: SML Enabled / SML Disabled (main window button).
#   Enabled  -> publish appearances on track/signalhead/<packed> (SET)
#   Disabled -> apply track/signalmast/<packed> to IH heads; no SET
# Per-mast SML dest Enable off -> Unheld that source's heads; mast MQTT -> IH + mast.
# Re-check Enable -> Digicon SET. Global Disable still owns the bulk Unheld burst.
#
# Boot (read topic only -- no MQTT retain publish, except stored-Enabled):
#   If Digicon dests loaded Enabled (stored tables): popup, publish
#   enabling. That instance does not abort -- dests stay on. Other
#   agents that see the token publish aborting, uncheck immediately
#   (no Hold/Red/Unheld), then aborted, and stay Disabled. Solo boot has
#   nobody to abort (correct). After SML_ABORT_RESUME_MS the originator
#   Holds, then publishes enabled. If that never happens, the LCOS bridge
#   challenges. Clean boot: hold Digicon SML off until track/bridge/sml_mode
#   is seen.
#   missing / disabled / query / disabling -> take Digicon (enable SML; announce enabled).
#   enabled / enabling / aborting / aborted -> stay Disabled (originator owns resume).
#   Later, the bridge's release (disabling then disabled) while this instance is
#   idle runs the take again, so a stale retained enabled cannot leave every host
#   Disabled. A bare disabled (operator Disable elsewhere) is left alone.
# Claims (owner decision 2026-11-19): sml_mode payloads stay the bare words the
#   LCOS bridge reads. Each enabling / enabled is followed by a retained claim on
#   track/bridge/sml_claim, which only the coordinators read: "enabling <host>
#   <epoch-ms>" (" force" added for Force override and stored dests), and
#   "enabled <host> <same ms>". The bare word goes first, so another host hears
#   "someone is taking" before it can compare claims. When two hosts claim at
#   once, the smaller key wins: force first, then the earlier stamp, then the
#   host name. Stamps are only compared with each other, never with this
#   host's clock, so a skewed clock changes who wins but never lets both own.
#   The loser of a pending claim cancels its Hold quietly; an owner yields to a
#   smaller key (abort) and answers a larger one with its enabled again. While
#   claiming, a bare enabling / enabled on sml_mode is left to the claim topic.
#   At boot, a retained enabled whose last claim names this host was left by
#   this host's own earlier run.
# Abort runs on a worker thread (it waits on the layout thread; the MQTT callback
#   thread must not). A Disable/Enable worker that an abort overtakes publishes no
#   Unheld, no disabled and no enabled.
# Re-running the script detaches the earlier controller (listeners, MQTT
#   subscriptions, quit task, window hook, button) before the new one starts.
# Operator Enable when sml_mode is already enabled: force-override popup;
#   Yes publishes enabling (same abort for other agents) then enabled.
# Query or disabling ACK while this instance owns or is taking Digicon
#   (including Enable/Disable/quit Hold) so the LCOS bridge can suspend RELEASE.
# Quit (ShutDownTask.call + main-window close): if this instance still owns
#   Digicon, Hold / wait / Unheld then sml_mode disabled, then pairs off (a layout
#   hang cannot skip RELEASE; JMRI is exiting). Work is in call() because JMRI
#   run() is after windows close. Abort does not RELEASE.
# Never two owners: Disable sends `disabled` only once every pair is off, and
#   Enable sends `enabled` only once every pair is on (or, after a failed Enable,
#   could not be turned off again). A failed Disable keeps this host the owner
#   (pairs back on, enabled again). A recovery that announces enabled with some
#   pairs off sends Unheld for the heads of masts with no enabled dest.
#
# Topic leaf is packed digits only (IH432 -> .../432). Beans stay IH*.
# Digicon plants: SignalMasts that carry LCOS Virtual IH heads (UID 32-47) in
# JMRI tables — no hardcoded HEAD_NAMES. MQTT SET/Unheld/paint still requires
# enrollment from track/signalmast/<packed> (bridge + field status up).

import java
import jmri
import sys
import threading
import time
from java.beans import PropertyChangeListener
from java.lang import Runnable, Thread
from javax.swing import JButton, JOptionPane, SwingUtilities
from jmri.jmrix.mqtt import MqttEventListener

# Sibling modules beside this script in preference:jython, in load order: each comes after
# every module it imports. The deploy ships each one beside it
# (tools/hosts/tests/test_coordinator_shipping.py holds every host's list to this tuple).
SIBLING_MODULES = (
    "sml_beans",
    "sml_claims",
    "sml_handoff",
)


class SiblingModuleError(ImportError):
    """A sibling module is missing from the jython folder, or was loaded from another one."""


try:
    _reload = reload  # Jython 2.7: a builtin
except NameError:  # CPython 3, where the tests run the script
    from importlib import reload as _reload


def _load_siblings(names):
    """Import each sibling from preference:jython, or reload it if an earlier run imported it.

    JMRI runs this script with no __file__ and without its folder on sys.path, so the folder
    is added. A re-run in the same JMRI would otherwise get the modules the earlier run
    cached: a redeployed script with the old modules. Every file is found and compiled
    before any is loaded, so a missing or broken one stops a re-run before it reloads the
    earlier run's modules under its live controller.
    """
    import os

    folder = jmri.util.FileUtil.getExternalFilename("preference:jython")
    if not folder or not os.path.isdir(folder):
        raise SiblingModuleError(
            "signal_coordinator: no jython folder (preference:jython is %r)" % (folder,)
        )
    if folder not in sys.path:
        sys.path.insert(0, folder)
    want = os.path.normcase(os.path.realpath(folder))
    for name in names:
        path = os.path.join(folder, name + ".py")
        if not os.path.isfile(path):
            raise SiblingModuleError(
                "signal_coordinator: %s.py is missing from %s; the deploy ships it beside "
                "this script" % (name, folder)
            )
        try:
            with open(path) as f:
                compile(f.read(), path, "exec")
        except Exception as exc:
            raise SiblingModuleError(
                "signal_coordinator: %s.py in %s does not compile: %s" % (name, folder, exc)
            )
    for name in names:
        try:
            module = sys.modules.get(name)
            if module is None:
                module = __import__(name)
            else:
                module = _reload(module)
        except Exception as exc:
            raise SiblingModuleError(
                "signal_coordinator: cannot import %s from %s: %s" % (name, folder, exc)
            )
        got = os.path.dirname(getattr(module, "__file__", None) or "")
        if os.path.normcase(os.path.realpath(got)) != want:
            raise SiblingModuleError(
                "signal_coordinator: %s was loaded from %r, not from %s" % (name, got, folder)
            )
    print("mqtt_signalhead: modules %s from %s" % (", ".join(names), folder))


_load_siblings(SIBLING_MODULES)

from sml_beans import (  # noqa: E402
    TOPIC_PREFIX, MAST_TOPIC_PREFIX, SML_MODE_TOPIC, SML_CLAIM_TOPIC, SML_MODE_SENSOR,
    HOLD_WAIT_MS, BOOT_MODE_WAIT_MS, SML_ABORT_RESUME_MS, PROBE_WAIT_MS,
    _LCOS_SIGNAL_UID_MIN, _LCOS_SIGNAL_UID_MAX, _HEAD_IN_MAST, _ASPECT_TO_APPEARANCE,
    _ascii, _topic_suffix, _packed_is_lcos_signal, _is_lcos_ih_sys, _mqtt_adapter,
    _mast_manager, _head_manager, _sml_manager, _head_names_on_mast, _appearance_constant,
    _dest_listed, _bean_label, SmlBeans,
)
from sml_claims import (  # noqa: E402
    _host_token, _local_host_name, _parse_claim, _claim_key, _owned_claim, SmlClaims,
)
from sml_handoff import (  # noqa: E402
    SmlHandoff,
)


class _BulkRun(object):
    """One bulk SML set's run. cancel() stops the pair flips not yet made.

    The result is decided once: the run's own finish, or the cancel that came first.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cancelled = False
        self.result = None

    def go_on(self):
        with self._lock:
            return not self._cancelled

    def finish(self, ok):
        with self._lock:
            if self.result is None:
                self.result = bool(ok) and not self._cancelled
            return self.result

    def cancel(self):
        """Stop the run; returns its result (False if it had not finished)."""
        with self._lock:
            self._cancelled = True
            if self.result is None:
                self.result = False
            return self.result


class DigiconMqttSml(
    SmlBeans,
    SmlClaims,
    SmlHandoff,
    PropertyChangeListener,
    MqttEventListener,
):
    """Global SML toggle + Digicon MQTT SET / mast->IH / query ACK."""

    # Cross-script handle for panel status-lamp clicks (panel_status).
    INSTANCE = None

    def __init__(self):
        # MQTT live roster: empty until track/signalmast/<packed> reports.
        self.mqtt_wanted = set()
        self.mqtt = None
        self._masts = []
        self._heads = []
        self._smls = []
        self._head_to_mast = {}
        self._global_enabled = False
        self._busy = False
        self._suppress_sml = False
        self._boot_pending = False
        self._retained_mode = None
        self._button = None
        self._probe_active = False
        self._probe_saw_enabled = False
        self._mast_sml_was_enabled = {}
        self._source_field_owned = {}
        self._dest_enable_maps = {}
        self._sml_by_mast = {}
        self._enabling_originator = False
        self._abort_in_progress = False
        self._enabling_wait_scheduled = False
        self._shutting_down = False
        self._shutdown_released = False
        # Quit work runs once: the window-close worker and the ShutDownTask may overlap.
        self._shutdown_lock = threading.Lock()
        self._last_mqtt_appearance = {}
        # Bumped by every abort; a Disable/Enable worker that sees it change stands down.
        self._abort_gen = 0
        # The bridge announced disabling and no owner has spoken since: a disabled now
        # is its release, not an operator Disable (which publishes disabled alone).
        self._bridge_release_pending = False
        self._shutdown_task = None
        self._close_frame = None
        self._close_listener = None
        # Claim identity: this host's name and, while it claims or owns, (stamp ms, force).
        self._host = _local_host_name()
        if self._host in ("unknown", "localhost"):
            # Two hosts with one name cannot tell their claims apart.
            print(
                "mqtt_signalhead: WARNING host name is %r; give each JMRI host its own "
                "name or both may own Digicon" % self._host
            )
        self._now_ms = lambda: int(time.time() * 1000)
        self._claim = None
        self._retained_host = None
        # Disable or quit release under way: any claim from another host wins.
        self._releasing = False
        # Set by the script on a re-run: the earlier run's claim, if that run owned Digicon.
        self._inherited_claim = None
        # Serialises claim decisions with sml_mode messages: a boot or operator take
        # reads the mode and claims in one step, so a rival claim is either heard first
        # or compared with this one. Re-entrant: a message can start a take.
        self._claim_lock = threading.RLock()

    def start(self):
        DigiconMqttSml.INSTANCE = self
        try:
            import __main__

            __main__.digicon_sml_controller = self
        except Exception:
            pass
        self.mqtt = _mqtt_adapter()
        if self.mqtt is None:
            print("mqtt_signalhead: no JMRI MQTT connection; not starting")
            return
        self._collect_beans()
        self._attach_bean_listeners()
        self._attach_sml_listeners()
        adopted = self._adopt_inherited_claim()
        stored_on = False
        if not adopted:
            stored_on = self._warn_if_stored_sml_enabled()
        if stored_on:
            # Stamp before subscribe: a retained claim delivered at subscribe is compared
            # with this one, not taken for a rival with no claim to answer.
            self._stamp_claim(force=True)
        self._subscribe_mqtt()
        self._add_toggle_button()
        if adopted:
            pass
        elif stored_on:
            # A retained claim heard at subscribe may already have won.
            if self._claim is not None:
                self._announce_enabling("stored dests", force=True)
                self._schedule_enabled_after_enabling()
        else:
            # Boot: force Digicon SML off until mode read. Hold/Aspect still publish.
            # No MQTT retain publish here -- only read broker delivery on subscribe.
            self._boot_hold_sml_off()
            self._schedule_boot_check()
        self._register_shutdown_task()
        self._sync_sml_mode_sensor()
        print(
            "mqtt_signalhead: Digicon SML MQTT, %d LCOS masts, %d MQTT heads enrolled "
            "(SET requires signalmast; packed topics)"
            % (len(self._masts), len(self._heads))
        )

    def _adopt_inherited_claim(self):
        """Re-run on the owning host: keep Digicon with the earlier run's claim.

        The earlier run left the dests on, which would otherwise look like stored-Enabled
        tables (popup, enabling, Hold). Nothing is published; heads SET again as the
        retained signalmast reports enroll them.
        """
        claim = self._inherited_claim
        self._inherited_claim = None
        if claim is None or not self._digicon_dests_on():
            return False
        self._claim = claim
        self._global_enabled = True
        self._snapshot_mast_sml_state()
        print(
            "mqtt_signalhead: re-run on the owning host -- keep Digicon (claim %s %d)"
            % (self._host, claim[0])
        )
        return True

    def _digicon_dests_on(self):
        for mast in self._masts:
            if self._enabled_dest_count(mast) > 0:
                return True
        return False

    def toggle_from_panel(self):
        """Panel Signals lamp click — same as the main-window SML button."""
        print("mqtt_signalhead: panel Signals lamp toggle")
        self._on_toggle()

    def _sync_sml_mode_sensor(self):
        """Drive panel Signals lamp (IS:SML_MODE): ACTIVE=enabled, INACTIVE=otherwise."""
        try:
            s = sensors.provideSensor(SML_MODE_SENSOR)
            want = (
                jmri.Sensor.ACTIVE
                if self._global_enabled
                else jmri.Sensor.INACTIVE
            )
            if s.getKnownState() != want:
                s.setKnownState(want)
        except Exception as e:
            print("mqtt_signalhead: SML mode sensor update failed: %s" % e)

    def _register_shutdown_task(self):
        """Register before windows/MQTT close. Work runs in call(), not run()."""
        try:
            task = DigiconSmlQuitTask("Digicon SML quit")
            # The task keeps its own controller: a re-run rebinds the global `controller`.
            task._controller = self
            jmri.InstanceManager.getDefault(jmri.ShutDownManager).register(task)
            self._shutdown_task = task
            print("mqtt_signalhead: registered ShutDownTask")
        except Exception as exc:
            print("mqtt_signalhead: ShutDownTask register failed: " + _ascii(exc))
        self._add_quit_window_hook()

    def _add_quit_window_hook(self):
        """WINDOW_CLOSING still has MQTT; File->Exit / window X both hit this."""
        try:
            from apps import Apps
            from java.awt.event import WindowAdapter

            space = Apps.buttonSpace()
            frame = space.getTopLevelAncestor() if space is not None else None
            if frame is None:
                print("mqtt_signalhead: no main frame for window close hook")
                return
            hook = self

            class _Quit(Runnable):
                def run(_self):
                    hook._on_jmri_shutdown()

            class _Close(WindowAdapter):
                def windowClosing(_self, event):
                    # The release Holds for HOLD_WAIT_MS; never sleep on the Swing thread.
                    print("mqtt_signalhead: main window closing")
                    Thread(_Quit(), "digicon-sml-quit").start()

            listener = _Close()
            frame.addWindowListener(listener)
            self._close_frame = frame
            self._close_listener = listener
            print(
                "mqtt_signalhead: window close hook on %s"
                % _ascii(frame.getTitle())
            )
        except Exception as exc:
            print("mqtt_signalhead: window close hook failed: " + _ascii(exc))

    def _owns_digicon_now(self):
        if self._global_enabled or self._enabling_originator:
            return True
        try:
            for mast in self._masts:
                if self._enabled_dest_count(mast) > 0:
                    return True
        except Exception:
            pass
        return False

    def _on_jmri_shutdown(self):
        """Quit: Hold/wait/Unheld then sml_mode disabled. Idempotent.

        The window-close worker and the ShutDownTask can both call this; the lock makes
        the later caller wait for the release instead of running it a second time.
        """
        with self._shutdown_lock:
            self._on_jmri_shutdown_locked()

    def _on_jmri_shutdown_locked(self):
        if self._shutdown_released:
            return
        self._shutting_down = True
        try:
            if self._abort_in_progress:
                print(
                    "mqtt_signalhead: shutdown skip (abort; other agent owns Digicon)"
                )
                self._shutdown_released = True
                return
            if not self._owns_digicon_now():
                print("mqtt_signalhead: shutdown skip (SML not enabled)")
                self._shutdown_released = True
                return
            print("mqtt_signalhead: shutdown Hold/wait/Unheld then disabled")
            self._busy = True
            try:
                self._release_on_quit()
            finally:
                self._busy = False
            self._shutdown_released = True
        except Exception as exc:
            print("mqtt_signalhead: shutdown task failed: " + _ascii(exc))

    def _release_on_quit(self):
        """MQTT Unheld + disabled before dest uncheck so a layout hang cannot skip RELEASE.

        JMRI is exiting, so its pairs stop driving Digicon anyway. An abort during the
        Hold means another agent is taking Digicon: no Unheld and no disabled over its
        enabling. While it runs, any other host's claim wins.
        """
        self._releasing = True
        try:
            self._release_on_quit_steps()
        finally:
            self._releasing = False

    def _release_on_quit_steps(self):
        abort_gen = self._abort_gen
        print(
            "mqtt_signalhead: Hold Digicon masts, wait %d ms before Unheld / disabled"
            % HOLD_WAIT_MS
        )
        self._set_masts_held(True)
        Thread.sleep(HOLD_WAIT_MS)
        if self._abort_gen != abort_gen:
            print("mqtt_signalhead: shutdown aborted during Hold -- no Unheld, no disabled")
        else:
            print(
                "mqtt_signalhead: shutdown publishing Unheld for %d MQTT head(s)"
                % len(self._heads)
            )
        for head in self._heads:
            if self._abort_gen != abort_gen:
                break
            self._publish_unheld(head)
        sent = False
        with self._claim_lock:
            if self._abort_gen == abort_gen:
                self._publish_mode("disabled")
                sent = True
                # Not the owner from here on: no head SET may follow disabled.
                self._global_enabled = False
                self._enabling_originator = False
                self._claim = None
        if sent:
            # The release is out: a later failure must not make a second caller
            # send disabled again.
            self._shutdown_released = True
            self._sync_sml_mode_sensor()
            print("mqtt_signalhead: shutdown sml_mode disabled -- unchecking SML pairs")
        else:
            print("mqtt_signalhead: shutdown -- unchecking SML pairs (no disabled sent)")
        suppress = self._suppress_sml
        self._suppress_sml = True  # the uncheck itself publishes nothing
        try:
            if self._set_all_digicon_sml_destinations(False) is not True:
                print(
                    "mqtt_signalhead: shutdown FAILED to turn all SML pairs off "
                    "(still on: %s)" % self._pairs_still_on()
                )
            try:
                self._snapshot_mast_sml_state()
            except Exception as exc:
                print("mqtt_signalhead: shutdown snapshot failed: " + _ascii(exc))
        finally:
            self._suppress_sml = suppress
            # A failed bulk set must not leave the masts Held or this host owning.
            self._set_masts_held(False)
            self._global_enabled = False
            self._enabling_originator = False
            self._claim = None
            self._sync_sml_mode_sensor()

    def _stored_enabled_source_names(self):
        """UserNames of Digicon sources that loaded with any dest Enabled."""
        names = []
        n = 0
        for mast in self._masts:
            c = self._enabled_dest_count(mast)
            if c <= 0:
                continue
            n += c
            try:
                name = mast.getUserName() or mast.getSystemName()
            except Exception:
                name = "?"
            names.append(_ascii(name))
        return n, names

    def _warn_if_stored_sml_enabled(self):
        """Popup if tables.xml stored Digicon SML Enabled. Does not stop boot."""
        n, sources = self._stored_enabled_source_names()
        if n == 0:
            return False
        preview = ", ".join(sources[:8])
        if len(sources) > 8:
            preview += ", ..."
        print(
            "mqtt_signalhead: stored SML Enabled "
            "(%d dests on %d sources) -- warning popup"
            % (n, len(sources))
        )
        msg = (
            "Digicon SML was stored Enabled in tables.xml "
            "(%d destination(s) on %d source(s)).\n"
            "This warning returns at every start until you Store "
            "with SML Disabled.\n\n"
            "Sources: %s\n\n"
            "Startup continues."
            % (n, len(sources), preview)
        )

        class _Warn(Runnable):
            def run(_self):
                try:
                    from jmri.util.swing import JmriJOptionPane

                    JmriJOptionPane.showMessageDialog(
                        None,
                        msg,
                        "Digicon SML stored Enabled",
                        JmriJOptionPane.WARNING_MESSAGE,
                    )
                except Exception:
                    JOptionPane.showMessageDialog(
                        None,
                        msg,
                        "Digicon SML stored Enabled",
                        JOptionPane.WARNING_MESSAGE,
                    )

        SwingUtilities.invokeLater(_Warn())
        return True

    def _set_all_digicon_sml_destinations(self, enabled):
        """Flip Enabled checkbox for every Digicon source→dest pair (SML table).

        Runs on the layout thread and waits. Abort holds `_suppress_sml` until
        that wait returns so dest uncheck does not publish (another agent owns SET).
        Returns True only if every pair reached the requested state; False on a
        timeout, a cancel, an exception or any pair that failed. A timed-out run is
        cancelled: once the layout thread gets to it, it flips no further pair.
        """
        # SML may finish discovering after Start Up -- refresh before bulk set.
        self._attach_sml_listeners(quiet=True)

        def _do(run):
            n = 0
            ok = True
            for sml in self._smls:
                try:
                    dests = sml.getDestinationList()
                except Exception as exc:
                    print(
                        "mqtt_signalhead: getDestinationList: " + _ascii(exc)
                    )
                    ok = False
                    continue
                if dests is None:
                    continue
                try:
                    empty = dests.isEmpty()
                except Exception:
                    empty = len(dests) == 0
                if empty:
                    continue
                try:
                    # A copy: a pair added or removed meanwhile cannot upset the loop.
                    copy = []
                    it = dests.iterator()
                    while it.hasNext():
                        copy.append(it.next())
                    for dest in copy:
                        # Checked before each flip. A cancel that lands during a flip
                        # lets that one flip finish: at most one pair changes after it.
                        if not run.go_on():
                            print(
                                "mqtt_signalhead: SML bulk set cancelled after %d pair(s)"
                                % n
                            )
                            return run.finish(False)
                        try:
                            if enabled == bool(sml.isEnabled(dest)):
                                continue
                            if enabled:
                                sml.setEnabled(dest)
                            else:
                                sml.setDisabled(dest)
                            if enabled != bool(sml.isEnabled(dest)):
                                raise RuntimeError("pair did not change")
                            n += 1
                        except Exception as exc:
                            if not _dest_listed(sml, dest):
                                # Removed from the logic meanwhile: nothing to set.
                                print(
                                    "mqtt_signalhead: SML pair %s gone -- skipped"
                                    % _bean_label(dest)
                                )
                                continue
                            ok = False
                            print(
                                "mqtt_signalhead: setEnabled/Disabled(%s): %s"
                                % (_ascii(dest), _ascii(exc))
                            )
                except Exception as exc:
                    ok = False
                    print("mqtt_signalhead: dest iterate: " + _ascii(exc))
            print(
                "mqtt_signalhead: SML pairs %s (%d)%s"
                % (("enabled" if enabled else "disabled"), n, "" if ok else " -- not all")
            )
            return run.finish(ok)

        if self._shutting_down:
            return _do(_BulkRun())

        queued = _BulkRun()
        ran = [False]
        wait = [None]  # (latch, TimeUnit) once the latch exists
        queued_ok = [False]  # runOnLayout returned: the work is queued
        try:
            from java.util.concurrent import CountDownLatch, TimeUnit
            from jmri.util import ThreadingUtil

            latch = CountDownLatch(1)
            wait[0] = (latch, TimeUnit)

            def _run():
                try:
                    _do(queued)
                finally:
                    ran[0] = True
                    latch.countDown()

            if ThreadingUtil.isLayoutThread():
                _run()
                return queued.result is True

            # JMRI wants ThreadAction (not bare Runnable).
            class _R(ThreadingUtil.ThreadAction):
                def run(__self):
                    _run()

            ThreadingUtil.runOnLayout(_R())
            queued_ok[0] = True
            if not latch.await(30, TimeUnit.SECONDS):
                if not queued.cancel():
                    print("mqtt_signalhead: SML bulk set timed out on layout thread")
                    return False
            return queued.result is True
        except Exception as exc:
            print("mqtt_signalhead: SML bulk set fallback: " + _ascii(exc))
            if queued_ok[0] and not ran[0]:
                # A queued copy may be running now: give it a moment to finish.
                try:
                    wait[0][0].await(1, wait[0][1].SECONDS)
                except Exception:
                    pass
            if ran[0]:
                return queued.result is True
            # Cancel the copy that may still be queued, then run here instead.
            if queued.cancel():
                return True
            return _do(_BulkRun())

    def _subscribe_mqtt(self):
        try:
            self.mqtt.subscribe(SML_MODE_TOPIC, self)
            self.mqtt.subscribe(SML_CLAIM_TOPIC, self)
            # signalmast first (roster + paint). signalhead is SET/Unheld; do not enroll.
            self.mqtt.subscribe(MAST_TOPIC_PREFIX + "#", self)
            self.mqtt.subscribe(TOPIC_PREFIX + "#", self)
        except Exception as exc:
            print("mqtt_signalhead: MQTT subscribe failed: " + _ascii(exc))

    def _enroll_packed(self, packed):
        """Add packed disc to MQTT roster from track/signalmast (not signalhead)."""
        packed = str(packed).strip()
        if not _packed_is_lcos_signal(packed):
            return
        sys_name = "IH" + packed
        if sys_name in self.mqtt_wanted:
            return
        hm = _head_manager()
        if hm is None:
            return
        head = hm.getSignalHead(sys_name)
        if head is None:
            print(
                "mqtt_signalhead: skip enroll %s (no IH bean)"
                % _ascii(sys_name)
            )
            return
        self.mqtt_wanted.add(sys_name)
        if head not in self._heads:
            self._heads.append(head)
            try:
                head.addPropertyChangeListener(self)
            except Exception as exc:
                print(
                    "mqtt_signalhead: listener %s: %s"
                    % (_ascii(sys_name), _ascii(exc))
                )
        print("mqtt_signalhead: enrolled %s from signalmast" % _ascii(sys_name))
        if self._global_enabled:
            self._publish_head_set(head)

    def _add_toggle_button(self, attempt=0):
        """PanelPro main-window strip — kept in addition to the LE Signals lamp."""
        max_attempts = 12
        delay_ms = 500

        def _try_attach():
            try:
                from apps import Apps

                space = Apps.buttonSpace()
                if space is None:
                    raise RuntimeError("Apps.buttonSpace() is None")
                # Already on the strip (retry). A button left by an earlier run drives
                # that run's controller, so take it off rather than reuse it.
                for i in range(space.getComponentCount() - 1, -1, -1):
                    c = space.getComponent(i)
                    try:
                        if c is self._button:
                            space.revalidate()
                            space.repaint()
                            return True
                        if c.getText() in ("SML Enabled", "SML Disabled"):
                            space.remove(c)
                            print("mqtt_signalhead: removed SML button left by an earlier run")
                    except Exception:
                        pass
                if self._button is None:
                    self._button = JButton("SML Disabled")
                    self._button.addActionListener(lambda e: self._on_toggle())
                space.add(self._button)
                space.revalidate()
                space.repaint()
                print("mqtt_signalhead: SML toggle on PanelPro button strip")
                return True
            except Exception as exc:
                print(
                    "mqtt_signalhead: buttonSpace attempt %d failed: %s"
                    % (attempt + 1, _ascii(exc))
                )
                return False

        class _Attach(Runnable):
            def run(_self):
                # Detached by a re-run (or quitting): leave the strip to the new one.
                if self._shutting_down:
                    return
                if _try_attach():
                    self._set_button_label()
                    return
                if attempt + 1 >= max_attempts:
                    print(
                        "mqtt_signalhead: giving up on main-window SML button "
                        "(panel Signals lamp still works)"
                    )
                    return
                self._add_toggle_button(attempt + 1)

        if attempt == 0 and self._button is None:
            self._button = JButton("SML Disabled")
            self._button.addActionListener(lambda e: self._on_toggle())

        if attempt == 0:
            SwingUtilities.invokeLater(_Attach())
        else:

            class _Retry(Runnable):
                def run(_self):
                    Thread.sleep(delay_ms)
                    if not self._shutting_down:
                        SwingUtilities.invokeLater(_Attach())

            Thread(_Retry(), "mqtt-sml-button").start()

    def _set_button_busy(self):
        """Grey the button while a worker runs (on the Swing thread)."""
        button = self._button
        if button is None:
            return

        class _Grey(Runnable):
            def run(_self):
                button.setEnabled(False)

        SwingUtilities.invokeLater(_Grey())

    def _set_button_label(self):
        if self._button is None:
            return
        label = "SML Enabled" if self._global_enabled else "SML Disabled"

        class _Set(Runnable):
            def run(_self):
                self._button.setText(label)
                self._button.setEnabled(True)

        SwingUtilities.invokeLater(_Set())

    def _publish(self, topic, payload, retain=False):
        if self.mqtt is None:
            return
        try:
            # Always name the retain flag: JMRI's two-argument MqttAdapter.publish(topic, data)
            # retains (its `retained` field defaults to true), so it cannot send a plain message.
            # The three-argument form needs JMRI 5.9.1 or later (hosts run 5.16); on an older
            # JMRI this raises and is printed below, with no two-argument fallback.
            self.mqtt.publish(topic, payload, bool(retain))
        except Exception as exc:
            print(
                "mqtt_signalhead: publish failed %s %s: %s"
                % (_ascii(topic), _ascii(payload), _ascii(exc))
            )

    def _publish_mode(self, mode):
        """Retained sml_mode word; enabling / enabled then this host's claim.

        The word goes first: a host that hears it while idle stands back before the
        claim reaches it, and one already claiming compares the claim.
        """
        claim = self._claim
        if mode in ("enabling", "enabled") and claim is None:
            # Lost or aborted on another thread just now: nothing to announce.
            print("mqtt_signalhead: no claim -- %s not sent" % mode)
            return
        self._retained_mode = mode
        self._publish(SML_MODE_TOPIC, mode, retain=True)
        if mode not in ("enabling", "enabled"):
            return
        stamp, force = claim
        payload = "%s %s %d" % (mode, self._host, stamp)
        if force:
            # On enabled too: both hosts must rank an owner with the same key.
            payload += " force"
        self._retained_host = self._host
        self._publish(SML_CLAIM_TOPIC, payload, retain=True)

    def notifyMqttMessage(self, topic, message):
        topic = _ascii(topic)
        message = _ascii(message).strip()
        # JMRI may deliver full topic or channel-relative leaf.
        if topic == SML_CLAIM_TOPIC or topic.endswith("bridge/sml_claim"):
            self._on_sml_claim(message)
            return
        if (
            topic == SML_MODE_TOPIC
            or topic.endswith("/bridge/sml_mode")
            or topic.endswith("bridge/sml_mode")
            or topic == "bridge/sml_mode"
            or topic.endswith("sml_mode")
        ):
            self._on_sml_mode(message)
            return
        # SET/Unheld: never enroll from signalhead (publisher also publishes SET).
        if (
            topic.startswith(TOPIC_PREFIX)
            or "/signalhead/" in topic
            or topic.startswith("signalhead/")
        ):
            return
        # track/signalmast/<packed>
        prefix = MAST_TOPIC_PREFIX
        leaf = None
        if topic.startswith(prefix):
            leaf = topic[len(prefix) :]
        elif "/signalmast/" in topic:
            leaf = topic.split("/signalmast/", 1)[1]
        elif topic.startswith("signalmast/"):
            leaf = topic[len("signalmast/") :]
        if leaf is None:
            return
        if "/" in leaf:
            leaf = leaf.split("/", 1)[0]
        if not leaf.isdigit():
            return
        self._enroll_packed(leaf)
        self._apply_mast_payload_to_head(leaf, message)

    def _on_sml_claim(self, message):
        """A claim from track/bridge/sml_claim (this host's own echo included)."""
        mode, host, stamp, force = _parse_claim(message)
        if mode not in ("enabling", "enabled") or stamp is None:
            print("mqtt_signalhead: sml_claim %r not understood -- ignored" % message)
            return
        with self._claim_lock:
            # The last claim on the broker; read at boot with the retained mode.
            self._retained_host = host
            if self._is_own_claim(host, stamp):
                return
            if self._claim is not None:
                self._resolve_claim_race(mode, host, stamp, force)

    def _on_sml_mode(self, message):
        words = message.split()
        mode = words[0].lower() if words else ""
        with self._claim_lock:
            self._on_sml_mode_locked(mode)

    def _on_sml_mode_locked(self, mode):
        bridge_release = mode == "disabled" and self._bridge_release_pending
        if mode == "disabling":
            self._bridge_release_pending = True
        elif mode in ("enabled", "enabling", "aborting", "aborted", "disabled"):
            self._bridge_release_pending = False
        if mode == "enabled" and self._probe_active:
            self._probe_saw_enabled = True
        if mode in (
            "enabled",
            "disabled",
            "query",
            "disabling",
            "enabling",
            "aborting",
            "aborted",
        ):
            # Do not let our probe query wipe a known enabled retain for the fast path.
            if not (self._probe_active and mode == "query"):
                self._retained_mode = mode
        if mode in ("enabling", "enabled") and self._claim is not None:
            # Claiming or owning: this host's own echo, or a rival whose claim follows
            # on sml_claim and is compared there.
            if mode == "enabling" and self._enabling_originator:
                print(
                    "mqtt_signalhead: own enabling -- leave SML, wait to announce enabled"
                )
            return
        if mode == "enabling":
            print("mqtt_signalhead: saw enabling -- abort SML")
            self._abort_sml_immediate()
            return
        # Live Digicon: answer query and disabling so the LCOS bridge can abort RELEASE.
        # ACK while owning or taking (Hold included). Do not ACK our Enable probe
        # or during abort (unchecked, not yet re-enabled).
        if mode in ("query", "disabling") and self._should_ack_sml_alive():
            self._publish_mode("enabled")
            print("mqtt_signalhead: ACK %s -> enabled" % mode)
            return
        # The bridge found nobody owning a retained enabled (query, disabling, then
        # disabled): e.g. a stale retain after a power cut made this host stay Disabled
        # at boot. Take the boot decision again. An operator Disable on another host
        # publishes disabled alone, and stays as the operator set it.
        if bridge_release and self._idle_for_take():
            print("mqtt_signalhead: bridge released sml_mode -- take Digicon (enable)")
            self._enter_enabled(force=True, from_boot=True)

    def _idle_for_take(self):
        """Not owning, taking, aborting, booting or quitting Digicon."""
        return not (
            self._is_busy()
            or self._boot_pending
            or self._shutting_down
            or self._global_enabled
            or self._enabling_originator
            or self._owns_digicon_now()
        )

    def _should_ack_sml_alive(self):
        """True while this instance owns or is taking Digicon (including Hold)."""
        if self._probe_active or self._abort_in_progress:
            return False
        if self._enabling_originator:
            return True
        return bool(self._global_enabled)

    def propertyChange(self, event):
        name = event.propertyName
        source = event.source
        # Abort only: dests off without Hold; do not publish SET/Unheld.
        if self._suppress_sml:
            return
        # SML enable/disable (table checkbox or our setEnabled/Disabled)
        if source in self._smls or (
            hasattr(source, "getSourceMast") and name in ("Enabled", "disabled", "Disabled")
        ):
            self._on_sml_property(source)
            return
        if name in ("Aspect", "Held", "Lit"):
            if source in self._masts:
                for sys_name in _head_names_on_mast(source):
                    if sys_name not in self.mqtt_wanted:
                        continue
                    head = _head_manager().getSignalHead(sys_name)
                    if head is not None:
                        self._publish_head_set(head)
            return
        if name == "Appearance":
            self._publish_head_set(source)

    def _on_sml_property(self, sml):
        # Global button / boot bulk setDisabled owns Unheld.
        if self._is_busy() or self._boot_pending:
            return
        if not self._global_enabled:
            return
        try:
            mast = sml.getSourceMast()
        except Exception:
            return
        if mast not in self._masts:
            return
        now_map = self._dest_enable_map(sml)
        was_map = self._dest_enable_maps.get(sml) or {}
        self._dest_enable_maps[sml] = now_map
        self._mast_sml_was_enabled[mast] = any(now_map.values())
        if not was_map:
            return
        disabled = []
        enabled = []
        keys = set(now_map.keys()) | set(was_map.keys())
        for dest in keys:
            now_on = now_map.get(dest)
            was_on = was_map.get(dest)
            if was_on is None or now_on is None:
                continue
            if was_on and not now_on:
                disabled.append(dest)
            elif (not was_on) and now_on:
                enabled.append(dest)
        if disabled:
            print(
                "mqtt_signalhead: dest Enabled off %s -> %s"
                % (_ascii(mast.getDisplayName()), _ascii(disabled[0]))
            )
            self._hand_source_to_field(mast)
            return
        if enabled:
            print(
                "mqtt_signalhead: dest Enabled on %s -> %s"
                % (_ascii(mast.getDisplayName()), _ascii(enabled[0]))
            )
            self._hand_source_to_sml(mast)


class DigiconSmlQuitTask(jmri.implementation.AbstractShutDownTask):
    """JMRI calls call() before closing windows; run() is after MQTT may be gone."""

    def _owner(self):
        return getattr(self, "_controller", None) or controller

    def call(self):
        self.setDoRun(True)
        print("mqtt_signalhead: ShutDownTask call()")
        try:
            self._owner()._on_jmri_shutdown()
        except Exception as exc:
            print("mqtt_signalhead: ShutDownTask call failed: " + _ascii(exc))
        return True

    def run(self):
        print("mqtt_signalhead: ShutDownTask run()")
        try:
            self._owner()._on_jmri_shutdown()
        except Exception as exc:
            print("mqtt_signalhead: ShutDownTask run failed: " + _ascii(exc))


def _detach_controller(old):
    """Unhook a controller left by an earlier run of this script.

    Without this a re-run leaves the old listeners, MQTT subscriptions, quit task and
    window hook live beside the new ones, and the visible button drives the old
    instance. Reads attributes with defaults so a controller from an older copy of the
    script is detached as far as it allows. Sends nothing on MQTT.
    """
    if old is None:
        return
    print("mqtt_signalhead: detaching the controller from an earlier run")
    try:
        old._shutting_down = True
        old._shutdown_released = True
    except Exception:
        pass
    beans = (
        list(getattr(old, "_masts", []))
        + list(getattr(old, "_heads", []))
        + list(getattr(old, "_smls", []))
    )
    for bean in beans:
        try:
            bean.removePropertyChangeListener(old)
        except Exception:
            pass
    mqtt = getattr(old, "mqtt", None)
    if mqtt is not None:
        for topic in (
            SML_MODE_TOPIC,
            SML_CLAIM_TOPIC,
            MAST_TOPIC_PREFIX + "#",
            TOPIC_PREFIX + "#",
        ):
            try:
                mqtt.unsubscribe(topic, old)
            except Exception as exc:
                print("mqtt_signalhead: unsubscribe %s: %s" % (topic, _ascii(exc)))
    task = getattr(old, "_shutdown_task", None)
    if task is not None:
        try:
            jmri.InstanceManager.getDefault(jmri.ShutDownManager).deregister(task)
        except Exception as exc:
            print("mqtt_signalhead: ShutDownTask deregister: " + _ascii(exc))
    frame = getattr(old, "_close_frame", None)
    listener = getattr(old, "_close_listener", None)
    if frame is not None and listener is not None:
        try:
            frame.removeWindowListener(listener)
        except Exception:
            pass
    button = getattr(old, "_button", None)
    if button is not None:

        class _Remove(Runnable):
            def run(_self):
                try:
                    parent = button.getParent()
                    if parent is not None:
                        parent.remove(button)
                        parent.revalidate()
                        parent.repaint()
                except Exception as exc:
                    print("mqtt_signalhead: old button remove: " + _ascii(exc))

        SwingUtilities.invokeLater(_Remove())


_inherited = None
try:
    import __main__

    _previous = getattr(__main__, "digicon_sml_controller", None)
    # Read before the detach marks it shutting down: a run that owns Digicon hands on its claim.
    _inherited = _owned_claim(_previous)
    _detach_controller(_previous)
except Exception as exc:
    print("mqtt_signalhead: detach earlier run failed: " + _ascii(exc))

controller = DigiconMqttSml()
controller._inherited_claim = _inherited
DigiconMqttSml.INSTANCE = controller
try:
    import __main__

    __main__.digicon_sml_controller = controller
except Exception:
    pass
controller.start()
