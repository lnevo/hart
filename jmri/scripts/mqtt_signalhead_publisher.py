# JMRI jython -- Digicon MQTT <-> SML hand-off (publisher + receiver + global toggle).
#
# Name kept as mqtt_signalhead_publisher.py for existing profile Start Up entries.
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
#   publishes enabled. If that never happens, the LCOS bridge challenges.
#   Clean boot: hold Digicon SML off until track/bridge/sml_mode is seen.
#   missing / disabled / query / disabling -> take Digicon (enable SML; announce enabled).
#   enabled / enabling / aborting / aborted -> stay Disabled (originator owns resume).
# Operator Enable when sml_mode is already enabled: force-override popup;
#   Yes publishes enabling (same abort for other agents) then enabled.
# Query or disabling ACK when Enabled (so bridge can suspend RELEASE).
#
# Topic leaf is packed digits only (IH432 -> .../432). Beans stay IH*.
# Generated HEAD_NAMES: cats/scripts/build_hart_signal_heads.py
# (signal_wiring.csv). Keep the HEAD_NAMES_BEGIN/END markers.

import java
import jmri
import re
from java.beans import PropertyChangeListener
from java.lang import Runnable, Thread
from javax.swing import JButton, JOptionPane, SwingUtilities
from jmri.jmrix.mqtt import MqttEventListener

TOPIC_PREFIX = "track/signalhead/"
MAST_TOPIC_PREFIX = "track/signalmast/"
SML_MODE_TOPIC = "track/bridge/sml_mode"
HOLD_WAIT_MS = 3000
BOOT_MODE_WAIT_MS = 3000
# After enabling, originator waits then announces sml_mode enabled.
SML_ABORT_RESUME_MS = 3000
# True: skip Held/Aspect MQTT during Hold wait (production).
# False: Hold still publishes Red before the explicit Unheld (test).
# Bulk setDisabled never publishes Unheld from the checkbox listener — the
# operator Disable path owns that burst. Per-mast table uncheck still does.
SUPPRESS_SML_DURING_HANDOFF = True

# HEAD_NAMES_BEGIN
HEAD_NAMES = [
    'IH432',
    'IH433',
    'IH434',
    'IH436',
    'IH437',
    'IH438',
    'IH439',
    'IH1332',
    'IH1333',
    'IH1334',
    'IH1335',
    'IH1336',
    'IH1337',
    'IH1338',
    'IH1232',
    'IH1233',
    'IH1234',
    'IH1235',
    'IH1236',
    'IH1237',
    'IH1238',
    'IH1239',
    'IH1240',
    'IH1241',
    'IH132',
    'IH133',
    'IH134',
    'IH135',
    'IH136',
    'IH137',
    'IH138',
    'IH139',
    'IH140',
    'IH141',
    'IH142',
    'IH143',
]
# HEAD_NAMES_END

# TEST LIMIT: MQTT SET / Unheld / mast→IH only for these Digicon heads.
# Full HEAD_NAMES still drive Digicon mast discovery and SML enable/disable.
# Restore to all HEAD_NAMES (or empty list = all) when more LCOS signals are live.
MQTT_HEAD_NAMES = [
    "IH432",
]

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
    upper = key.upper().replace(" ", "")
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


class DigiconMqttSml(
    PropertyChangeListener,
    MqttEventListener,
):
    """Global SML toggle + Digicon MQTT SET / mast->IH / query ACK."""

    def __init__(self, head_names):
        self.wanted = set(head_names)
        if MQTT_HEAD_NAMES:
            self.mqtt_wanted = set(MQTT_HEAD_NAMES)
        else:
            self.mqtt_wanted = set(head_names)
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

    def start(self):
        self.mqtt = _mqtt_adapter()
        if self.mqtt is None:
            print("mqtt_signalhead: no JMRI MQTT connection; not starting")
            return
        self._collect_beans()
        self._attach_bean_listeners()
        self._attach_sml_listeners()
        # Snapshot before subscribe so our own enabling echo cannot abort us.
        stored_on = self._warn_if_stored_sml_enabled()
        if stored_on:
            self._enabling_originator = True
        self._subscribe_mqtt()
        self._add_toggle_button()
        if stored_on:
            self._announce_enabling("stored dests")
            self._schedule_enabled_after_enabling()
        else:
            # Boot: force Digicon SML off and keep suppress until mode read.
            # No MQTT retain publish here -- only read broker delivery on subscribe.
            self._boot_hold_sml_off()
            self._schedule_boot_check()
        print(
            "mqtt_signalhead: Digicon SML MQTT, %d masts, %d MQTT heads "
            "(of %d Digicon; packed topics)"
            % (len(self._masts), len(self._heads), len(self.wanted))
        )

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

    def _abort_sml_immediate(self):
        """Uncheck Digicon SML now: aborting -> dests off (no Hold/Red/Unheld) -> aborted."""
        if self._abort_in_progress:
            return
        self._abort_in_progress = True
        self._boot_pending = False
        self._busy = True
        self._suppress_sml = True
        try:
            print("mqtt_signalhead: sml_mode aborting (immediate uncheck, no RELEASE)")
            self._publish_mode("aborting")
            self._set_all_digicon_sml_destinations(False)
            self._snapshot_mast_sml_state()
            self._global_enabled = False
            self._publish_mode("aborted")
            print("mqtt_signalhead: sml_mode aborted")
        finally:
            self._suppress_sml = False
            self._abort_in_progress = False
            self._busy = False
            self._set_button_label()

    def _announce_enabling(self, reason):
        """Publish enabling; this instance does not abort. Other agents must."""
        self._enabling_originator = True
        self._publish_mode("enabling")
        print(
            "mqtt_signalhead: sml_mode enabling (%s; this instance does not abort)"
            % reason
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
                if controller._global_enabled and str(
                    controller._retained_mode or ""
                ).strip().lower() == "enabled":
                    print("mqtt_signalhead: enabling announce skipped (already enabled)")
                    return
                print("mqtt_signalhead: enabling -- take Digicon (enabled)")
                controller._enter_enabled(force=True, from_boot=True)

        Thread(_Resume(), "digicon-sml-enabling").start()

    def _boot_hold_sml_off(self):
        """Force Digicon SML pairs off; leave suppress on until boot check finishes."""
        self._boot_pending = True
        self._suppress_sml = SUPPRESS_SML_DURING_HANDOFF
        self._set_all_digicon_sml_destinations(False)
        self._global_enabled = False
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

        Runs on the layout thread and waits so callers can keep _suppress_sml
        until every setEnabled/setDisabled has finished (avoids Unheld storms).
        """
        # SML may finish discovering after Start Up -- refresh before bulk set.
        self._attach_sml_listeners()

        def _do():
            n = 0
            for sml in self._smls:
                try:
                    dests = sml.getDestinationList()
                except Exception as exc:
                    print(
                        "mqtt_signalhead: getDestinationList: " + _ascii(exc)
                    )
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
                        try:
                            already = bool(sml.isEnabled(dest))
                            if enabled == already:
                                continue
                            if enabled:
                                sml.setEnabled(dest)
                            else:
                                sml.setDisabled(dest)
                            n += 1
                        except Exception as exc:
                            print(
                                "mqtt_signalhead: setEnabled/Disabled(%s): %s"
                                % (_ascii(dest), _ascii(exc))
                            )
                except Exception as exc:
                    print("mqtt_signalhead: dest iterate: " + _ascii(exc))
            print(
                "mqtt_signalhead: SML pairs %s (%d)"
                % (("enabled" if enabled else "disabled"), n)
            )

        ran = [False]
        try:
            from java.util.concurrent import CountDownLatch, TimeUnit
            from jmri.util import ThreadingUtil

            latch = CountDownLatch(1)

            def _run():
                try:
                    _do()
                finally:
                    ran[0] = True
                    latch.countDown()

            if ThreadingUtil.isLayoutThread():
                _run()
                return

            # JMRI wants ThreadAction (not bare Runnable).
            class _R(ThreadingUtil.ThreadAction):
                def run(__self):
                    _run()

            ThreadingUtil.runOnLayout(_R())
            if not latch.await(30, TimeUnit.SECONDS):
                print("mqtt_signalhead: SML bulk set timed out on layout thread")
        except Exception as exc:
            print("mqtt_signalhead: SML bulk set fallback: " + _ascii(exc))
            if not ran[0]:
                _do()

    def _collect_beans(self):
        mm = _mast_manager()
        hm = _head_manager()
        self._masts = []
        self._heads = []
        self._head_to_mast = {}
        if mm is not None:
            for mast in mm.getNamedBeanSet():
                heads = _head_names_on_mast(mast)
                wanted_heads = [n for n in heads if n in self.wanted]
                if not wanted_heads:
                    continue
                self._masts.append(mast)
                for n in wanted_heads:
                    self._head_to_mast[n] = mast
        if hm is not None:
            # Listeners / SET / Unheld only for MQTT-active heads.
            for name in sorted(self.mqtt_wanted):
                if name not in self.wanted:
                    print(
                        "mqtt_signalhead: MQTT_HEAD_NAMES entry not in HEAD_NAMES: "
                        + _ascii(name)
                    )
                    continue
                head = hm.getSignalHead(name)
                if head is None:
                    print("mqtt_signalhead: missing head " + _ascii(name))
                    continue
                self._heads.append(head)

    def _attach_bean_listeners(self):
        for mast in self._masts:
            mast.addPropertyChangeListener(self)
        for head in self._heads:
            head.addPropertyChangeListener(self)

    def _attach_sml_listeners(self):
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
        print(
            "mqtt_signalhead: watching %d Digicon SignalMastLogic sources"
            % len(self._smls)
        )

    def _subscribe_mqtt(self):
        try:
            self.mqtt.subscribe(SML_MODE_TOPIC, self)
            # Mast status → IH only for MQTT-active packed leaves.
            for sys_name in sorted(self.mqtt_wanted):
                packed = _topic_suffix(sys_name)
                if packed:
                    self.mqtt.subscribe(MAST_TOPIC_PREFIX + packed, self)
        except Exception as exc:
            print("mqtt_signalhead: MQTT subscribe failed: " + _ascii(exc))

    def _add_toggle_button(self):
        self._button = JButton("SML Disabled")
        self._button.addActionListener(lambda e: self._on_toggle())
        try:
            from apps import Apps

            Apps.buttonSpace().add(self._button)
            Apps.buttonSpace().revalidate()
        except Exception as exc:
            print("mqtt_signalhead: buttonSpace failed: " + _ascii(exc))

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
            # JMRI MqttAdapter.publish(topic, data); retain via overload if present.
            if retain:
                try:
                    self.mqtt.publish(topic, payload, True)
                    return
                except TypeError:
                    pass
            self.mqtt.publish(topic, payload)
        except Exception as exc:
            print(
                "mqtt_signalhead: publish failed %s %s: %s"
                % (_ascii(topic), _ascii(payload), _ascii(exc))
            )

    def _publish_mode(self, mode):
        self._retained_mode = mode
        self._publish(SML_MODE_TOPIC, mode, retain=True)

    def _schedule_boot_check(self):
        """After subscribe, read sml_mode (broker retain arrives as a message).

        No publish during this decision. missing/disabled/query -> enable Digicon;
        enabled -> stay Disabled with zero Unheld.
        """
        controller = self

        class _Boot(Runnable):
            def run(_self):
                Thread.sleep(BOOT_MODE_WAIT_MS)
                mode = controller._retained_mode
                mode_s = "" if mode is None else str(mode).strip().lower()
                take = mode is None or mode_s in (
                    "",
                    "disabled",
                    "query",
                    "disabling",
                )
                if take:
                    print(
                        "mqtt_signalhead: boot mode=%s -- take Digicon (enable)"
                        % (mode_s if mode_s else "missing")
                    )
                    controller._boot_pending = False
                    # suppress stays True until _hand_off_enabled finishes
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
                controller._suppress_sml = False
                controller._set_button_label()

        Thread(_Boot(), "digicon-sml-boot").start()

    def _on_toggle(self):
        if self._busy:
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
            Thread.sleep(2000)
        finally:
            self._probe_active = False
        if self._probe_saw_enabled:
            print("mqtt_signalhead: probe saw enabled -- asking override")
            if self._ask_force_override_edt():
                return "force"
            return "cancel"
        print("mqtt_signalhead: probe clear -- enabling without override")
        return "ok"

    def _enter_enabled(self, force, from_boot):
        if self._busy:
            return
        self._busy = True
        if self._button is not None:
            self._button.setEnabled(False)
        controller = self

        class _Run(Runnable):
            def run(_self):
                try:
                    if not force and not from_boot:
                        result = controller._probe_and_confirm_override()
                        if result == "cancel":
                            print("mqtt_signalhead: enable aborted (no override)")
                            return
                        if result == "force":
                            controller._announce_enabling("force override")
                            Thread.sleep(SML_ABORT_RESUME_MS)
                    controller._hand_off_enabled()
                finally:
                    controller._busy = False
                    controller._set_button_label()

        Thread(_Run(), "digicon-sml-enable").start()

    def _enter_disabled(self, release):
        if self._busy:
            return
        self._busy = True
        if self._button is not None:
            self._button.setEnabled(False)
        controller = self

        class _Run(Runnable):
            def run(_self):
                try:
                    controller._hand_off_disabled(release=release)
                finally:
                    controller._busy = False
                    controller._set_button_label()

        Thread(_Run(), "digicon-sml-disable").start()

    def _apply_global_disabled(self, release, publish_mode):
        """Disable Digicon SML in JMRI. RELEASE only when release=True."""
        self._suppress_sml = SUPPRESS_SML_DURING_HANDOFF
        try:
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
            # Always mute checkbox listeners around bulk uncheck. The TEST
            # flag only allows Held/Aspect MQTT during the Hold wait.
            was_suppress = self._suppress_sml
            self._suppress_sml = True
            try:
                self._set_all_digicon_sml_destinations(False)
                self._snapshot_mast_sml_state()
            finally:
                self._suppress_sml = was_suppress
            if release:
                print(
                    "mqtt_signalhead: publishing Unheld for %d MQTT head(s)"
                    % len(self._heads)
                )
                for head in self._heads:
                    self._publish_unheld(head)
            for mast in self._masts:
                try:
                    mast.setHeld(False)
                except Exception:
                    pass
            self._global_enabled = False
            if publish_mode:
                self._publish_mode("disabled")
        finally:
            self._suppress_sml = False

    def _hand_off_disabled(self, release):
        print("mqtt_signalhead: global -> SML Disabled (release=%s)" % release)
        self._apply_global_disabled(release=release, publish_mode=True)

    def _hand_off_enabled(self):
        print("mqtt_signalhead: global -> SML Enabled")
        self._suppress_sml = SUPPRESS_SML_DURING_HANDOFF
        try:
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
            print("mqtt_signalhead: Hold wait done -- enabling SML pairs")
            was_suppress = self._suppress_sml
            self._suppress_sml = True
            try:
                self._set_all_digicon_sml_destinations(True)
                self._snapshot_mast_sml_state()
            finally:
                self._suppress_sml = was_suppress
            for mast in self._masts:
                try:
                    mast.setHeld(False)
                except Exception:
                    pass
            self._global_enabled = True
            # Ownership announce for the bridge (not a boot retain republish).
            self._publish_mode("enabled")
            self._enabling_originator = False
            # Push current appearances once Digicon owns SET again.
            for head in self._heads:
                if self._mast_logic_enabled(self._mast_for_head(head)):
                    self._publish_head_set(head)
        finally:
            self._suppress_sml = False

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
        self._publish(topic, "Unheld", retain=False)

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
                "(MQTT_HEAD_NAMES=%s)"
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
            self._publish_head_set(head)
        print(
            "mqtt_signalhead: SML dest on -> SET %s (Digicon owns)"
            % _ascii(mast.getDisplayName())
        )

    def _publish_head_set(self, head):
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
        self._publish(topic, data, retain=False)

    def _apply_mast_payload_to_head(self, packed, payload):
        """track/signalmast/<packed> -> IH heads + source SignalMast when field owns."""
        sys_name = "IH" + str(packed)
        if sys_name not in self.mqtt_wanted:
            return
        mast = self._head_to_mast.get(sys_name)
        if not self._field_owns_mast(mast):
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
        if (
            topic == SML_MODE_TOPIC
            or topic.endswith("/bridge/sml_mode")
            or topic.endswith("bridge/sml_mode")
            or topic == "bridge/sml_mode"
            or topic.endswith("sml_mode")
        ):
            self._on_sml_mode(message)
            return
        # track/signalmast/<packed>
        prefix = MAST_TOPIC_PREFIX
        leaf = None
        if topic.startswith(prefix):
            leaf = topic[len(prefix) :]
        elif "/signalmast/" in topic:
            leaf = topic.split("/signalmast/", 1)[1]
        if leaf is None:
            return
        if "/" in leaf:
            leaf = leaf.split("/", 1)[0]
        if not leaf.isdigit():
            return
        self._apply_mast_payload_to_head(leaf, message)

    def _on_sml_mode(self, message):
        mode = message.strip().lower()
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
        if mode == "enabling":
            if self._enabling_originator:
                print(
                    "mqtt_signalhead: own enabling -- leave SML, wait to announce enabled"
                )
                return
            print("mqtt_signalhead: saw enabling -- abort SML")
            self._abort_sml_immediate()
            return
        # Live Digicon: answer query and disabling so the LCOS bridge can abort RELEASE.
        # Do not ACK during abort (unchecked, not yet re-enabled).
        if (
            mode in ("query", "disabling")
            and self._global_enabled
            and not self._busy
            and not self._abort_in_progress
        ):
            self._publish_mode("enabled")
            print("mqtt_signalhead: ACK %s -> enabled" % mode)

    def propertyChange(self, event):
        name = event.propertyName
        source = event.source
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
        if self._busy or self._boot_pending:
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


controller = DigiconMqttSml(HEAD_NAMES)
controller.start()
