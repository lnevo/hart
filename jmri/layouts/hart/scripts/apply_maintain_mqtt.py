# JMRI jython — HART standard boot: READ MQTT retain and paint JMRI beans only.
#
# Canonical name: apply_maintain_mqtt.py
# (apply_mqtt_retain_at_startup.py is a thin alias for older Mac profiles.)
#
# One shot. Uses mosquitto_sub (broker pushes retained messages on subscribe).
# This script must NEVER publish to MQTT.
#
#   track/turnout/{addr}  CLOSED | THROWN  -> M2T{addr}  (newKnownState)
#   track/sensor/{addr}   ACTIVE | INACTIVE -> M2S{addr} (setOwnState)
#
# Sensors: setOwnState only (setKnownState on MqttSensor publishes).
# TWOSENSOR turnouts: setInitialKnownStateFromFeedback() after sensors paint.
#
# Preferences -> Start Up -> Script file (after tables.xml).

import os
import socket
import subprocess
import time

import jmri
from jmri import Sensor, Turnout

WAIT_SECS = "2"

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
    # Platform defaults: Pi broker local; Windows ICS → Pi; Mac → Pi mDNS
    for h in ("127.0.0.1", "192.168.137.2", "minipc-e5h6x.local", "localhost"):
        if h not in hosts:
            hosts.append(h)
    return hosts


def _probe_host(host):
    """True if TCP 1883 accepts a connect (broker up)."""
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
    # Fall back to first candidate even if probe failed (mosquitto_sub may still work)
    return _candidate_hosts()[0]


def _retained(host):
    """Return list of (topic, payload) from broker retain. Read-only."""
    exe = _mosquitto_sub()
    cmd = [
        exe,
        "-h",
        host,
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
        print("apply_maintain_mqtt: mosquitto_sub failed: " + _ascii(e))
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


# Brief settle so MQTT connection / tables are present.
try:
    time.sleep(0.5)
except Exception:
    pass

host = _mqtt_host()
print("apply_maintain_mqtt: host=" + _ascii(host) + " exe=" + _ascii(_mosquitto_sub()))

n_to = n_s = 0
for topic, payload in _retained(host):
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
    "apply_maintain_mqtt: turnouts=%d sensors=%d twosensor_fb=%d"
    % (n_to, n_s, n_fb)
)
