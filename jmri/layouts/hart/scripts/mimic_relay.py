# mimic_relay.py - publishes LCOS-style feedback for the JMRI-hosted mimic page.
#
# The page (preference:web/mimic/, served at /web/mimic/) reads layout state through
# the JMRI JSON WebSocket. To fake LCOS feedback it writes one request into memory
# IMHART_MIMIC; this script publishes each line of it, retained, through JMRI's own
# MQTT connection, exactly as the old Mac mimic (tools/mqtt-mimic) did with
# mosquitto_pub -r.
#
# A request is "<sequence>\n<topic> <payload>\n<topic> <payload>...". The sequence
# makes every request a new memory value, so a repeated click still fires. "<sequence>\nping"
# asks whether the relay is listening. Every request is answered by replacing the value
# with "ack <sequence>", so the page knows the relay heard it and a PanelPro Store only
# ever saves that short value.
#
# Only these are ever published:
#   track/sensor/<digits>   ACTIVE | INACTIVE
#   track/turnout/<digits>  CLOSED | THROWN
# Anything else, track/cmd/... included, is dropped. This never moves a motor.
# Runs from the Pi Start Up. Python 2 (Jython) and 3 compatible; no print_function.

import re

import jmri
from java.beans import PropertyChangeListener

MEMORY = "IMHART_MIMIC"
MAX_LINES = 500
_LINE = re.compile(r"^track/(sensor|turnout)/([0-9]{1,6}) ([A-Z]+)$")
_ALLOWED = {
    "sensor": ("ACTIVE", "INACTIVE"),
    "turnout": ("CLOSED", "THROWN"),
}


def _lines(value):
    if value is None:
        return []
    try:
        text = u"%s" % (value,)
    except Exception:
        return []
    return [l.strip() for l in text.splitlines() if l.strip()]


def is_request(value):
    """A page request: first line a sequence number (acks start with "ack")."""
    lines = _lines(value)
    return bool(lines) and lines[0].isdigit()


def parse_request(value):
    """Return ([(topic, payload)...], rejected_count) for one memory value."""
    lines = _lines(value)
    if not lines:
        return [], 0
    body = [l for l in lines[1:] if l != "ping"]  # first line is the sequence
    good = []
    rejected = 0
    for line in body[:MAX_LINES]:
        m = _LINE.match(line)
        if m is None or m.group(3) not in _ALLOWED[m.group(1)]:
            rejected += 1
            continue
        good.append(("track/%s/%s" % (m.group(1), m.group(2)), str(m.group(3))))
    rejected += max(0, len(body) - MAX_LINES)
    return good, rejected


def _mqtt_adapter():
    try:
        memo = jmri.InstanceManager.getDefault(jmri.jmrix.mqtt.MqttSystemConnectionMemo)
        if memo is None:
            return None
        return memo.getMqttAdapter()
    except Exception:
        return None


def _publish(adapter, topic, payload):
    try:
        adapter.publish(topic, payload, True)
    except TypeError:
        print("mimic_relay: retained publish unavailable, sent %s without retain" % topic)
        adapter.publish(topic, payload)


def handle(value, adapter=None):
    """Publish one request. Returns the number of messages sent."""
    good, rejected = parse_request(value)
    if rejected:
        print("mimic_relay: dropped %d line(s) that are not LCOS feedback" % rejected)
    if not good:
        return 0
    adapter = adapter or _mqtt_adapter()
    if adapter is None:
        print("mimic_relay: no MQTT connection, nothing published")
        return 0
    sent = 0
    for topic, payload in good:
        try:
            _publish(adapter, topic, payload)
            sent += 1
        except Exception as exc:
            print("mimic_relay: publish failed %s %s: %s" % (topic, payload, exc))
    return sent


class _Listener(PropertyChangeListener):
    hart_mimic_relay = True  # marks our listener so a re-run can find and replace it

    def propertyChange(self, event):
        if event.getPropertyName() != "value" or not is_request(event.getNewValue()):
            return
        try:
            handle(event.getNewValue())
        except Exception as exc:
            print("mimic_relay: request failed: %s" % (exc,))
        try:
            event.getSource().setValue("ack " + _lines(event.getNewValue())[0])
        except Exception as exc:
            print("mimic_relay: ack failed: %s" % (exc,))


def install():
    memory = memories.provideMemory(MEMORY)  # noqa: F821 - JMRI Jython global
    if memory.getUserName() is None:
        memory.setUserName("Mimic relay")
    for old in list(memory.getPropertyChangeListeners()):
        if getattr(old, "hart_mimic_relay", False):
            memory.removePropertyChangeListener(old)
    memory.addPropertyChangeListener(_Listener())
    print("mimic_relay: listening on %s" % MEMORY)
    return memory


install()
