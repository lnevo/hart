# JMRI jython — optional UNKNOWN→THROWN for a few plants (not used at CATS boot).
#
# Prefer apply_mqtt_retain_at_startup.py: one-shot MQTT retain → JMRI KnownState.
# Keep this for manual Script Entry if a turnout is UNKNOWN with no retain.

DEFAULT_THROWN = (
    "M2T408",   # Switch 100
    "M2T1213",  # Switch 112
    "M2T109",   # Switch 114
    "M2T110",   # Switch 115
)

for name in DEFAULT_THROWN:
    t = turnouts.getTurnout(name)
    if t is None:
        print("default_thrown_if_unknown: missing " + name)
        continue
    if t.getKnownState() == Turnout.UNKNOWN:
        t.setCommandedState(Turnout.THROWN)
        print("default_thrown_if_unknown: " + name + " UNKNOWN → THROWN")
    else:
        print(
            "default_thrown_if_unknown: "
            + name
            + " keep "
            + t.describeState(t.getKnownState())
        )
