# JMRI jython - at startup, READ MQTT retain and paint JMRI beans only.
#
# One shot. Uses mosquitto_sub (broker pushes retained messages on subscribe).
# This script must NEVER publish to MQTT.
#
#   track/turnout/{addr}  CLOSED | THROWN  -> M2T{addr}  (newKnownState)
#   track/sensor/{addr}   ACTIVE | INACTIVE -> M2S{addr} (setOwnState)
#
# Sensors: setOwnState only (setKnownState on MqttSensor publishes).
# JMRI MQTT 11.3 = _discard/cmd/sensor/{0} (not empty, not field).
#
# Preferences -> Start Up -> Script file (My_JMRI_Railroad / CATS profile).

import os
import subprocess

from jmri import Sensor, Turnout

MQTT_HOST = "minipc-e5h6x.local"
# Retain is delivered immediately on subscribe; keep the wait short.
WAIT_SECS = "1"

_MOSQUITTO_CANDIDATES = (
    "/opt/local/bin/mosquitto_sub",
    "/opt/homebrew/bin/mosquitto_sub",
    "/usr/local/bin/mosquitto_sub",
    "mosquitto_sub",
)


def _mosquitto_sub():
    for p in _MOSQUITTO_CANDIDATES:
        if p == "mosquitto_sub" or os.path.isfile(p):
            return p
    return "mosquitto_sub"


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


def _retained():
    """Return list of (topic, payload) from broker retain. Read-only."""
    exe = _mosquitto_sub()
    cmd = [
        exe,
        "-h",
        MQTT_HOST,
        "-t",
        "track/turnout/#",
        "-t",
        "track/sensor/#",
        "-v",
        "-W",
        WAIT_SECS,
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ignored = proc.communicate()
        rc = proc.returncode
    except Exception as e:
        print("apply_mqtt_retain: mosquitto_sub failed: " + _ascii(e))
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
        print("apply_mqtt_retain: mosquitto_sub rc=%s" % rc)
    return rows


def _is_twosensor(t):
    try:
        return t.getFeedbackMode() == Turnout.TWOSENSOR
    except Exception:
        return False


def _apply_turnout(addr, payload):
    name = "M2T" + str(addr)
    t = turnouts.provideTurnout(name)
    if _is_twosensor(t):
        try:
            t.setInitialKnownStateFromFeedback()
        except Exception:
            pass
        return
    p = payload.upper()
    if p == "THROWN":
        t.newKnownState(Turnout.THROWN)
    elif p == "CLOSED":
        t.newKnownState(Turnout.CLOSED)


def _apply_sensor(addr, payload):
    name = "M2S" + str(addr)
    s = sensors.provideSensor(name)
    p = payload.upper()
    if p == "ACTIVE":
        s.setOwnState(Sensor.ACTIVE)
    elif p == "INACTIVE":
        s.setOwnState(Sensor.INACTIVE)


n_to = n_s = 0
for topic, payload in _retained():
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "track":
        continue
    kind, addr_s = parts[1], parts[2]
    if not addr_s.isdigit():
        continue
    addr = int(addr_s)
    if kind == "turnout":
        _apply_turnout(addr, payload)
        n_to += 1
    elif kind == "sensor":
        _apply_sensor(addr, payload)
        n_s += 1

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
    "apply_mqtt_retain: turnouts=%d sensors=%d twosensor_fb=%d"
    % (n_to, n_s, n_fb)
)
