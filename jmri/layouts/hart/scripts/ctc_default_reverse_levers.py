# Set CTC switch levers to Reverse for turnouts that rest Thrown,
# and default the West Yard / East End ladder lock toggles to Local.
# CTC itself initializes UNKNOWN levers to Normal (ACTIVE) and lock
# toggles to Locked (INACTIVE). Run this after "Run CTC Logic"; it
# also re-applies after Reload CTC.
#
# Levers: IS3=SW100, IS23=SW112, IS27=SW114, IS29=SW115
#   ACTIVE = Normal, INACTIVE = Reverse.
# Lock toggles: IS10=SW116, IS12=SW103, IS22=SW110
#   ACTIVE = Local, INACTIVE = Locked.

import jmri
from java.beans import PropertyChangeListener

LEVERS = ("IS3:LEVER", "IS23:LEVER", "IS27:LEVER", "IS29:LEVER")
LOCAL_LOCKS = ("IS10:LOCKTOGGLE", "IS12:LOCKTOGGLE", "IS22:LOCKTOGGLE")


def set_reverse(reason=""):
    for name in LEVERS:
        s = sensors.getSensor(name)
        if s is not None:
            s.setKnownState(INACTIVE)
    for name in LOCAL_LOCKS:
        s = sensors.getSensor(name)
        if s is not None:
            s.setKnownState(ACTIVE)
    print("CTC defaults%s: 100/112/114/115 Reverse; 116/103/110 Local" %
          ((" (%s)" % reason) if reason else ""))


class _OnReload(PropertyChangeListener):
    def propertyChange(self, event):
        if event.propertyName == "KnownState" and event.newValue == ACTIVE:
            jmri.util.ThreadingUtil.runOnGUIDelayed(
                lambda: set_reverse("reload"), 400)


set_reverse("startup")
jmri.util.ThreadingUtil.runOnGUIDelayed(lambda: set_reverse("delayed"), 2500)

_reload = sensors.getSensor("IS:RELOADCTC")
if _reload is not None:
    _reload.addPropertyChangeListener(_OnReload())
