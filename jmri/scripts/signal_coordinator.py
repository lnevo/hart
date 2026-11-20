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
#   Digicon, Hold / wait / pairs off / Unheld then sml_mode disabled. Work is in
#   call() because JMRI run() is after windows close. Abort does not RELEASE.
# Never two owners: `disabled` goes out only once every pair is off, and `enabled`
#   only once every pair is on (or, after a failed Enable, could not be turned
#   off again). A failed Disable keeps this host the owner (pairs back on,
#   enabled again); a failed quit unholds the masts and sends no disabled.
#
# Topic leaf is packed digits only (IH432 -> .../432). Beans stay IH*.
# Digicon plants: SignalMasts that carry LCOS Virtual IH heads (UID 32-47) in
# JMRI tables — no hardcoded HEAD_NAMES. MQTT SET/Unheld/paint still requires
# enrollment from track/signalmast/<packed> (bridge + field status up).

import java
import jmri
import re
import threading
import time
from java.beans import PropertyChangeListener
from java.lang import Runnable, Thread
from javax.swing import JButton, JOptionPane, SwingUtilities
from jmri.jmrix.mqtt import MqttEventListener

TOPIC_PREFIX = "track/signalhead/"
MAST_TOPIC_PREFIX = "track/signalmast/"
SML_MODE_TOPIC = "track/bridge/sml_mode"
# Coordinators only (the bridge never subscribes): who claims, and when.
SML_CLAIM_TOPIC = "track/bridge/sml_claim"
SML_MODE_SENSOR = "IS:SML_MODE"
HOLD_WAIT_MS = 3000
BOOT_MODE_WAIT_MS = 1000
# After enabling, originator waits then Holds and announces sml_mode enabled.
SML_ABORT_RESUME_MS = 1000
# Operator Enable probe: wait for another instance to ACK enabled.
PROBE_WAIT_MS = 1000
# Only abort mutes bean MQTT: dests uncheck without Hold/Red/Unheld because
# another agent owns Digicon. Operator Enable/Disable Hold wait publishes.

# LCOS signal UIDs: UID_OFFSET_SIGNALS .. UID_OFFSET_CROSSINGS-1 (lcos.h).
_LCOS_SIGNAL_UID_MIN = 32
_LCOS_SIGNAL_UID_MAX = 47

_HEAD_IN_MAST = re.compile(r"\(IH\d+\)")

_ASPECT_TO_APPEARANCE = {
    "stop": "Red",
    "approach": "Yellow",
    "clear": "Green",
    "red": "Red",
    "yellow": "Yellow",
    "green": "Green",
    "dark": "Dark",
    "off": "Dark",
}


def _ascii(s):
    if s is None:
        return ""
    if not isinstance(s, str):
        try:
            s = str(s)
        except Exception:
            return repr(s)
    try:
        return s.encode("ascii", "replace").decode("ascii")
    except Exception:
        return repr(s)


def _topic_suffix(sys_name):
    """MQTT topic leaf: packed digits only (drop IH prefix)."""
    if sys_name is None:
        return ""
    name = str(sys_name)
    if len(name) > 2 and name[:2].upper() == "IH" and name[2:].isdigit():
        return name[2:]
    return name


def _packed_is_lcos_signal(packed):
    """True if packed = display_node*100 + signal UID (32-47) and node is octal-legal."""
    if packed is None:
        return False
    s = str(packed).strip()
    if not s.isdigit():
        return False
    n = int(s)
    node = n // 100
    uid = n % 100
    if uid < _LCOS_SIGNAL_UID_MIN or uid > _LCOS_SIGNAL_UID_MAX:
        return False
    try:
        int(str(node), 8)
    except Exception:
        return False
    return True


def _is_lcos_ih_sys(sys_name):
    """True if system name is IH<packed> for an LCOS signal UID."""
    if sys_name is None:
        return False
    name = str(sys_name)
    if len(name) <= 2 or name[:2].upper() != "IH":
        return False
    return _packed_is_lcos_signal(name[2:])


def _host_token(name):
    """One lower-case word for the payload: first DNS label, [a-z0-9_-] only."""
    s = _ascii(name).strip().lower().split(".")[0] if name else ""
    s = re.sub(r"[^a-z0-9_-]+", "-", s).strip("-")
    return s or "unknown"


def _local_host_name():
    name = None
    try:
        from java.net import InetAddress

        name = InetAddress.getLocalHost().getHostName()
    except Exception:
        name = None
    if not name:
        try:
            import platform

            name = platform.node()
        except Exception:
            name = None
    return _host_token(name)


def _parse_claim(message):
    """sml_claim payload -> (mode, host, stamp, force).

    "enabling <host> <ms> [force]" or "enabled <host> <ms>". Anything shorter or without
    a number gives host and stamp None.
    """
    words = _ascii(message).split()
    if not words:
        return "", None, None, False
    mode = words[0].lower()
    if len(words) < 3:
        return mode, None, None, False
    try:
        stamp = int(words[2])
    except Exception:
        return mode, None, None, False
    force = "force" in [w.lower() for w in words[3:]]
    return mode, words[1].lower(), stamp, force


def _claim_key(stamp, host, force):
    """Smaller wins: a force claim first, then the earlier stamp, then the host name."""
    return (0 if force else 1, stamp, host)


def _owned_claim(old):
    """The claim of an earlier run's controller if it owns Digicon and is not mid-change."""
    try:
        claim = getattr(old, "_claim", None)
        if claim is None or not getattr(old, "_global_enabled", False):
            return None
        for busy in ("_busy", "_abort_in_progress", "_releasing", "_shutting_down"):
            if getattr(old, busy, False):
                return None
        return claim
    except Exception:
        return None


def _mqtt_adapter():
    try:
        memo = jmri.InstanceManager.getDefault(
            jmri.jmrix.mqtt.MqttSystemConnectionMemo
        )
        if memo is None:
            return None
        return memo.getMqttAdapter()
    except Exception:
        return None


def _mast_manager():
    try:
        return masts
    except NameError:
        return jmri.InstanceManager.getDefault(jmri.SignalMastManager)


def _head_manager():
    try:
        return signals
    except NameError:
        return jmri.InstanceManager.getDefault(jmri.SignalHeadManager)


def _sml_manager():
    return jmri.InstanceManager.getDefault(jmri.SignalMastLogicManager)


def _head_names_on_mast(mast):
    """IH* heads encoded on a SignalHeadSignalMast systemName."""
    names = []
    for token in _HEAD_IN_MAST.findall(str(mast.getSystemName())):
        names.append(token[1:-1])
    return names


def _appearance_constant(name):
    """Map appearance name to SignalHead int, or None."""
    if name is None:
        return None
    key = str(name).strip()
    # JMRI's names are the standard ("Flashing Red"); the LCOS firmware's tokens
    # ("FlashRed") are accepted too.
    upper = key.upper().replace(" ", "").replace("FLASHING", "FLASH")
    table = {
        "RED": jmri.SignalHead.RED,
        "YELLOW": jmri.SignalHead.YELLOW,
        "GREEN": jmri.SignalHead.GREEN,
        "DARK": jmri.SignalHead.DARK,
        "OFF": jmri.SignalHead.DARK,
        "LUNAR": jmri.SignalHead.LUNAR,
        "FLASHRED": jmri.SignalHead.FLASHRED,
        "FLASHYELLOW": jmri.SignalHead.FLASHYELLOW,
        "FLASHGREEN": jmri.SignalHead.FLASHGREEN,
        "FLASHLUNAR": jmri.SignalHead.FLASHLUNAR,
    }
    return table.get(upper)


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
        """Quit: Hold/wait/pairs off/Unheld then sml_mode disabled. Idempotent.

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
        """Hold, pairs off, then Unheld + disabled. Never `disabled` with pairs on.

        If the pairs cannot all be turned off, the masts are still unheld but no
        disabled goes out; the bridge's query / disabling release takes Digicon back
        once this JMRI is gone. An abort during the Hold means another agent is
        taking Digicon: no Unheld and no disabled over its enabling. While it runs,
        any other host's claim wins.
        """
        self._releasing = True
        try:
            self._release_on_quit_steps()
        finally:
            self._releasing = False

    def _release_on_quit_steps(self):
        abort_gen = self._abort_gen
        print(
            "mqtt_signalhead: Hold Digicon masts, wait %d ms before pairs off / Unheld"
            % HOLD_WAIT_MS
        )
        self._set_masts_held(True)
        Thread.sleep(HOLD_WAIT_MS)
        print("mqtt_signalhead: shutdown -- unchecking SML pairs")
        off = False
        try:
            off = self._set_all_digicon_sml_destinations(False) is True
            self._snapshot_mast_sml_state()
            if self._abort_gen != abort_gen:
                print("mqtt_signalhead: shutdown aborted during Hold -- no Unheld, no disabled")
            elif not off:
                print(
                    "mqtt_signalhead: shutdown FAILED to turn all SML pairs off -- no "
                    "disabled; the bridge releases Digicon once this JMRI is gone"
                )
            else:
                print(
                    "mqtt_signalhead: shutdown publishing Unheld for %d MQTT head(s)"
                    % len(self._heads)
                )
                for head in self._heads:
                    if self._abort_gen != abort_gen:
                        break
                    self._publish_unheld(head)
        finally:
            # Whatever happened, a Held mast must not stay red.
            self._set_masts_held(False)
        aborted = self._abort_gen != abort_gen
        if not off and not aborted:
            return  # pairs may be on: this host still owns them
        with self._claim_lock:
            if self._abort_gen == abort_gen:
                self._publish_mode("disabled")
                print("mqtt_signalhead: shutdown sml_mode disabled")
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

    def _is_busy(self):
        """A Disable/Enable worker or an abort is running."""
        return self._busy or self._abort_in_progress

    def _abort_sml_immediate(self):
        """Uncheck Digicon SML now: aborting -> dests off (no Hold/Red/Unheld) -> aborted.

        Called on JMRI's one MQTT callback thread. The bulk uncheck waits on the layout
        thread, so it runs on a worker; SET stops and the ACK is refused here at once.
        Leaves `_busy` alone: a Disable/Enable worker still running owns that flag.
        """
        if self._abort_in_progress:
            return
        self._abort_in_progress = True
        self._abort_gen += 1
        self._boot_pending = False
        self._global_enabled = False
        self._enabling_originator = False
        self._claim = None
        self._sync_sml_mode_sensor()
        controller = self

        class _Abort(Runnable):
            def run(_self):
                controller._run_abort()

        Thread(_Abort(), "digicon-sml-abort").start()

    def _run_abort(self):
        self._suppress_sml = True
        try:
            print("mqtt_signalhead: sml_mode aborting (immediate uncheck, no RELEASE)")
            self._publish_mode("aborting")
            self._set_all_digicon_sml_destinations(False)
            self._snapshot_mast_sml_state()
            self._publish_mode("aborted")
            print("mqtt_signalhead: sml_mode aborted")
        finally:
            self._suppress_sml = False
            self._abort_in_progress = False
            # A Disable/Enable worker still running resets the button when it ends.
            if not self._busy:
                self._set_button_label()

    def _stamp_claim(self, force=False):
        """Start a claim: this host's stamp now. Published by _announce_enabling."""
        with self._claim_lock:
            self._claim = (self._now_ms(), bool(force))
            self._enabling_originator = True

    def _announce_enabling(self, reason, force=False):
        """Publish enabling with this host's claim; a stamped claim keeps its stamp."""
        with self._claim_lock:
            if self._claim is None or not self._enabling_originator:
                self._stamp_claim(force=force)
            stamp, forced = self._claim
            self._publish_mode("enabling")
        print(
            "mqtt_signalhead: sml_mode enabling (%s; claim %s %d%s)"
            % (reason, self._host, stamp, " force" if forced else "")
        )

    def _my_claim_key(self):
        stamp, force = self._claim
        return _claim_key(stamp, self._host, force)

    def _is_own_claim(self, host, stamp):
        return (
            self._claim is not None
            and host == self._host
            and stamp == self._claim[0]
        )

    def _lose_claim(self, why):
        """Another host's claim won. Pending: cancel the Hold; with dests on: abort."""
        print("mqtt_signalhead: %s -- stand down" % why)
        self._claim = None
        self._enabling_originator = False
        if self._global_enabled or self._digicon_dests_on():
            self._abort_sml_immediate()
        else:
            # A pending Hold reads the bump and leaves the pairs off, with no enabled.
            self._abort_gen += 1
            self._sync_sml_mode_sensor()

    def _resolve_claim_race(self, mode, host, stamp, force):
        """A claim (enabling) or ownership (enabled) from elsewhere while this host
        claims or owns. The smaller key wins on both hosts, as each compares the
        same two keys."""
        if host == self._host:
            print(
                "mqtt_signalhead: %s from this host's earlier run (%d) -- ignored"
                % (mode, stamp)
            )
            return
        theirs = _claim_key(stamp, host, force)
        if self._releasing or theirs < self._my_claim_key():
            self._lose_claim(
                "%s %s %d%s is first" % (mode, host, stamp, " force" if force else "")
            )
            return
        if self._global_enabled:
            # Still the owner: say so, so the later claimant stands down.
            print(
                "mqtt_signalhead: %s %s %d is later -- keep Digicon, re-announce enabled"
                % (mode, host, stamp)
            )
            self._publish_mode("enabled")
            return
        print(
            "mqtt_signalhead: %s %s %d is later -- keep taking" % (mode, host, stamp)
        )

    def _schedule_enabled_after_enabling(self):
        """Originator only: dests stay on; after a short wait announce enabled."""
        if self._enabling_wait_scheduled:
            return
        self._enabling_wait_scheduled = True
        controller = self

        class _Resume(Runnable):
            def run(_self):
                Thread.sleep(SML_ABORT_RESUME_MS)
                controller._enabling_wait_scheduled = False
                if controller._shutting_down:
                    print("mqtt_signalhead: enabling announce skipped (shutting down)")
                    return
                if controller._global_enabled and str(
                    controller._retained_mode or ""
                ).strip().lower() == "enabled":
                    print("mqtt_signalhead: enabling announce skipped (already enabled)")
                    return
                print("mqtt_signalhead: enabling -- take Digicon (enabled)")
                controller._enter_enabled(force=True, from_boot=True, resume=True)

        Thread(_Resume(), "digicon-sml-enabling").start()

    def _boot_hold_sml_off(self):
        """Force Digicon SML pairs off until boot check finishes. No MQTT mute."""
        self._boot_pending = True
        self._set_all_digicon_sml_destinations(False)
        self._global_enabled = False
        self._sync_sml_mode_sensor()
        self._snapshot_mast_sml_state()
        self._set_button_label()

    def _snapshot_mast_sml_state(self):
        """Baseline dest Enabled maps. Bulk/boot must not Unheld from the listener.

        Per-mast field ownership is dest checkboxes only. Global Disable is
        `_global_enabled` in `_field_owns_mast` — do not fold it in here, or
        Enable's snapshot (taken before `_global_enabled = True`) would leave
        every source field-owned and block SET.
        """
        state = {}
        owned = {}
        dest_maps = {}
        for mast in self._masts:
            sml = self._sml_for_mast(mast)
            dmap = self._dest_enable_map(sml) if sml is not None else {}
            if sml is not None:
                dest_maps[sml] = dmap
            on = any(dmap.values())
            state[mast] = on
            owned[mast] = not on
        self._mast_sml_was_enabled = state
        self._source_field_owned = owned
        self._dest_enable_maps = dest_maps

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
                    it = dests.iterator()
                    while it.hasNext():
                        dest = it.next()
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
                            n += 1
                            if enabled != bool(sml.isEnabled(dest)):
                                ok = False
                                print(
                                    "mqtt_signalhead: SML pair %s did not change"
                                    % _ascii(dest)
                                )
                        except Exception as exc:
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
        try:
            from java.util.concurrent import CountDownLatch, TimeUnit
            from jmri.util import ThreadingUtil

            latch = CountDownLatch(1)

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
            if not latch.await(30, TimeUnit.SECONDS):
                if not queued.cancel():
                    print("mqtt_signalhead: SML bulk set timed out on layout thread")
                    return False
            return queued.result is True
        except Exception as exc:
            print("mqtt_signalhead: SML bulk set fallback: " + _ascii(exc))
            if ran[0]:
                return queued.result is True
            # Cancel the copy that may still be queued, then run here instead.
            if queued.cancel():
                return True
            return _do(_BulkRun())

    def _collect_beans(self):
        """Digicon plants = SHSM masts with LCOS Virtual IH heads (tables, not a static list).

        MQTT SET/Unheld heads attach later via _enroll_packed from signalmast.
        """
        mm = _mast_manager()
        self._masts = []
        self._heads = []
        self._head_to_mast = {}
        if mm is None:
            return
        for mast in mm.getNamedBeanSet():
            lcos_heads = [n for n in _head_names_on_mast(mast) if _is_lcos_ih_sys(n)]
            if not lcos_heads:
                continue
            self._masts.append(mast)
            for n in lcos_heads:
                self._head_to_mast[n] = mast

    def _attach_bean_listeners(self):
        for mast in self._masts:
            mast.addPropertyChangeListener(self)
        for head in self._heads:
            head.addPropertyChangeListener(self)

    def _attach_sml_listeners(self, quiet=False):
        smlm = _sml_manager()
        if smlm is None:
            return
        for sml in self._smls:
            try:
                sml.removePropertyChangeListener(self)
            except Exception:
                pass
        self._smls = []
        self._sml_by_mast = {}
        digicon = set(self._masts)
        for sml in smlm.getSignalMastLogicList():
            try:
                src = sml.getSourceMast()
            except Exception:
                continue
            if src not in digicon:
                continue
            sml.addPropertyChangeListener(self)
            self._smls.append(sml)
            self._sml_by_mast[src] = sml
        n = len(self._smls)
        # Refresh before bulk set is normal; only log when the count changes.
        if quiet and n == getattr(self, "_sml_watch_logged", None):
            return
        print(
            "mqtt_signalhead: watching %d Digicon SignalMastLogic sources"
            % n
        )
        self._sml_watch_logged = n

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

    def _schedule_boot_check(self):
        """After subscribe, read sml_mode (broker retain arrives as a message).

        No publish during this decision. missing/disabled/query -> enable Digicon;
        enabled -> stay Disabled with zero Unheld.
        """
        controller = self

        class _Boot(Runnable):
            def run(_self):
                Thread.sleep(BOOT_MODE_WAIT_MS)
                if controller._shutting_down:
                    print("mqtt_signalhead: boot check skipped (shutting down)")
                    return
                # Read and claim in one step: a rival claim lands before (seen here) or after
                # (compared with this claim).
                with controller._claim_lock:
                    mode = controller._retained_mode
                    mode_s = "" if mode is None else str(mode).strip().lower()
                    take = mode is None or mode_s in (
                        "",
                        "disabled",
                        "query",
                        "disabling",
                    )
                    # A claim with this host's own name was left by its earlier run.
                    own_stale = (
                        mode_s in ("enabled", "enabling")
                        and controller._retained_host == controller._host
                    )
                    if take or own_stale:
                        print(
                            "mqtt_signalhead: boot mode=%s%s -- take Digicon (enable)"
                            % (
                                mode_s if mode_s else "missing",
                                " (left by this host)" if own_stale else "",
                            )
                        )
                        controller._boot_pending = False
                        controller._enter_enabled(force=True, from_boot=True)
                        return
                print(
                    "mqtt_signalhead: boot mode=%s -- stay SML Disabled "
                    "(no Unheld, no mode publish)"
                    % (mode_s if mode_s else "missing")
                )
                controller._boot_pending = False
                controller._global_enabled = False
                controller._snapshot_mast_sml_state()
                controller._set_button_label()

        Thread(_Boot(), "digicon-sml-boot").start()

    def _on_toggle(self):
        if self._is_busy():
            return
        if self._global_enabled:
            self._enter_disabled(release=True)
        else:
            self._enter_enabled(force=False, from_boot=False)

    def _ask_force_override_edt(self):
        """Show override confirm on the EDT. Return True if Yes."""
        holder = [JOptionPane.NO_OPTION]
        msg = (
            "track/bridge/sml_mode is already enabled "
            "(another Digicon session or stale retain).\n"
            "Force override Digicon control?"
        )
        title = "SML Enabled"

        class _Ask(Runnable):
            def run(_self):
                try:
                    from jmri.util.swing import JmriJOptionPane

                    holder[0] = JmriJOptionPane.showConfirmDialog(
                        None,
                        msg,
                        title,
                        JmriJOptionPane.YES_NO_OPTION,
                        JmriJOptionPane.WARNING_MESSAGE,
                    )
                except Exception:
                    holder[0] = JOptionPane.showConfirmDialog(
                        None,
                        msg,
                        title,
                        JOptionPane.YES_NO_OPTION,
                        JOptionPane.WARNING_MESSAGE,
                    )

        try:
            if SwingUtilities.isEventDispatchThread():
                _Ask().run()
            else:
                SwingUtilities.invokeAndWait(_Ask())
        except Exception as exc:
            print("mqtt_signalhead: override dialog failed: " + _ascii(exc))
            return False
        return holder[0] == JOptionPane.YES_OPTION

    def _probe_and_confirm_override(self):
        """If sml_mode is already enabled elsewhere, ask before taking control.

        Return "ok" (take Digicon now), "force" (publish enabling so others
        abort), or "cancel".
        """
        mode = self._retained_mode
        if mode is not None and str(mode).strip().lower() == "enabled":
            print("mqtt_signalhead: retain already enabled -- asking override")
            if self._ask_force_override_edt():
                return "force"
            return "cancel"
        # Live probe: another Enabled Digicon answers query with enabled.
        self._probe_saw_enabled = False
        self._probe_active = True
        try:
            self._publish(SML_MODE_TOPIC, "query", retain=False)
            print("mqtt_signalhead: enable probe query (wait for enabled ACK)")
            Thread.sleep(PROBE_WAIT_MS)
        finally:
            self._probe_active = False
        if self._probe_saw_enabled:
            print("mqtt_signalhead: probe saw enabled -- asking override")
            if self._ask_force_override_edt():
                return "force"
            return "cancel"
        print("mqtt_signalhead: probe clear -- enabling without override")
        return "ok"

    def _enter_enabled(self, force, from_boot, resume=False):
        """Take Digicon on a worker. force/from_boot skip the operator probe.

        A boot or bridge-release take claims here, on the deciding thread, so the claim
        goes out at the moment of the decision. resume=True carries on the claim the
        stored-dests boot announced, and skips if that claim was lost.
        """
        with self._claim_lock:
            if self._is_busy() or self._shutting_down:
                return
            if resume:
                if self._claim is None or not self._enabling_originator:
                    print("mqtt_signalhead: enabling lost to another host -- no take")
                    return
            elif force or from_boot:
                self._announce_enabling("take")
            self._busy = True
            abort_gen = self._abort_gen
        self._set_button_busy()
        controller = self

        class _Run(Runnable):
            def run(_self):
                try:
                    if controller._shutting_down:
                        return
                    if not force and not from_boot:
                        result = controller._probe_and_confirm_override()
                        if result == "cancel":
                            print("mqtt_signalhead: enable aborted (no override)")
                            return
                        with controller._claim_lock:
                            if controller._abort_gen != abort_gen:
                                print(
                                    "mqtt_signalhead: enable skipped (aborted during "
                                    "probe; another agent is taking Digicon)"
                                )
                                return
                            if result == "force":
                                controller._announce_enabling("force override", force=True)
                            else:
                                controller._announce_enabling("operator enable")
                        if result == "force":
                            Thread.sleep(SML_ABORT_RESUME_MS)
                    if controller._shutting_down:
                        print("mqtt_signalhead: enable skipped (shutting down)")
                        return
                    controller._hand_off_enabled(abort_gen)
                finally:
                    controller._busy = False
                    controller._set_button_label()
                    controller._sync_sml_mode_sensor()

        Thread(_Run(), "digicon-sml-enable").start()

    def _enter_disabled(self, release):
        if self._is_busy():
            return
        self._busy = True
        self._set_button_busy()
        controller = self
        abort_gen = self._abort_gen

        class _Run(Runnable):
            def run(_self):
                controller._releasing = True
                try:
                    controller._hand_off_disabled(release=release, abort_gen=abort_gen)
                finally:
                    controller._releasing = False
                    controller._busy = False
                    controller._set_button_label()
                    controller._sync_sml_mode_sensor()

        Thread(_Run(), "digicon-sml-disable").start()

    def _apply_global_disabled(self, release, publish_mode, abort_gen=None):
        """Disable Digicon SML in JMRI. RELEASE only when release=True.

        If an abort ran since `abort_gen` was read, another agent owns Digicon: no
        Unheld of its heads and no `disabled` over its enabling.
        """
        if abort_gen is None:
            abort_gen = self._abort_gen
        print(
            "mqtt_signalhead: Hold Digicon masts, wait %d ms before SML off / Unheld"
            % HOLD_WAIT_MS
        )
        for mast in self._masts:
            try:
                mast.setHeld(True)
            except Exception:
                pass
        Thread.sleep(HOLD_WAIT_MS)
        print("mqtt_signalhead: Hold wait done -- disabling SML pairs")
        off = self._try_set_all_digicon_sml(False)
        aborted = self._abort_gen != abort_gen
        if aborted:
            print(
                "mqtt_signalhead: aborted during Disable -- no Unheld, no disabled "
                "(another agent owns Digicon)"
            )
        elif not off:
            self._stay_owner_after_failed_disable(abort_gen)
            return
        if release and not aborted:
            print(
                "mqtt_signalhead: publishing Unheld for %d MQTT head(s)"
                % len(self._heads)
            )
            for head in self._heads:
                if self._abort_gen != abort_gen:
                    break
                self._publish_unheld(head)
        for mast in self._masts:
            try:
                mast.setHeld(False)
            except Exception:
                pass
        self._global_enabled = False
        self._enabling_originator = False
        self._claim = None
        if publish_mode and self._abort_gen == abort_gen:
            self._publish_mode("disabled")
        self._sync_sml_mode_sensor()

    def _try_set_all_digicon_sml(self, enabled):
        """Bulk set, then snapshot; False (printed) if any pair may be left as it was."""
        ok = False
        try:
            ok = self._set_all_digicon_sml_destinations(enabled) is True
            self._snapshot_mast_sml_state()
        except Exception as exc:
            print(
                "mqtt_signalhead: %s SML pairs failed: %s"
                % ("enabling" if enabled else "disabling", _ascii(exc))
            )
            ok = False
        return ok

    def _set_masts_held(self, held):
        for mast in self._masts:
            try:
                mast.setHeld(held)
            except Exception:
                pass

    def _stay_owner_after_failed_disable(self, abort_gen):
        """Pairs may still be on: handing off now would make two owners. Keep Digicon."""
        print(
            "mqtt_signalhead: Disable FAILED -- SML pairs may still be on; keeping "
            "Digicon (enabled). Check the SML table, then try Disable again."
        )
        # Best effort: all pairs on again, so this host owns consistently.
        self._try_set_all_digicon_sml(True)
        self._set_masts_held(False)
        with self._claim_lock:
            if self._abort_gen == abort_gen:
                self._publish_mode("enabled")
        self._sync_sml_mode_sensor()

    def _hand_off_disabled(self, release, abort_gen=None):
        print("mqtt_signalhead: global -> SML Disabled (release=%s)" % release)
        self._apply_global_disabled(
            release=release, publish_mode=True, abort_gen=abort_gen
        )

    def _hand_off_enabled(self, abort_gen=None):
        if self._shutting_down:
            print("mqtt_signalhead: enable skipped (shutting down)")
            return
        if abort_gen is None:
            abort_gen = self._abort_gen
        if self._abort_gen != abort_gen or self._claim is None:
            print("mqtt_signalhead: enable skipped (aborted; another agent is taking Digicon)")
            self._enabling_originator = False
            return
        # ACK query/disabling during Hold (not yet _global_enabled). The Hold is also the
        # window in which a rival claim is heard and compared.
        self._enabling_originator = True
        print("mqtt_signalhead: global -> SML Enabled")
        print(
            "mqtt_signalhead: Hold Digicon masts, wait %d ms before SML on"
            % HOLD_WAIT_MS
        )
        for mast in self._masts:
            try:
                mast.setHeld(True)
            except Exception:
                pass
        Thread.sleep(HOLD_WAIT_MS)
        # Commit under the claim lock: a rival claim is handled either before (this claim
        # lost, or kept) or after (this host owns; the rival is compared with an owner).
        with self._claim_lock:
            lost = (
                self._shutting_down
                or self._abort_gen != abort_gen
                or self._claim is None
            )
            if not lost:
                self._global_enabled = True
        if lost:
            print(
                "mqtt_signalhead: enable Hold done but shutting down, aborted or lost "
                "to another host -- leave dests, no enabled"
            )
            if self._abort_gen != abort_gen:
                self._enabling_originator = False
            for mast in self._masts:
                try:
                    mast.setHeld(False)
                except Exception:
                    pass
            return
        print("mqtt_signalhead: Hold wait done -- enabling SML pairs")
        on = self._try_set_all_digicon_sml(True)
        if self._abort_gen != abort_gen:
            # Taken over while the pairs went on: the abort's uncheck may have run first.
            print("mqtt_signalhead: taken over during enable -- pairs off, no enabled")
            self._set_all_digicon_sml_destinations(False)
            self._snapshot_mast_sml_state()
            for mast in self._masts:
                try:
                    mast.setHeld(False)
                except Exception:
                    pass
            return
        if not on and self._back_out_failed_enable(abort_gen):
            return
        for mast in self._masts:
            try:
                mast.setHeld(False)
            except Exception:
                pass
        # Ownership announce for the bridge and the other host (not a boot retain republish).
        # Under the lock, so an abort that lands now cannot be followed by our enabled.
        with self._claim_lock:
            if self._abort_gen == abort_gen and self._claim is not None:
                self._publish_mode("enabled")
            self._enabling_originator = False
        self._sync_sml_mode_sensor()
        # Push current appearances once Digicon owns SET again.
        for head in self._heads:
            if self._mast_logic_enabled(self._mast_for_head(head)):
                self._publish_head_set(head, force=True)

    def _back_out_failed_enable(self, abort_gen):
        """The pairs did not all go on: never announce enabled with pairs off.

        Turn them off again and hand off as Disable does (True). If that fails too,
        some pairs may be on: return False, and the caller stays the owner and
        announces enabled. One owner, possibly partial, beats two.
        """
        print("mqtt_signalhead: Enable FAILED -- not all SML pairs went on; no enabled")
        off = self._try_set_all_digicon_sml(False)
        if not off:
            print(
                "mqtt_signalhead: and turning them off FAILED -- keeping Digicon "
                "(enabled). Check the SML table."
            )
            return False
        print(
            "mqtt_signalhead: SML pairs off again -- publishing Unheld for %d MQTT head(s)"
            % len(self._heads)
        )
        for head in self._heads:
            if self._abort_gen != abort_gen:
                break
            self._publish_unheld(head)
        self._set_masts_held(False)
        with self._claim_lock:
            self._global_enabled = False
            self._enabling_originator = False
            self._claim = None
            if self._abort_gen == abort_gen:
                self._publish_mode("disabled")
        self._sync_sml_mode_sensor()
        return True

    def _mast_for_head(self, head):
        if head is None:
            return None
        return self._head_to_mast.get(head.getSystemName())

    def _sml_for_mast(self, mast):
        if mast is None:
            return None
        return self._sml_by_mast.get(mast)

    def _mast_logic_enabled(self, mast):
        """True if Digicon source mast has any destination Enabled in the SML table."""
        return self._enabled_dest_count(mast) > 0

    def _enabled_dest_count(self, mast):
        if mast is None:
            return 0
        sml = self._sml_for_mast(mast)
        if sml is None:
            return 0
        n = 0
        try:
            dests = sml.getDestinationList()
            if dests is None or dests.isEmpty():
                return 0
            it = dests.iterator()
            while it.hasNext():
                dest = it.next()
                try:
                    if sml.isEnabled(dest):
                        n += 1
                except Exception:
                    continue
        except Exception:
            return 0
        return n

    def _dest_enable_map(self, sml):
        """dest systemName -> isEnabled for one source logic."""
        out = {}
        if sml is None:
            return out
        try:
            dests = sml.getDestinationList()
            if dests is None or dests.isEmpty():
                return out
            it = dests.iterator()
            while it.hasNext():
                dest = it.next()
                try:
                    key = dest.getSystemName()
                    out[key] = bool(sml.isEnabled(dest))
                except Exception:
                    continue
        except Exception:
            return out
        return out

    def _field_owns_mast(self, mast):
        """Field owns heads when global SML is off or this source was unchecked."""
        if mast is None:
            return False
        if not self._global_enabled:
            return True
        if self._source_field_owned.get(mast):
            return True
        return not self._mast_logic_enabled(mast)

    def _publish_unheld(self, head):
        if head is None:
            return
        sys_name = head.getSystemName()
        if sys_name not in self.mqtt_wanted:
            return
        topic = TOPIC_PREFIX + _topic_suffix(sys_name)
        prev = self._last_mqtt_appearance.get(sys_name)
        if prev == "Unheld":
            return
        self._last_mqtt_appearance[sys_name] = "Unheld"
        self._publish(topic, "Unheld", retain=True)

    def _mqtt_heads_on_mast(self, mast):
        heads = []
        hm = _head_manager()
        if hm is None or mast is None:
            return heads
        for sys_name in _head_names_on_mast(mast):
            if sys_name not in self.mqtt_wanted:
                continue
            head = hm.getSignalHead(sys_name)
            if head is not None:
                heads.append(head)
        return heads

    def _hand_source_to_field(self, mast):
        """Uncheck Enable: Unheld this source's heads; field owns until re-enabled."""
        if self._source_field_owned.get(mast):
            return
        self._source_field_owned[mast] = True
        heads = self._mqtt_heads_on_mast(mast)
        if not heads:
            print(
                "mqtt_signalhead: SML dest off %s — no MQTT heads "
                "(roster=%s)"
                % (
                    _ascii(mast.getDisplayName()),
                    ",".join(sorted(self.mqtt_wanted)),
                )
            )
            return
        for head in heads:
            self._publish_unheld(head)
        print(
            "mqtt_signalhead: SML dest off -> Unheld %s (field owns)"
            % _ascii(mast.getDisplayName())
        )

    def _hand_source_to_sml(self, mast):
        """Re-check Enable: Digicon SET again."""
        self._source_field_owned[mast] = False
        heads = self._mqtt_heads_on_mast(mast)
        for head in heads:
            self._publish_head_set(head, force=True)
        print(
            "mqtt_signalhead: SML dest on -> SET %s (Digicon owns)"
            % _ascii(mast.getDisplayName())
        )

    def _publish_head_set(self, head, force=False):
        if self.mqtt is None or head is None:
            return
        if not self._global_enabled:
            return
        mast = self._mast_for_head(head)
        if self._field_owns_mast(mast):
            return
        sys_name = head.getSystemName()
        if sys_name not in self.mqtt_wanted:
            return
        topic = TOPIC_PREFIX + _topic_suffix(sys_name)
        data = head.getAppearanceName()
        prev = self._last_mqtt_appearance.get(sys_name)
        # Skip unchanged chatter on property churn — but Enable must always SET
        # so the field/bridge re-applies even if the aspect string is the same.
        if not force and prev is not None and prev == data:
            return
        self._last_mqtt_appearance[sys_name] = data
        # Retain so LCOS bridge can resume Flashing Red / … after restart
        # (color/Dark toggles stay bridge-local and never appear on MQTT).
        self._publish(topic, data, retain=True)

    def _apply_mast_payload_to_head(self, packed, payload):
        """track/signalmast/<packed> -> IH heads + source SignalMast when field owns."""
        sys_name = "IH" + str(packed)
        if sys_name not in self.mqtt_wanted:
            return
        mast = self._head_to_mast.get(sys_name)
        if self._global_enabled and not self._field_owns_mast(mast):
            return
        parts = [p.strip() for p in str(payload).split(";") if p.strip()]
        if not parts:
            return
        aspect = parts[0]
        head = _head_manager().getSignalHead(sys_name)
        if head is not None:
            mapped = _ASPECT_TO_APPEARANCE.get(aspect.lower())
            if mapped is None:
                mapped = aspect
            const = _appearance_constant(mapped)
            if const is not None:
                try:
                    if head.getAppearance() != const:
                        head.setAppearance(const)
                except Exception as exc:
                    print(
                        "mqtt_signalhead: setAppearance %s %s: %s"
                        % (_ascii(sys_name), _ascii(mapped), _ascii(exc))
                    )
        if mast is None:
            return
        mast_aspect = aspect
        if aspect.lower() in _ASPECT_TO_APPEARANCE:
            appearance = _ASPECT_TO_APPEARANCE[aspect.lower()]
            mast_aspect = {
                "Red": "Stop",
                "Yellow": "Approach",
                "Green": "Clear",
                "Dark": "Dark",
            }.get(appearance, aspect)
        try:
            current = None
            try:
                current = mast.getAspect()
            except Exception:
                pass
            if current != mast_aspect:
                mast.setAspect(mast_aspect)
        except Exception as exc:
            print(
                "mqtt_signalhead: setAspect %s %s: %s"
                % (_ascii(mast.getDisplayName()), _ascii(mast_aspect), _ascii(exc))
            )
        for token in parts[1:]:
            low = token.lower()
            try:
                if low == "lit":
                    mast.setLit(True)
                elif low == "unlit":
                    mast.setLit(False)
                elif low == "held":
                    mast.setHeld(True)
                elif low == "unheld":
                    mast.setHeld(False)
            except Exception:
                pass

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
