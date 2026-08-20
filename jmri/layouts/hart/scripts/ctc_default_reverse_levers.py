# Set CTC switch levers to Reverse for turnouts that rest Thrown.
# CTC itself initializes UNKNOWN levers to Normal (ACTIVE). Run this
# after "Run CTC Logic" and it also re-applies after Reload CTC.
#
# Levers: IS3=SW100, IS23=SW112, IS27=SW114, IS29=SW115
# ACTIVE = Normal, INACTIVE = Reverse.

import jmri
from java.beans import PropertyChangeListener

LEVERS = ("IS3:LEVER", "IS23:LEVER", "IS27:LEVER", "IS29:LEVER")


def set_reverse(reason=""):
    for name in LEVERS:
        s = sensors.getSensor(name)
        if s is not None:
            s.setKnownState(INACTIVE)
    print("CTC reverse-default levers%s: 100, 112, 114, 115 -> Reverse" %
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
