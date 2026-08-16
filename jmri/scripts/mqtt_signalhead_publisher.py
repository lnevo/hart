# JMRI jython — Virtual Signal Heads + Brick relay-lamp status.
#
# Name kept as mqtt_signalhead_publisher.py for existing profile Start Up entries.
#
#   track/signalhead/IH###  GREEN|YELLOW|RED|DARK|…
#
# Boot: read broker retain once and setAppearance in JMRI only (no publish).
# Then: listen for Appearance changes (CATS / CATS ABS / Digicon) and publish
# JMRI → MQTT with retain=True so a restart can paint IH* from the broker and
# Digicon Stop→Stop (unchanged) does not re-queue every head.
#
# Brick physical lamps (interim): LH464 Triple Output → LCOS Relay Obj 1/2/3 on node 4
# (packed 452/453/454 = Stop/Approach/Clear). On Appearance, publish
# track/cmd/turnout/<n> and track/turnout/<n> THROWN|CLOSED so the Nano bridge
# issues EVENT_CONTROL_CMD and MONITORING feedback stays in sync.
#
# Do not publish the retain-paint pass — that would echo defaults and stomp SoR.
# Field aspect status is track/signalmast/432 (API UID 32), not 464.
# Generated head list: cats/scripts/build_hart_signal_heads.py
#
# Preferences -> Start Up -> Script file (after tables.xml + apply_maintain_mqtt).

import os
import socket
import subprocess
import time

import java
import jmri
from jmri import SignalHead

WAIT_SECS = "2"
TOPIC_PREFIX = "track/signalhead/"
CMD_TURNOUT_PREFIX = "track/cmd/turnout/"
TURNOUT_STATE_PREFIX = "track/turnout/"

# Brick physical lamps via relays are paused (mast is MQTT $432 again). Keep map for later.
RELAY_LAMP_HEAD = "LH464"
RELAY_LAMP_PACKED = {
    "red": "452",
    "yellow": "453",
    "green": "454",
}
RELAY_LAMP_ENABLED = False

# Packed IH heads from cats/data/signal_wiring.csv (build_hart_signal_heads.py).
HEAD_NAMES = [
    "IH432",
    "IH433",
    "IH434",
    "IH435",
    "IH436",
    "IH437",
    "IH1332",
    "IH1333",
    "IH1334",
    "IH1335",
    "IH1336",
    "IH1337",
    "IH1338",
    "IH1232",
    "IH1233",
    "IH1234",
    "IH1235",
    "IH1236",
    "IH1237",
    "IH1238",
    "IH1239",
    "IH1240",
    "IH1241",
    "IH132",
    "IH133",
    "IH134",
    "IH135",
    "IH136",
    "IH137",
    "IH138",
    "IH139",
    "IH140",
    "IH141",
]

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

_APPEARANCE = {
    "GREEN": SignalHead.GREEN,
    "YELLOW": SignalHead.YELLOW,
    "RED": SignalHead.RED,
    "LUNAR": SignalHead.LUNAR,
    "DARK": SignalHead.DARK,
    "FLASHGREEN": SignalHead.FLASHGREEN,
    "FLASHYELLOW": SignalHead.FLASHYELLOW,
    "FLASHRED": SignalHead.FLASHRED,
    "FLASHLUNAR": SignalHead.FLASHLUNAR,
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


def _mosquitto_sub():
    for p in _MOSQUITTO_CANDIDATES:
        if p in ("mosquitto_sub", "mosquitto_sub.exe") or os.path.isfile(p):
            return p
    return "mosquitto_sub"


def _host_from_jmri_mqtt():
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
                        return str(v).strip()
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


def _retained(host):
    """Return list of (topic, payload) for track/signalhead/#. Read-only."""
    exe = _mosquitto_sub()
    cmd = [
        exe,
        "-h",
        host,
        "-t",
        "track/signalhead/#",
        "-v",
        "-W",
        WAIT_SECS,
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, _ignored = proc.communicate()
        rc = proc.returncode
    except Exception as e:
        print("mqtt_signalhead: mosquitto_sub failed: " + _ascii(e))
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
        if not topic.startswith("track/signalhead/"):
            continue
        rows.append((topic, payload.strip()))
    if rc not in (0, 27):
        print("mqtt_signalhead: mosquitto_sub rc=%s host=%s" % (rc, host))
    return rows


def _apply_head(sys_name, payload):
    head = signals.getSignalHead(sys_name)
    if head is None:
        return False
    key = payload.strip().upper().replace(" ", "")
    appearance = _APPEARANCE.get(key)
    if appearance is None:
        print(
            "mqtt_signalhead: skip %s unknown appearance %s"
            % (_ascii(sys_name), _ascii(payload))
        )
        return False
    # Boot paint only — listeners are not attached yet, so this does not publish.
    head.setAppearance(appearance)
    return True


class HartMqttSignalHeadPublisher(java.beans.PropertyChangeListener):
    def __init__(self, topic_prefix, head_names):
        self.topic_prefix = topic_prefix
        self.head_names = list(head_names)
        self.mqtt = None
        self._last_pub = {}

    def start(self):
        memo = jmri.InstanceManager.getDefault(jmri.jmrix.mqtt.MqttSystemConnectionMemo)
        self.mqtt = memo.getMqttAdapter()
        for name in self.head_names:
            head = signals.getSignalHead(name)
            if head is None:
                print("HartMqttSignalHeadPublisher: missing head", name)
                continue
            # Remember boot-painted appearance so Digicon Stop→Stop does not re-MQTT.
            try:
                self._last_pub[name] = _ascii(head.getAppearanceName()).strip().upper()
            except Exception:
                self._last_pub[name] = ""
            head.addPropertyChangeListener(self)
            print("HartMqttSignalHeadPublisher: listening", name)
        return

    def propertyChange(self, event):
        if event.propertyName == "Appearance":
            self._publish(event.source)
        return

    def _publish(self, head):
        name = head.getSystemName()
        topic = self.topic_prefix + name
        data = head.getAppearanceName()
        key = _ascii(data).strip().upper()
        if self._last_pub.get(name) == key:
            return
        self._last_pub[name] = key
        print("HartMqttSignalHeadPublisher:", topic, data, "(retain)")
        # Explicit retain so broker keeps last Digicon aspect across CATS restarts.
        self.mqtt.publish(topic, data, True)
        return


class HartRelayLampPublisher(java.beans.PropertyChangeListener):
    """Publish LCOS relay-band turnout cmd + state for a Triple Output head."""

    def __init__(self, head_name, packed_by_color):
        self.head_name = head_name
        self.packed_by_color = dict(packed_by_color)
        self.mqtt = None

    def start(self):
        memo = jmri.InstanceManager.getDefault(jmri.jmrix.mqtt.MqttSystemConnectionMemo)
        self.mqtt = memo.getMqttAdapter()
        head = signals.getSignalHead(self.head_name)
        if head is None:
            print("HartRelayLampPublisher: missing head", self.head_name)
            return
        head.addPropertyChangeListener(self)
        print(
            "HartRelayLampPublisher: listening",
            self.head_name,
            "relays",
            self.packed_by_color,
        )
        self._publish(head)
        return

    def propertyChange(self, event):
        if event.propertyName == "Appearance":
            self._publish(event.source)
        return

    def _appearance_key(self, head):
        try:
            name = head.getAppearanceName()
        except Exception:
            name = ""
        key = _ascii(name).strip().upper().replace(" ", "")
        if key in ("FLASHRED",):
            return "RED"
        if key in ("FLASHYELLOW", "LUNAR", "FLASHLUNAR"):
            return "YELLOW"
        if key in ("FLASHGREEN",):
            return "GREEN"
        if key in ("RED", "YELLOW", "GREEN", "DARK", "OFF"):
            return key if key != "OFF" else "DARK"
        # Numeric appearance constants
        try:
            a = head.getAppearance()
            if a == SignalHead.RED or a == SignalHead.FLASHRED:
                return "RED"
            if a in (SignalHead.YELLOW, SignalHead.FLASHYELLOW, SignalHead.LUNAR, SignalHead.FLASHLUNAR):
                return "YELLOW"
            if a == SignalHead.GREEN or a == SignalHead.FLASHGREEN:
                return "GREEN"
        except Exception:
            pass
        return "DARK"

    def _publish(self, head):
        aspect = self._appearance_key(head)
        on_color = None
        if aspect == "RED":
            on_color = "red"
        elif aspect == "YELLOW":
            on_color = "yellow"
        elif aspect == "GREEN":
            on_color = "green"
        for color, packed in self.packed_by_color.items():
            state = "THROWN" if color == on_color else "CLOSED"
            cmd_topic = CMD_TURNOUT_PREFIX + packed
            state_topic = TURNOUT_STATE_PREFIX + packed
            print("HartRelayLampPublisher:", cmd_topic, state, "(aspect=%s)" % aspect)
            self.mqtt.publish(cmd_topic, state, False)
            self.mqtt.publish(state_topic, state, True)
        return


try:
    time.sleep(0.5)
except Exception:
    pass

wanted = set(HEAD_NAMES)
host = _mqtt_host()
print(
    "mqtt_signalhead: host=%s exe=%s heads=%d (retain paint, then publish)"
    % (_ascii(host), _ascii(_mosquitto_sub()), len(wanted))
)

n = 0
for topic, payload in _retained(host):
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "track" or parts[1] != "signalhead":
        continue
    name = parts[2]
    if name not in wanted:
        continue
    if _apply_head(name, payload):
        n += 1

print("mqtt_signalhead: painted %d heads from broker retain (no publish)" % n)

publisher = HartMqttSignalHeadPublisher(TOPIC_PREFIX, HEAD_NAMES)
publisher.start()

relay_pub = HartRelayLampPublisher(RELAY_LAMP_HEAD, RELAY_LAMP_PACKED)
if RELAY_LAMP_ENABLED:
    relay_pub.start()
else:
    print("HartRelayLampPublisher: skipped (RELAY_LAMP_ENABLED=False; Brick mast is MQTT 432)")
