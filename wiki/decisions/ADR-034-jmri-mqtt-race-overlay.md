# ADR-034: JMRI's MQTT race fix as an overlay until JMRI ships it

- **Status:** Accepted (2026-11-24)
- **Date:** 2026-11-24
- **Deciders:** lnevo
- **Amends:** AGENTS.md "Do not patch or wrap JMRI or CATS" (one exception, below); the 2026-10-31 removal of `hart-startup-guard.jar`

## Context

At PanelPro start, JMRI 5.16's `MqttAdapter` can drop the broker connection while `tables.xml` loads, then reconnect about 15 seconds later. It is a stock JMRI bug, shown on bare profiles and fixed upstream in [JMRI/JMRI#16004](https://github.com/JMRI/JMRI/pull/16004), opened 2026-11-23 for the 5.19 series ([`MQTT_STARTUP_RACE.md`](../../docs/jmri/MQTT_STARTUP_RACE.md)). The hosts stay on 5.16 until CATS supports a newer JMRI, so the upstream fix does not reach them for some time.

The old overlay (`hart-startup-guard.jar`, removed 2026-10-31) patched JMRI and CATS classes with javassist, swallowed exceptions and changed which MQTT topics JMRI published.

## Decision

With the pull request submitted, the owner asked for the overlay back for the MQTT race only, not for CATS (2026-11-24):

- `tools/jmri/mqtt_overlay/hart-mqtt-race-fix.jar` holds one class, `jmri.jmrix.mqtt.MqttAdapter`: JMRI 5.16's source with the #16004 hunks and nothing else (not the 5.19 UTF-8 change). `build.sh` compiles it against the stock 5.16 jars; `build.sh --check` shows that the committed jar matches the source.
- Each host loads it through the user's `jmri.conf` (`default_options="--cp:p=<settings dir>/hart-mqtt-race-fix.jar ..."`), so it applies to every JMRI app that user starts, including CATS, which uses JMRI's MQTT connection. JMRI's install folder is not touched, and other options in `jmri.conf` are kept.
- `install_overlay.py` runs in every deploy (Mac, Pi, Windows). It installs only over JMRI 5.16.0, revision `909e15189e`. On any other build it takes the overlay out of `jmri.conf` and prints a warning, so a JMRI upgrade runs stock.
- No CATS class, no swallowed exceptions, no topic filtering.

## Consequences

- The exception in AGENTS.md covers this one class until the hosts run a JMRI release that carries #16004: the 5.20 production release, not the 5.19.2 test release (owner, 2026-11-27). Then remove `tools/jmri/mqtt_overlay/` and the deploy lines that call it (the version check has already taken it out of `jmri.conf` by then).
- A change asked for in #16004 is copied into `MqttAdapter.java` and the jar rebuilt, so the hosts run what JMRI reviews.
- `install_overlay.py --remove --settings-dir <dir>` takes it off one host by hand.
