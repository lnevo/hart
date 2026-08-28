# JMRI jython — Digicon MQTT <-> SML hand-off (publisher + receiver + global toggle).
#
# Name kept as mqtt_signalhead_publisher.py for existing profile Start Up entries.
#
# Global toggle: SML Enabled / SML Disabled (main window button).
#   Enabled  -> publish appearances on track/signalhead/<packed> (SET)
#   Disabled -> apply track/signalmast/<packed> to IH heads; no SET
# Per-mast SML off -> immediate Unheld for that mast's heads + mast->IH
# track/bridge/sml_mode: enabled|disabled|query (reply enabled when global Enabled)
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
        self.mqtt = None
        self._masts = []
        self._heads = []
        self._smls = []
        self._head_to_mast = {}
        self._global_enabled = False
        self._busy = False
        self._suppress_sml = False
        self._retained_mode = None
        self._mode_seen = False
        self._button = None

    def start(self):
        self.mqtt = _mqtt_adapter()
        if self.mqtt is None:
            print("mqtt_signalhead: no JMRI MQTT connection; not starting")
            return
        self._collect_beans()
        self._attach_bean_listeners()
        self._attach_sml_listeners()
        self._subscribe_mqtt()
        self._add_toggle_button()
        # Boot: Disabled in JMRI (no Unheld, no Hold wait), then flip from retain.
        self._boot_disabled_no_release()
        self._schedule_boot_flip()
        print(
            "mqtt_signalhead: Digicon SML MQTT, %d masts, %d heads (packed topics)"
            % (len(self._masts), len(self._heads))
        )

    def _boot_disabled_no_release(self):
        """JMRI/SML/receiver state only — field RELEASE is the bridge's job."""
        self._suppress_sml = True
        try:
            self._set_all_digicon_sml_destinations(False)
            self._global_enabled = False
            self._set_button_label()
        finally:
            self._suppress_sml = False

    def _set_all_digicon_sml_destinations(self, enabled):
        """Flip Enabled checkbox for every Digicon source→dest pair (SML table)."""
        # SML may finish discovering after Start Up — refresh before bulk set.
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

        try:
            from jmri.util import ThreadingUtil

            class _R(Runnable):
                def run(__self):
                    _do()

            if ThreadingUtil.isLayoutThread():
                _do()
            else:
                ThreadingUtil.runOnLayout(_R())
        except Exception:
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
            for name in self.wanted:
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
        print(
            "mqtt_signalhead: watching %d Digicon SignalMastLogic sources"
            % len(self._smls)
        )

    def _subscribe_mqtt(self):
        try:
            self.mqtt.subscribe(SML_MODE_TOPIC, self)
            self.mqtt.subscribe(MAST_TOPIC_PREFIX + "#", self)
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

    def _schedule_boot_flip(self):
        controller = self

        class _Boot(Runnable):
            def run(_self):
                # Wait briefly for retained sml_mode delivery.
                Thread.sleep(1500)
                mode = controller._retained_mode
                if mode is None or str(mode).strip().lower() in ("", "enabled", "query"):
                    controller._enter_enabled(force=True, from_boot=True)
                else:
                    controller._publish_mode("disabled")
                    controller._set_button_label()
                    print("mqtt_signalhead: boot stay SML Disabled (retain disabled)")

        Thread(_Boot(), "digicon-sml-boot").start()

    def _on_toggle(self):
        if self._busy:
            return
        if self._global_enabled:
            self._enter_disabled(release=True)
        else:
            self._enter_enabled(force=False, from_boot=False)

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

    def _enter_enabled(self, force, from_boot):
        if self._busy:
            return
        mode = self._retained_mode
        if (
            not force
            and not from_boot
            and mode is not None
            and str(mode).strip().lower() == "enabled"
        ):
            rc = JOptionPane.showConfirmDialog(
                None,
                "track/bridge/sml_mode is already enabled.\nForce override Digicon control?",
                "SML Enabled",
                JOptionPane.YES_NO_OPTION,
                JOptionPane.WARNING_MESSAGE,
            )
            if rc != JOptionPane.YES_OPTION:
                print("mqtt_signalhead: enable aborted (no override)")
                return
        self._busy = True
        if self._button is not None:
            self._button.setEnabled(False)
        controller = self

        class _Run(Runnable):
            def run(_self):
                try:
                    controller._hand_off_enabled()
                finally:
                    controller._busy = False
                    controller._set_button_label()

        Thread(_Run(), "digicon-sml-enable").start()

    def _apply_global_disabled(self, release, publish_mode):
        """Disable Digicon SML in JMRI. RELEASE only when release=True."""
        self._suppress_sml = True
        try:
            for mast in self._masts:
                try:
                    mast.setHeld(True)
                except Exception:
                    pass
            Thread.sleep(HOLD_WAIT_MS)
            self._set_all_digicon_sml_destinations(False)
            if release:
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
        self._suppress_sml = True
        try:
            for mast in self._masts:
                try:
                    mast.setHeld(True)
                except Exception:
                    pass
            Thread.sleep(HOLD_WAIT_MS)
            self._set_all_digicon_sml_destinations(True)
            for mast in self._masts:
                try:
                    mast.setHeld(False)
                except Exception:
                    pass
            self._global_enabled = True
            self._publish_mode("enabled")
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
        for sml in self._smls:
            try:
                if sml.getSourceMast() == mast:
                    return sml
            except Exception:
                continue
        return None

    def _mast_logic_enabled(self, mast):
        """True if Digicon source mast has any destination Enabled in the SML table."""
        if mast is None:
            return False
        sml = self._sml_for_mast(mast)
        if sml is None:
            return False
        try:
            dests = sml.getDestinationList()
            if dests is None or dests.isEmpty():
                return False
            it = dests.iterator()
            while it.hasNext():
                dest = it.next()
                try:
                    if sml.isEnabled(dest):
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def _field_owns_mast(self, mast):
        if not self._global_enabled:
            return True
        return not self._mast_logic_enabled(mast)

    def _publish_unheld(self, head):
        if head is None:
            return
        sys_name = head.getSystemName()
        if sys_name not in self.wanted:
            return
        topic = TOPIC_PREFIX + _topic_suffix(sys_name)
        self._publish(topic, "Unheld", retain=False)

    def _publish_head_set(self, head):
        if self.mqtt is None or head is None:
            return
        if not self._global_enabled:
            return
        mast = self._mast_for_head(head)
        if not self._mast_logic_enabled(mast):
            return
        sys_name = head.getSystemName()
        if sys_name not in self.wanted:
            return
        topic = TOPIC_PREFIX + _topic_suffix(sys_name)
        data = head.getAppearanceName()
        self._publish(topic, data, retain=False)

    def _apply_mast_payload_to_head(self, packed, payload):
        sys_name = "IH" + str(packed)
        if sys_name not in self.wanted:
            return
        mast = self._head_to_mast.get(sys_name)
        if not self._field_owns_mast(mast):
            return
        head = _head_manager().getSignalHead(sys_name)
        if head is None:
            return
        aspect = str(payload).split(";")[0].strip()
        mapped = _ASPECT_TO_APPEARANCE.get(aspect.lower())
        if mapped is None:
            mapped = aspect
        const = _appearance_constant(mapped)
        if const is None:
            return
        try:
            if head.getAppearance() == const:
                return
            head.setAppearance(const)
        except Exception as exc:
            print(
                "mqtt_signalhead: setAppearance %s %s: %s"
                % (_ascii(sys_name), _ascii(mapped), _ascii(exc))
            )

    def notifyMqttMessage(self, topic, message):
        topic = _ascii(topic)
        message = _ascii(message).strip()
        if topic == SML_MODE_TOPIC or topic.endswith("/bridge/sml_mode"):
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
        self._mode_seen = True
        if mode in ("enabled", "disabled", "query"):
            self._retained_mode = mode
        if mode == "query" and self._global_enabled and not self._busy:
            self._publish_mode("enabled")
            print("mqtt_signalhead: ACK query -> enabled")

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
                    if sys_name not in self.wanted:
                        continue
                    head = _head_manager().getSignalHead(sys_name)
                    if head is not None:
                        self._publish_head_set(head)
            return
        if name == "Appearance":
            self._publish_head_set(source)

    def _on_sml_property(self, sml):
        try:
            mast = sml.getSourceMast()
        except Exception:
            return
        if mast not in self._masts:
            return
        enabled = self._mast_logic_enabled(mast)
        if enabled:
            # Re-enabled: resume SET, no Unheld.
            for sys_name in _head_names_on_mast(mast):
                if sys_name not in self.wanted:
                    continue
                head = _head_manager().getSignalHead(sys_name)
                if head is not None:
                    self._publish_head_set(head)
            return
        # Disabled: immediate Unheld for this mast's heads (even under global Enabled).
        for sys_name in _head_names_on_mast(mast):
            if sys_name not in self.wanted:
                continue
            head = _head_manager().getSignalHead(sys_name)
            if head is not None:
                self._publish_unheld(head)
        print(
            "mqtt_signalhead: per-mast SML off -> Unheld %s"
            % _ascii(mast.getDisplayName())
        )


controller = DigiconMqttSml(HEAD_NAMES)
controller.start()
