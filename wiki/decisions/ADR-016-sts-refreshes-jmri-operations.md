# ADR-016 — STS refreshes JMRI Operations

- **Status:** Accepted. Builds on ADR-015.
- **Date:** 2026-11-03
- **Deciders:** lnevo

## Context

Sessions run on STS. JMRI Operations Pro holds the same cars (ADR-013, ADR-015), but nothing kept its car positions, loads and final destinations in step with STS, so the roster, manifests and CATS fell behind after every session. Moving STS onto Aaron's v2 was ruled out on 2026-11-03.

## Decision

1. STS is the master of where each car is, what it carries and where it is going. JMRI Operations Pro is a copy that STS refreshes.
2. The refresh is one way, from STS to JMRI. It is the `jmri_ops` plugin in `external/sts-plugins` (a workflow step and an Operations page button), and `jmri/layouts/hart/scripts/sts_car_sync.py`, which runs in JMRI's Start Up on the Pi and the Mac.
3. The JMRI train builder is not used during an STS session. A car on a built JMRI train is left alone.
4. The plugins carry nothing HART-specific. The JMRI address and the STS-to-JMRI names are settings, edited on the plugin's Settings page and saved in the STS config volume. HART's copy is kept in `jmri/layouts/hart/data/sts_jmri_ops_settings.json`, taken from the 2026-11-02 Operations Pro build. The same holds for the track scale and Coke Orders plugins: their HART values are a preset in `hart_layout`, and `tests/check_generic_plugins.sh` in sts-plugins fails on a HART name anywhere else.

## Consequences

- JMRI saves Operations after a refresh, so the Pi's files carry STS state. `make ops-pull` before the next deploy keeps it (ADR-015).
- Cars STS does not hold (the 28 with no photo, HART 1776) and `Unavailable` cars are not touched.
- The refresh copies STS as it is, including data slips the Operations Pro build had corrected by hand (two coke hoppers at Aristech Chemical Unload, NW 12986 at Shenango). The preview names every car placed on a track JMRI would refuse.
- Nothing flows from JMRI back to STS.
