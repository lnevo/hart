# Set CTC switch levers to Reverse for turnouts that rest Thrown,
# and default the West Yard / East End ladder lock toggles to Local.
# CTC itself initializes UNKNOWN levers to Normal (ACTIVE) and lock
# toggles to Locked (INACTIVE). Run this after "Run CTC Logic"; it
# also re-applies after Reload CTC.
#
# Levers: IS3=Switch 1, IS23=Switch 33, IS27=Switch 37, IS29=Switch 39
#   ACTIVE = Normal, INACTIVE = Reverse.
# Lock toggles: yard ladders default Local (ACTIVE = Local, INACTIVE = Locked).

import jmri
from java.beans import PropertyChangeListener

LEVERS = ("IS3:LEVER", "IS23:LEVER", "IS27:LEVER", "IS29:LEVER")
LOCAL_LOCKS = (
    "IS10:LOCKTOGGLE",  # Switch 13
    "IS12:LOCKTOGGLE",  # Switch 15
    "IS22:LOCKTOGGLE",  # Switch 31
    "IS32:LOCKTOGGLE",  # Switch 9
    "IS34:LOCKTOGGLE",  # Switch 11
    "IS36:LOCKTOGGLE",  # Switch 17
    "IS38:LOCKTOGGLE",  # Switch 19
    "IS40:LOCKTOGGLE",  # Switch 21
    "IS14:LOCKTOGGLE",  # Switch 25
    "IS16:LOCKTOGGLE",  # Switch 27
    "IS20:LOCKTOGGLE",  # Switch 29
)


def set_reverse(reason=""):
    for name in LEVERS:
        s = sensors.getSensor(name)
        if s is not None:
            s.setKnownState(INACTIVE)
    for name in LOCAL_LOCKS:
        s = sensors.getSensor(name)
        if s is not None:
            s.setKnownState(ACTIVE)
    print("CTC defaults%s: 1/33/37/39 Reverse; yard ladders Local" %
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
