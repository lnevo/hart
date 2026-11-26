# JMRI jython -- part of signal_coordinator.py: its constants, bean and name helpers, and
# the Digicon bean roster (SignalMasts with LCOS heads, their SignalMastLogics).
#
# signal_coordinator.py loads this from preference:jython and reloads it on every run
# (jython_siblings.py). JMRI binds `masts`, `signals` and the other manager names in the
# script's globals only, so the manager helpers here use InstanceManager, which holds the
# same defaults.

import jmri
import re

TOPIC_PREFIX = "track/signalhead/"
MAST_TOPIC_PREFIX = "track/signalmast/"
SML_MODE_TOPIC = "track/bridge/sml_mode"
# Coordinators only (the bridge never subscribes): who claims, and when.
SML_CLAIM_TOPIC = "track/bridge/sml_claim"
SML_MODE_SENSOR = "IS:SML_MODE"
HOLD_WAIT_MS = 3000
BOOT_MODE_WAIT_MS = 1000
# After enabling, originator waits then Holds and announces sml_mode enabled.
SML_ABORT_RESUME_MS = 1000
# Operator Enable probe: wait for another instance to ACK enabled.
PROBE_WAIT_MS = 1000
# Only abort mutes bean MQTT: dests uncheck without Hold/Red/Unheld because
# another agent owns Digicon. Operator Enable/Disable Hold wait publishes.

# LCOS signal UIDs: UID_OFFSET_SIGNALS .. UID_OFFSET_CROSSINGS-1 (lcos.h).
_LCOS_SIGNAL_UID_MIN = 32
_LCOS_SIGNAL_UID_MAX = 47

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


def _packed_is_lcos_signal(packed):
    """True if packed = display_node*100 + signal UID (32-47) and node is octal-legal."""
    if packed is None:
        return False
    s = str(packed).strip()
    if not s.isdigit():
        return False
    n = int(s)
    node = n // 100
    uid = n % 100
    if uid < _LCOS_SIGNAL_UID_MIN or uid > _LCOS_SIGNAL_UID_MAX:
        return False
    try:
        int(str(node), 8)
    except Exception:
        return False
    return True


def _is_lcos_ih_sys(sys_name):
    """True if system name is IH<packed> for an LCOS signal UID."""
    if sys_name is None:
        return False
    name = str(sys_name)
    if len(name) <= 2 or name[:2].upper() != "IH":
        return False
    return _packed_is_lcos_signal(name[2:])


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
    # JMRI's names are the standard ("Flashing Red"); the LCOS firmware's tokens
    # ("FlashRed") are accepted too.
    upper = key.upper().replace(" ", "").replace("FLASHING", "FLASH")
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


def _dest_listed(sml, dest):
    """True if dest is still one of the logic's destinations."""
    try:
        it = sml.getDestinationList().iterator()
        while it.hasNext():
            if it.next() == dest:
                return True
    except Exception:
        return True  # cannot tell: count it as a failure
    return False


def _bean_label(bean):
    """UserName, else system name, else text: for failure lines."""
    for getter in ("getUserName", "getSystemName"):
        try:
            name = getattr(bean, getter)()
            if name:
                return _ascii(name)
        except Exception:
            pass
    return _ascii(bean)


class SmlBeans(object):
    """DigiconMqttSml's bean roster: the Digicon masts, their heads and SML sources."""

    def _snapshot_mast_sml_state(self):
        """Baseline dest Enabled maps. Bulk/boot must not Unheld from the listener.

        Per-mast field ownership is dest checkboxes only. Global Disable is
        `_global_enabled` in `_field_owns_mast` -- do not fold it in here, or
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

    def _collect_beans(self):
        """Digicon plants = SHSM masts with LCOS Virtual IH heads (tables, not a static list).

        MQTT SET/Unheld heads attach later via _enroll_packed from signalmast.
        """
        mm = _mast_manager()
        self._masts = []
        self._heads = []
        self._head_to_mast = {}
        if mm is None:
            return
        for mast in mm.getNamedBeanSet():
            lcos_heads = [n for n in _head_names_on_mast(mast) if _is_lcos_ih_sys(n)]
            if not lcos_heads:
                continue
            self._masts.append(mast)
            for n in lcos_heads:
                self._head_to_mast[n] = mast

    def _attach_bean_listeners(self):
        for mast in self._masts:
            mast.addPropertyChangeListener(self)
        for head in self._heads:
            head.addPropertyChangeListener(self)

    def _attach_sml_listeners(self, quiet=False):
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
        n = len(self._smls)
        # Refresh before bulk set is normal; only log when the count changes.
        if quiet and n == getattr(self, "_sml_watch_logged", None):
            return
        print(
            "mqtt_signalhead: watching %d Digicon SignalMastLogic sources"
            % n
        )
        self._sml_watch_logged = n
