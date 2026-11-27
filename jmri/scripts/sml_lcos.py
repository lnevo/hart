# JMRI jython -- part of signal_coordinator.py: which signal head system names are LCOS heads, the
# rule _collect_beans enrols the Digicon masts by.
#
# signal_coordinator.py loads this from preference:jython first of its modules and reloads it on
# every run (jython_siblings.py); sml_beans.py imports these names from it. The Layout Editor build
# imports the same file in CPython (tools/schematic/le_names.py, through hartlib.coordinator), so it
# imports nothing but re: no jmri, no java, no hartlib.
#
# Jython 2.7: no f-strings or annotations.

import re

# LCOS signal UIDs: UID_OFFSET_SIGNALS .. UID_OFFSET_CROSSINGS-1 (lcos.h).
_LCOS_SIGNAL_UID_MIN = 32
_LCOS_SIGNAL_UID_MAX = 47

_HEAD_IN_MAST = re.compile(r"\(IH\d+\)")


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
    except ValueError:
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
