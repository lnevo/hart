# JMRI jython — publish Virtual head appearances to MQTT from SML / SHSM masts.
#
# Name kept as mqtt_signalhead_publisher.py for existing profile Start Up entries.
#
#   track/signalhead/IH###  GREEN|YELLOW|RED|DARK|…
#
# JMRI's MQTT connection is the transport. SML owns aspects at startup and
# shutdown; this script does not read broker retain or write head appearances.
# Generated HEAD_NAMES: cats/scripts/build_hart_signal_heads.py
# (signal_wiring.csv). Keep the HEAD_NAMES_BEGIN/END markers.

import java
import jmri
import re

TOPIC_PREFIX = "track/signalhead/"

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

_HEAD_IN_MAST = re.compile(r"\(IH\d+\)")


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


def _head_names_on_mast(mast):
    """IH* heads encoded on a SignalHeadSignalMast systemName."""
    names = []
    for token in _HEAD_IN_MAST.findall(str(mast.getSystemName())):
        names.append(token[1:-1])
    return names


class HartMqttSignalPublisher(java.beans.PropertyChangeListener):
    """Push SHSM / SML head appearances onto track/signalhead/IH* via JMRI MQTT."""

    def __init__(self, topic_prefix, head_names):
        self.topic_prefix = topic_prefix
        self.wanted = set(head_names)
        self.mqtt = None
        self._masts = []
        self._heads = []

    def start(self):
        self.mqtt = _mqtt_adapter()
        if self.mqtt is None:
            print("mqtt_signalhead: no JMRI MQTT connection; not publishing")
            return
        mm = _mast_manager()
        hm = _head_manager()
        if mm is not None:
            for mast in mm.getNamedBeanSet():
                heads = _head_names_on_mast(mast)
                if not [name for name in heads if name in self.wanted]:
                    continue
                mast.addPropertyChangeListener(self)
                self._masts.append(mast)
        if hm is not None:
            for name in self.wanted:
                head = hm.getSignalHead(name)
                if head is None:
                    print("mqtt_signalhead: missing head " + _ascii(name))
                    continue
                head.addPropertyChangeListener(self)
                self._heads.append(head)
        print(
            "mqtt_signalhead: JMRI MQTT, %d masts, %d heads"
            % (len(self._masts), len(self._heads))
        )

    def propertyChange(self, event):
        name = event.propertyName
        source = event.source
        if name in ("Aspect", "Held", "Lit"):
            self._publish_mast(source)
            return
        if name == "Appearance":
            self._publish_head(source)

    def _publish_mast(self, mast):
        for sys_name in _head_names_on_mast(mast):
            if sys_name not in self.wanted:
                continue
            head = _head_manager().getSignalHead(sys_name)
            if head is not None:
                self._publish_head(head)

    def _publish_head(self, head):
        if self.mqtt is None or head is None:
            return
        sys_name = head.getSystemName()
        if sys_name not in self.wanted:
            return
        topic = self.topic_prefix + sys_name
        data = head.getAppearanceName()
        try:
            self.mqtt.publish(topic, data)
        except Exception as exc:
            print(
                "mqtt_signalhead: publish failed %s %s: %s"
                % (_ascii(topic), _ascii(data), _ascii(exc))
            )


publisher = HartMqttSignalPublisher(TOPIC_PREFIX, HEAD_NAMES)
publisher.start()
