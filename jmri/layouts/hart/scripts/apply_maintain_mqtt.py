# JMRI jython — HART standard boot: READ MQTT retain and paint JMRI beans only.
#
# Canonical name: apply_maintain_mqtt.py
# (apply_mqtt_retain_at_startup.py is a thin alias for older Mac profiles.)
#
# Uses mosquitto_sub (broker pushes retained messages on subscribe).
# This script must NEVER publish to MQTT.
#
#   track/turnout/{addr}  — ignored as a command; TWOSENSOR KnownState from FB only
#   track/sensor/{addr}   ACTIVE | INACTIVE -> M2S{addr} (setOwnState)
#
# Sensors: applied immediately (setOwnState — JMRI-only, no Digicon PTS race).
# Turnouts: DEFERRED so Digicon PtsVitalLogic / lock processors finish first.
#   Early SELECTEDREPORT on stock CATS NPEs RREventManager and freezes occupancy.
#   Override delay ms: HART_TURNOUT_RETAIN_DELAY_MS (default 12000).
#   Immediate (old behavior): HART_TURNOUT_RETAIN_DELAY_MS=0
# After turnout paint: Digicon IOSpec.refreshScreen() (Appearance → Refresh Screen)
# so frogs pick up JMRI known state without a manual menu click.
#
# TWOSENSOR turnouts: setInitialKnownStateFromFeedback() in the deferred pass.
# Do not newKnownState MQTT plants — that can publish track/cmd/turnout.
#
# Preferences -> Start Up -> Script file (after tables.xml).

import os
import socket
import subprocess
import time

import jmri
from jmri import Sensor, Turnout

WAIT_SECS = "2"
# After Digicon main init; keep short enough for usable frogs, long enough for PTS.
_DEFAULT_TURNOUT_DELAY_MS = 12000

_MOSQUITTO_CANDIDATES = (
    r"C:\Program Files\mosquitto\mosquitto_sub.exe",
    r"C:\Program Files (x86)\mosquitto\mosquitto_sub.exe",
    "/opt/local/bin/mosquitto_sub",
    "/opt/homebrew/bin/mosquitto_sub",
    "/usr/local/bin/mosquitto_sub",
    "/usr/bin/mosquitto_sub",
    "mosquitto_sub.exe",
    "mosquitto_sub",
)


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


def _mosquitto_sub():
    for p in _MOSQUITTO_CANDIDATES:
        if p in ("mosquitto_sub", "mosquitto_sub.exe") or os.path.isfile(p):
            return p
    return "mosquitto_sub"


def _host_from_jmri_mqtt():
    """Prefer the live JMRI MQTT connection host when available."""
    try:
        memo = jmri.InstanceManager.getDefault(
            jmri.jmrix.mqtt.MqttSystemConnectionMemo
        )
        adapter = memo.getMqttAdapter()
        for meth in ("getHostName", "getCurrentPortName", "getAddress"):
            if hasattr(adapter, meth):
                try:
                    v = getattr(adapter, meth)()
                    if v:
                        v = str(v).strip()
                        if v and v.lower() not in ("localhost",):
                            return v
                        if v:
                            return v
                except Exception:
                    pass
    except Exception:
        pass
    return None


def _candidate_hosts():
    env = os.environ.get("MQTT_HOST") or os.environ.get("HART_MQTT_HOST")
    hosts = []
    if env:
        hosts.append(env.strip())
    j = _host_from_jmri_mqtt()
    if j and j not in hosts:
        hosts.append(j)
    for h in ("127.0.0.1", "192.168.137.2", "minipc-e5h6x.local", "localhost"):
        if h not in hosts:
            hosts.append(h)
    return hosts


def _probe_host(host):
    try:
        s = socket.create_connection((host, 1883), timeout=0.6)
        s.close()
        return True
    except Exception:
        return False


def _mqtt_host():
    for h in _candidate_hosts():
        if _probe_host(h):
            return h
    return _candidate_hosts()[0]


def _retained(host, include_turnouts=True):
    """Return list of (topic, payload) from broker retain. Read-only."""
    exe = _mosquitto_sub()
    cmd = [exe, "-h", host, "-t", "track/sensor/#"]
    if include_turnouts:
        cmd.extend(["-t", "track/turnout/#"])
    cmd.extend(["-v", "-W", WAIT_SECS])
    # Hard cap so a stuck mosquitto_sub cannot freeze Digicon main init.
    # Jython 2.7: no communicate(timeout=) — use a watcher thread + kill.
    try:
        wait_n = int(WAIT_SECS)
    except Exception:
        wait_n = 2
    communicate_timeout = wait_n + 8
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as e:
        print("apply_maintain_mqtt: mosquitto_sub failed: " + _ascii(e))
        return []

    out = None
    rc = -1
    try:
        try:
            out, _ignored = proc.communicate(timeout=communicate_timeout)
            rc = proc.returncode
        except TypeError:
            # Jython: poll with join-style wait
            import threading

            box = [None]

            def _reader():
                box[0] = proc.communicate()

            th = threading.Thread(target=_reader)
            th.setDaemon(True)
            th.start()
            th.join(communicate_timeout)
            if th.isAlive():
                try:
                    proc.kill()
                except Exception:
                    pass
                print(
                    "apply_maintain_mqtt: mosquitto_sub kill after %ss"
                    % communicate_timeout
                )
                return []
            if box[0] is not None:
                out, _ignored = box[0]
            rc = proc.returncode
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        print("apply_maintain_mqtt: mosquitto_sub error: " + _ascii(e))
        return []

    if out is None:
        return []
    if not isinstance(out, str):
        out = out.decode("utf-8", "replace")
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line or " " not in line:
            continue
        if line.lower().startswith("timed out"):
            continue
        topic, payload = line.split(" ", 1)
        if topic.startswith("track/cmd/"):
            continue
        if not (
            topic.startswith("track/turnout/") or topic.startswith("track/sensor/")
        ):
            continue
        rows.append((topic, payload.strip()))
    if rc not in (0, 27):
        print("apply_maintain_mqtt: mosquitto_sub rc=%s host=%s" % (rc, host))
    return rows


def _is_twosensor(t):
    try:
        return t.getFeedbackMode() == Turnout.TWOSENSOR
    except Exception:
        return False


def _apply_turnout(addr, payload):
    """Paint KnownState from FB only. Never newKnownState on MQTT plants.

    newKnownState / setCommandedState on M2T* publishes track/cmd/turnout.
    """
    name = "M2T" + str(addr)
    t = turnouts.getTurnout(name)
    if t is None:
        return
    if _is_twosensor(t):
        try:
            t.setInitialKnownStateFromFeedback()
        except Exception:
            pass


def _sensor_needs_retain(s):
    """True when JMRI has not yet taken a live MQTT sensor value."""
    try:
        st = s.getKnownState()
        return st not in (Sensor.ACTIVE, Sensor.INACTIVE)
    except Exception:
        return True


def _apply_sensor(addr, payload, unknown_only=False):
    name = "M2S" + str(addr)
    s = sensors.provideSensor(name)
    if unknown_only and not _sensor_needs_retain(s):
        return False
    p = payload.upper()
    if p == "ACTIVE":
        s.setOwnState(Sensor.ACTIVE)
        return True
    if p == "INACTIVE":
        s.setOwnState(Sensor.INACTIVE)
        return True
    return False


def _turnout_delay_ms():
    raw = os.environ.get("HART_TURNOUT_RETAIN_DELAY_MS")
    if raw is None or raw == "":
        return _DEFAULT_TURNOUT_DELAY_MS
    try:
        return max(0, int(raw))
    except Exception:
        return _DEFAULT_TURNOUT_DELAY_MS


def _digicon_refresh_screen():
    """Appearance → Refresh Screen: re-pull JMRI IOSpec state into Digicon frogs."""
    try:
        from cats.layout.items import IOSpec

        IOSpec.refreshScreen()
        print("apply_maintain_mqtt: Digicon IOSpec.refreshScreen() done")
        return True
    except Exception as e:
        print(
            "apply_maintain_mqtt: Digicon refreshScreen failed: " + _ascii(e)
        )
        return False


def _paint_turnouts(turnout_rows):
    """Apply retained turnout state + TWOSENSOR feedback. Safe after Digicon PTS up."""
    n_to = 0
    for addr, payload in turnout_rows:
        try:
            _apply_turnout(addr, payload)
            n_to += 1
        except Exception as e:
            print(
                "apply_maintain_mqtt: turnout M2T%s failed: %s"
                % (addr, _ascii(e))
            )
    n_fb = 0
    for t in turnouts.getNamedBeanSet():
        if not _is_twosensor(t):
            continue
        try:
            t.setInitialKnownStateFromFeedback()
            n_fb += 1
        except Exception:
            pass
    print(
        "apply_maintain_mqtt: deferred turnouts=%d twosensor_fb=%d"
        % (n_to, n_fb)
    )
    # newKnownState alone does not always redraw Digicon SELECTEDREPORT frogs;
    # Refresh Screen re-reads IOSpec monitors from JMRI (safe: JMRI → Digicon).
    _digicon_refresh_screen()


# Keep strong refs so Jython GC cannot drop Swing Timer / listener before fire.
_PENDING_TURNOUT_TIMER = None
_PENDING_TURNOUT_LISTENER = None
_PENDING_TURNOUT_ROWS = None


def _schedule_turnout_paint(turnout_rows, delay_ms):
    """Non-blocking: return immediately so Digicon can finish main init."""
    global _PENDING_TURNOUT_TIMER, _PENDING_TURNOUT_LISTENER, _PENDING_TURNOUT_ROWS

    if delay_ms <= 0:
        _paint_turnouts(turnout_rows)
        return

    _PENDING_TURNOUT_ROWS = list(turnout_rows)

    def _run_paint():
        rows = _PENDING_TURNOUT_ROWS or []
        try:
            _paint_turnouts(rows)
        except Exception as e:
            print("apply_maintain_mqtt: deferred paint error: " + _ascii(e))

    # Prefer daemon thread + GUI marshal. Swing Timer alone can lose the Jython
    # ActionListener proxy to GC before fire (no deferred turnouts= line).
    def _run():
        try:
            time.sleep(delay_ms / 1000.0)
        except Exception:
            pass
        try:
            from jmri.util import ThreadingUtil

            ThreadingUtil.runOnGUI(_run_paint)
        except Exception:
            _run_paint()

    try:
        from threading import Thread

        th = Thread(target=_run)
        th.setDaemon(True)
        th.start()
        _PENDING_TURNOUT_TIMER = th  # strong ref until process exit
        print(
            "apply_maintain_mqtt: turnout paint scheduled in %d ms (thread)"
            % delay_ms
        )
        return
    except Exception as e:
        print(
            "apply_maintain_mqtt: thread schedule failed (%s); trying Swing Timer"
            % _ascii(e)
        )

    try:
        from javax.swing import Timer
        from java.awt.event import ActionListener

        class _Deferred(ActionListener):
            def actionPerformed(self, event):
                try:
                    event.getSource().stop()
                except Exception:
                    pass
                _run_paint()

        listener = _Deferred()
        t = Timer(delay_ms, listener)
        t.setRepeats(False)
        _PENDING_TURNOUT_LISTENER = listener
        _PENDING_TURNOUT_TIMER = t
        t.start()
        print(
            "apply_maintain_mqtt: turnout paint scheduled in %d ms (Swing Timer)"
            % delay_ms
        )
    except Exception as e:
        print(
            "apply_maintain_mqtt: schedule failed (%s); painting turnouts now"
            % _ascii(e)
        )
        _paint_turnouts(turnout_rows)


def reload_mqtt_retain(
    turnout_delay_ms=None,
    settle_secs=0.5,
    log_prefix=None,
    paint_turnouts=True,
    unknown_sensors_only=False,
):
    """Read broker retain; paint sensors now; optionally schedule/paint turnouts.

    Returns (sensor_count, turnout_queued). Start Up paints both. Yard-ladder
    boot must pass paint_turnouts=False so this never touches plant turnouts.

    turnout_delay_ms: None → HART_TURNOUT_RETAIN_DELAY_MS / default 12000;
    0 → paint turnouts immediately (use only when Digicon PTS is already up).
    unknown_sensors_only: only setOwnState when the bean is still UNKNOWN.
    """
    prefix = log_prefix or "apply_maintain_mqtt"
    if settle_secs and settle_secs > 0:
        try:
            time.sleep(settle_secs)
        except Exception:
            pass

    host = _mqtt_host()
    print(
        "%s: host=%s exe=%s"
        % (prefix, _ascii(host), _ascii(_mosquitto_sub()))
    )

    retained = _retained(host, include_turnouts=paint_turnouts)
    turnout_rows = []
    n_s = 0
    for topic, payload in retained:
        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != "track":
            continue
        kind, addr_s = parts[1], parts[2]
        if not addr_s.isdigit():
            continue
        addr = int(addr_s)
        if kind == "sensor":
            try:
                if _apply_sensor(addr, payload, unknown_only=unknown_sensors_only):
                    n_s += 1
            except Exception as e:
                print(
                    "%s: sensor M2S%s failed: %s"
                    % (prefix, addr, _ascii(e))
                )
        elif paint_turnouts and kind == "turnout":
            turnout_rows.append((addr, payload))

    print(
        "%s: sensors=%d turnouts_queued=%d"
        % (prefix, n_s, len(turnout_rows) if paint_turnouts else 0)
    )

    if not paint_turnouts:
        return n_s, 0

    delay = _turnout_delay_ms() if turnout_delay_ms is None else max(0, int(turnout_delay_ms))
    _schedule_turnout_paint(turnout_rows, delay)
    return n_s, len(turnout_rows)


# Start Up entry point. Importers set _HART_MQTT_RETAIN_AS_LIBRARY first.
if not globals().get("_HART_MQTT_RETAIN_AS_LIBRARY"):
    reload_mqtt_retain()
