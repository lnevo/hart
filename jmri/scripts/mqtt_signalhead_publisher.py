# Publish Virtual Signal Head appearances to MQTT (JMRI → broker).
# HART POC: Plane East East Main Ext (SW102 normal route, lower track).
#
# LCOS packed address = displayNode*100 + UID
#   (mqtt_serial.h / LCOS Public API UID Map: Signal 0..15 = UID 32..47)
# JMRI VirtualSignalHead systemName is IH<packed>; MQTT topic keeps that name.
# LCOS consumers may strip the "signalhead/" prefix and optional "IH" → ###.
#
# Heads (after mast 464):
#   IH465 = top head  → track/signalhead/IH465
#   IH466 = bottom    → track/signalhead/IH466
# Mast userName: Plane East East Main Ext
#   IF$shsm:cats-masts:cats-virtual-2(IH465)(IH466)
# Payload: appearance name GREEN / YELLOW / RED / DARK / FLASHRED / …
#
# Pair with MQTT Signal Mast 464 (Brick East Main West) for dual-path POC.
# Load after tables (Scripting → Run Script, or profile Start Up).

import jmri
import java

class HartMqttSignalHeadPublisher(java.beans.PropertyChangeListener):
    def __init__(self, topic_prefix, head_names):
        self.topic_prefix = topic_prefix
        self.head_names = list(head_names)
        self.mqtt = None

    def start(self):
        memo = jmri.InstanceManager.getDefault(jmri.jmrix.mqtt.MqttSystemConnectionMemo)
        self.mqtt = memo.getMqttAdapter()
        for name in self.head_names:
            head = signals.getSignalHead(name)
            if head is None:
                print("HartMqttSignalHeadPublisher: missing head", name)
                continue
            head.addPropertyChangeListener(self)
            # publish current state once
            self._publish(head)
            print("HartMqttSignalHeadPublisher: listening", name)
        return

    def propertyChange(self, event):
        if event.propertyName == "Appearance":
            self._publish(event.source)
        return

    def _publish(self, head):
        topic = self.topic_prefix + head.getSystemName()
        data = head.getAppearanceName()
        print("HartMqttSignalHeadPublisher:", topic, data)
        self.mqtt.publish(topic, data)
        return

publisher = HartMqttSignalHeadPublisher(
    "track/signalhead/",
    ["IH465", "IH466"],
)
publisher.start()
