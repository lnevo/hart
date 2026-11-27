# Drive HART Railroad status lamps and wire clicks on LCOS / Turnouts /
# Signals / Track Power panel icons. Never setCommandedState on M2T*/MTT*.
#
# Turnouts lamp (Green / Yellow / Red): among M2T* and MTT* that have both FB
# sensors assigned — all TWOSENSOR → Green; all DIRECT → Red; mixed → Yellow.
# Click: toggle those plants between TWOSENSOR and DIRECT.
#
# Signals lamp (IS:SML_MODE): click → DigiconMqttSml.toggle_from_panel().
# LCOS lamp (M2S1567): click → MQTT track/bridge/cmd RESUBSCRIBE (not FORCE).
# Track Power lamp (IS:TRACK_POWER): mirrors LCC PowerManager; click toggles ON/OFF.
#
# Lamps arm as soon as plant turnouts exist. Panel click wiring retries
# quietly afterward (do not block on Layout Editor — EditorManager often lags).

import jmri
import sys
from java.awt.event import ActionListener
from java.beans import PropertyChangeListener
from java.lang import Runnable
from javax.swing import SwingUtilities, Timer

# This script's sibling modules, beside it in preference:jython, in load order: each comes after every sibling it
# imports. The script imports them through jython_siblings.py, which reloads each on a re-run. The deploy ships
# each one beside the script (tools/hosts/tests/test_coordinator_shipping.py holds every host's list to this
# tuple).
PARTS = (
    "panel_status_clicks",
    "panel_status_turnouts",
)


def _sibling_loader():
    """jython_siblings.py from preference:jython, reloaded if an earlier run imported it; returns (module, folder).

    JMRI runs this script with no __file__ and not from its folder, so the folder comes from FileUtil and goes on
    sys.path. signal_coordinator.py starts the same way: these lines run before the shared loader is imported.
    """
    import os

    folder = jmri.util.FileUtil.getExternalFilename("preference:jython")
    if not folder or not os.path.isfile(os.path.join(folder, "jython_siblings.py")):
        raise ImportError("panel_status: no jython_siblings.py in the jython folder %r "
                          "(the folder is missing or the deploy left the loader out)"
                          % (folder,))
    if folder not in sys.path:
        sys.path.insert(0, folder)
    cached = sys.modules.get("jython_siblings")
    if cached is None:
        import jython_siblings as cached
    else:
        cached = cached.reload_module(cached)
    return cached, folder


_loader, _folder = _sibling_loader()
_loader.load("panel_status", _folder, PARTS)
print("panel_status: parts %s from %s" % (", ".join(PARTS), _folder))

from panel_status_clicks import _lamp_at, _PanelLampClick, _raise_block_labels  # noqa: E402,F401 (_lamp_at: tests)
from panel_status_clicks import arm_status_lamp_clicks  # noqa: E402
from panel_status_turnouts import (  # noqa: E402,F401 (_ensure_turnout_fb_head: the tests)
    TURNOUT_FB_HEAD, _LAMP_AMBER_MS, _after_paint, _ensure_turnout_fb_head, _included_plant_turnouts, _is_plant,
    _note_plant, _paint_turnout_fb_lamp, sync_turnout_fb_lamp, toggle_turnout_fb_mode,
)

LCOS_SENSOR = "M2S1567"
SML_MODE_SENSOR = "IS:SML_MODE"
TRACK_POWER_SENSOR = "IS:TRACK_POWER"
BRIDGE_CMD_TOPIC = "track/bridge/cmd"
RESUBSCRIBE_PAYLOAD = "RESUBSCRIBE"

# Lamps: short settle, then arm when plant turnouts exist (no LE gate).
_ARM_FIRST_MS = 1000
_ARM_RETRY_MS = 1000
_ARM_MAX_ATTEMPTS = 15
# Clicks: quiet background retries after panel contents appear.
_CLICK_RETRY_MS = 2000
_CLICK_MAX_ATTEMPTS = 30

_armed = False
_listener = None
_plant_count = 0

# Every listener this script attaches carries this attribute, so a second run of the script can find the first
# run's listeners and remove them (otherwise one click toggles twice). Same approach as mimic_relay.py. Each arm
# step drops the earlier run's listeners just before it attaches its own, so the old ones keep working until then.
_MARK = "hart_panel_status"
# The same classes before they carried _MARK (a re-run straight after the deploy that added it).
_UNMARKED_CLASSES = ("_TurnoutListener", "_PowerListener", "_PanelLampClick")


def _ours(listener):
    return bool(getattr(listener, _MARK, False)) or type(listener).__name__ in _UNMARKED_CLASSES


# A re-run's id, kept on __main__ (shared by every script run in this JMRI). The arm and click retry timers of an
# earlier run see a newer id there and stop, so two runs never arm against each other.
import __main__ as _main  # noqa: E402

_RUN_ID = getattr(_main, "hart_panel_status_run", 0) + 1
_main.hart_panel_status_run = _RUN_ID


def _superseded(run_id):
    """True when a later run of this script has started."""
    return getattr(_main, "hart_panel_status_run", run_id) != run_id


def _drop_ours(listeners, remove, keep=None):
    """Remove every listener of ours except `keep`; returns how many went."""
    n = 0
    for old in list(listeners):
        if old is not keep and _ours(old):
            try:
                remove(old)
                n += 1
            except Exception as e:
                print("panel_status: detach failed: %s" % e)
    return n



def _show_amber_sensor(sys_name):
    """Pending click feedback on LCOS/Signals (INCONSISTENT → yellow icon)."""
    try:
        s = sensors.getSensor(sys_name)
        if s is None:
            s = sensors.provideSensor(sys_name)
        s.setKnownState(jmri.Sensor.INCONSISTENT)
    except Exception as e:
        print("panel_status: amber %s failed: %s" % (sys_name, e))


def _mqtt_publish(topic, payload):
    try:
        memo = jmri.InstanceManager.getDefault(
            jmri.jmrix.mqtt.MqttSystemConnectionMemo
        )
        if memo is None:
            print("panel_status: no MQTT connection")
            return False
        adapter = memo.getMqttAdapter()
        if adapter is None:
            print("panel_status: no MQTT adapter")
            return False
        # Host commands to the bridge are not retained. JMRI's two-argument publish retains,
        # so the flag is named here. The three-argument form needs JMRI 5.9.1 or later.
        adapter.publish(topic, payload, False)
        return True
    except Exception as e:
        print("panel_status: MQTT publish failed: %s" % e)
        return False


def _restore_lcos_lamp(prev_state):
    """After RESUBSCRIBE: keep MQTT update if it arrived; else restore prior."""

    class _Restore(ActionListener):
        def actionPerformed(self, event):
            event.getSource().stop()
            try:
                s = sensors.getSensor(LCOS_SENSOR)
                if s is None:
                    return
                if s.getKnownState() != jmri.Sensor.INCONSISTENT:
                    return  # bridge/MQTT already painted final
                if prev_state in (jmri.Sensor.ACTIVE, jmri.Sensor.INACTIVE):
                    s.setKnownState(prev_state)
                else:
                    s.setKnownState(jmri.Sensor.INACTIVE)
            except Exception as e:
                print("panel_status: LCOS restore failed: %s" % e)

    # RESUBSCRIBE is fire-and-forget; give the bridge a moment to refresh HBLOOP.
    t = Timer(2000, _Restore())
    t.setRepeats(False)
    t.start()


def publish_lcos_resubscribe():
    """Click LCOS lamp: amber → RESUBSCRIBE (not FORCE) → restore/final."""
    prev = jmri.Sensor.UNKNOWN
    try:
        s = sensors.getSensor(LCOS_SENSOR)
        if s is not None:
            prev = s.getKnownState()
    except Exception as e:
        print("panel_status: LCOS lamp state unreadable, restoring to INACTIVE: %s" % e)
    _show_amber_sensor(LCOS_SENSOR)

    def _do():
        if _mqtt_publish(BRIDGE_CMD_TOPIC, RESUBSCRIBE_PAYLOAD):
            print(
                "panel_status: LCOS lamp → %s %s"
                % (BRIDGE_CMD_TOPIC, RESUBSCRIBE_PAYLOAD)
            )
        _restore_lcos_lamp(prev)

    _after_paint(_do)


# While Digicon is busy (a hold or hand-off), the Signals lamp watch polls every
# _SML_WATCH_MS for up to _SML_WATCH_MAX_ATTEMPTS tries (20 s) before it repaints.
_SML_WATCH_MS = 500
_SML_WATCH_MAX_ATTEMPTS = 40


def _digicon_controller():
    """The running DigiconMqttSml, or None: signal_coordinator.py keeps it on __main__
    (shared by every script in this JMRI) as digicon_sml_controller."""
    import __main__

    return getattr(__main__, "digicon_sml_controller", None)


def _watch_sml_amber_clear():
    """If Digicon finishes (or stalls), ensure Signals lamp leaves amber."""

    class _Watch(ActionListener):
        def __init__(self, attempt):
            self.attempt = attempt

        def actionPerformed(self, event):
            event.getSource().stop()
            try:
                s = sensors.getSensor(SML_MODE_SENSOR)
                if s is None or s.getKnownState() != jmri.Sensor.INCONSISTENT:
                    return
                ctrl = _digicon_controller()
                busy = bool(ctrl is not None and getattr(ctrl, "_busy", False))
                if busy and self.attempt < _SML_WATCH_MAX_ATTEMPTS:
                    t = Timer(_SML_WATCH_MS, _Watch(self.attempt + 1))
                    t.setRepeats(False)
                    t.start()
                    return
                if ctrl is not None:
                    try:
                        ctrl._sync_sml_mode_sensor()
                        return
                    except Exception as e:
                        print("panel_status: Digicon lamp sync failed, lamp set INACTIVE: %s" % e)
                # No controller to repaint the lamp: show it Disabled.
                s.setKnownState(jmri.Sensor.INACTIVE)
            except Exception as e:
                print("panel_status: SML amber clear failed: %s" % e)

    t = Timer(_SML_WATCH_MS, _Watch(0))
    t.setRepeats(False)
    t.start()


def toggle_sml_mode():
    """Click Signals lamp: amber → Digicon SML toggle → Digicon paints final."""
    _show_amber_sensor(SML_MODE_SENSOR)

    def _do():
        ctrl = _digicon_controller()
        if ctrl is None:
            print(
                "panel_status: Digicon SML controller not found "
                "(is signal_coordinator running?)"
            )
            try:
                sensors.provideSensor(SML_MODE_SENSOR).setKnownState(
                    jmri.Sensor.INACTIVE
                )
            except Exception as e:
                print("panel_status: Signals lamp reset failed: %s" % e)
            return
        try:
            ctrl.toggle_from_panel()
        except Exception as e:
            print("panel_status: SML toggle failed: %s" % e)
        _watch_sml_amber_clear()

    _after_paint(_do)


def _power_manager():
    """The default PowerManager (the LCC connection's), or None when JMRI has none."""
    return jmri.InstanceManager.getNullableDefault(jmri.PowerManager)


def _sync_track_power_sensor():
    """Drive Track Power lamp from JMRI LCC/OpenLCB PowerManager."""
    try:
        s = sensors.provideSensor(TRACK_POWER_SENSOR)
    except Exception as e:
        print("panel_status: Track Power sensor unavailable: %s" % e)
        return
    pm = _power_manager()
    if pm is None:
        return
    try:
        on = pm.getPower() == jmri.PowerManager.ON
    except Exception as e:
        print("panel_status: Track Power state unreadable, lamp left as it is: %s" % e)
        return
    want = jmri.Sensor.ACTIVE if on else jmri.Sensor.INACTIVE
    try:
        if s.getKnownState() != want:
            s.setKnownState(want)
    except Exception as e:
        print("panel_status: Track Power lamp set failed: %s" % e)


class _PowerListener(PropertyChangeListener):
    hart_panel_status = True  # _MARK: a re-run finds and replaces it

    def propertyChange(self, event):
        try:
            if event.getPropertyName() == "power":
                _sync_track_power_sensor()
        except Exception as e:
            print("panel_status: power listener error: %s" % e)


_power_listener = None


def _arm_power_listener():
    global _power_listener
    if _power_listener is not None:
        return
    pm = _power_manager()
    if pm is None:
        print("panel_status: no PowerManager -- the Track Power lamp is not driven")
        return
    _power_listener = _PowerListener()
    _drop_ours(pm.getPropertyChangeListeners(), pm.removePropertyChangeListener)
    pm.addPropertyChangeListener(_power_listener)


def toggle_track_power():
    """Click Track Power lamp: amber → PowerManager ON/OFF → sync sensor."""
    _show_amber_sensor(TRACK_POWER_SENSOR)

    def _do():
        pm = _power_manager()
        if pm is None:
            print("panel_status: no PowerManager for Track Power toggle")
            _sync_track_power_sensor()
            return
        try:
            if pm.getPower() == jmri.PowerManager.ON:
                pm.setPower(jmri.PowerManager.OFF)
                label = "OFF"
            else:
                pm.setPower(jmri.PowerManager.ON)
                label = "ON"
            print("panel_status: Track Power lamp click → %s" % label)
        except Exception as e:
            print("panel_status: Track Power toggle failed: %s" % e)
        _sync_track_power_sensor()

    _after_paint(_do, delay_ms=_LAMP_AMBER_MS)


def sync_lamps(event=None):
    """The lamps that follow plant state: the Turnouts lamp (sync_turnout_fb_lamp catches its own errors)."""
    sync_turnout_fb_lamp()


_sync_timer = Timer(250, None)
_sync_timer.setRepeats(False)


class _DebouncedSync(ActionListener):
    def actionPerformed(self, event):
        # turnout events have already updated their own cache entries; repaint without a full scan
        _paint_turnout_fb_lamp()


_sync_timer.addActionListener(_DebouncedSync())


def _schedule_sync():
    class _Restart(Runnable):
        def run(self):
            _sync_timer.restart()

    try:
        if SwingUtilities.isEventDispatchThread():
            _sync_timer.restart()
        else:
            SwingUtilities.invokeLater(_Restart())
    except Exception as e:
        print("panel_status: schedule failed: %s" % e)


class _TurnoutListener(PropertyChangeListener):
    hart_panel_status = True  # _MARK: a re-run finds and replaces it

    def propertyChange(self, event):
        try:
            name = event.getPropertyName()
            if name in ("KnownState", "FeedbackMode", "Sensor1", "Sensor2"):
                _note_plant(event.getSource())
                _schedule_sync()
        except Exception as e:
            print("panel_status: listener error: %s" % e)



def _arm_status_lamp_clicks():
    """Wire the four status lamps' clicks (panel_status_clicks.arm_status_lamp_clicks); True once all are found."""
    return arm_status_lamp_clicks(
        {
            LCOS_SENSOR: ("lcos", publish_lcos_resubscribe),
            SML_MODE_SENSOR: ("signals", toggle_sml_mode),
            TRACK_POWER_SENSOR: ("power", toggle_track_power),
        },
        {TURNOUT_FB_HEAD: ("turnouts", toggle_turnout_fb_mode)},
        _drop_ours,
    )


def _arm_listeners():
    """Attach plant listeners once (the Turnouts lamp). Independent of panel icons.

    Every M2T/MTT turnout gets one, not only those with both feedback sensors, so a plant that gains its second
    sensor later joins the lamp on its own event (_note_plant decides which are included)."""
    global _armed, _listener, _plant_count
    if _armed:
        return True
    _listener = _TurnoutListener()
    _plant_count = len(_included_plant_turnouts())
    try:
        plants = [to for to in turnouts.getNamedBeanSet() if _is_plant(to)]
    except Exception as e:
        print("panel_status: scan turnouts failed: %s" % e)
        plants = []
    for to in plants:
        try:
            _drop_ours(to.getPropertyChangeListeners(), to.removePropertyChangeListener)
            to.addPropertyChangeListener(_listener)
        except Exception as e:
            print("panel_status: listener not attached to %s: %s" % (to.getSystemName(), e))
    _armed = True
    print("panel_status: armed (plantFB=%d)" % _plant_count)
    return True


class _ArmAttempt(ActionListener):
    """Arm once the plant turnouts have loaded: some present and their count unchanged since the last try, so a
    connection that registers its turnouts later is not left without listeners."""
    def __init__(self, attempt, last=-1):
        self.attempt = attempt
        self.last = last
        self.run = _RUN_ID

    def actionPerformed(self, event):
        event.getSource().stop()
        if _superseded(self.run):
            return
        n = len(_included_plant_turnouts())
        if n == 0 or n != self.last:
            if self.attempt + 1 >= _ARM_MAX_ATTEMPTS:
                print("panel_status: plant turnouts not settled (%d); arming anyway" % n)
            else:
                if self.attempt == 0:
                    print("panel_status: waiting for plant turnouts…")
                t = Timer(_ARM_RETRY_MS, _ArmAttempt(self.attempt + 1, n))
                t.setRepeats(False)
                t.start()
                return
        try:
            _arm_listeners()
            _arm_power_listener()
            _sync_track_power_sensor()
            _raise_block_labels()
            sync_lamps()
        except Exception as e:
            print("panel_status: arm failed: %s" % e)
        t = Timer(_CLICK_RETRY_MS, _RetryClicks(0))
        t.setRepeats(False)
        t.start()


class _RetryClicks(ActionListener):
    def __init__(self, attempt):
        self.attempt = attempt
        self.run = _RUN_ID

    def actionPerformed(self, event):
        event.getSource().stop()
        if _superseded(self.run):
            return
        try:
            if _arm_status_lamp_clicks():
                return
        except Exception as e:
            print("panel_status: click retry failed: %s" % e)
        if self.attempt + 1 < _CLICK_MAX_ATTEMPTS:
            t = Timer(_CLICK_RETRY_MS, _RetryClicks(self.attempt + 1))
            t.setRepeats(False)
            t.start()
        else:
            print("panel_status: status lamp icons not found on panel")


print("panel_status: loaded; arming in %dms" % _ARM_FIRST_MS)
_t0 = Timer(_ARM_FIRST_MS, _ArmAttempt(0))
_t0.setRepeats(False)
_t0.start()
