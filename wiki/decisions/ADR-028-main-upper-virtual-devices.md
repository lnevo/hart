# ADR-028 — Main and upper levels run on virtual devices named by identity

- **Status:** Accepted
- **Date:** 2026-11-17 (recorded 2026-11-19)
- **Deciders:** lnevo
- **Amended by:** ADR-029. `device_map_main_upper.csv` was retired (R9e); its rows are the level 2 and 3 rows of the device master (`devices_field.csv` and `devices_generated.csv`, read through `hartlib.devices`; ADR-029 amendment of 2026-11-21).

## Context

The main and upper levels are in JMRI and on the CATS desks before their plant is wired. The planned LCOS nodes, ports and detector addresses are a draft that the owner has not reviewed. A JMRI name taken from a draft address, or from the order things were drawn in, would change when the plant is reviewed, and so would every panel, desk and Signal Mast Logic that names it.

## Decision

Every main and upper turnout, block sensor, signal head and mast in JMRI is an internal device named from what it is (owner, 2026-11-17, [status entry](../status/current/main-and-upper-devices-are-virtual.md), "Main and upper devices are virtual").

**Names**
- Turnout: `IT:HART:C3:<switch number>`.
- Block sensor: `IS:HART:C3:B:<block>`, one for every block.
- Signal head: `IH:HART:C3:<mast and head>`.
- Masts are stock signal-head masts (`IF$shsm:basic:…`) on those heads.

**The device map**
- `jmri/layouts/hart/data/schematic/device_map_main_upper.csv` (since R9e, the level 2 and 3 rows of the device master) is the one mapping from each device to its planned physical part. `tools/schematic/build_device_map.py` writes it from the control points, the local switch list and the LCOS node list.
- Per row, `jmri_name` is the virtual device that `tables.xml` and the CATS desks use now. `system_name` is the planned physical device, a draft.
- A physical device is swapped in through the map's `jmri_name` column alone.

**While virtual**
- The heads are internal, so nothing unwired reaches MQTT (ADR-024).
- The block sensors are set clear by a LogixNG when the tables load.
- The same LogixNG sets every virtual turnout to its startup position: Closed, except where the main route runs through the diverging leg (owner, 2026-11-19).

## Consequences

- JMRI names do not change when the draft plant changes. Only the `system_name` column does.
- The planned devices in the map are not a record of what is built. A detector or head with no place on the draft plant carries a "not wired yet" or "not on a node yet" note.
- Staging differs: its devices are in the field and keep their own names (ADR-027).

## Open

- The physical plant for both levels is not reviewed, and no device has been swapped in.
- The user names and control point names are placeholders until the owner names the levels.
- Occupancy detection for these levels (35 detectors, main line only, in `STATUS.md`) is not installed.

**Amended by ADR-033, naming-layers step 7 (2026-11-25):** a main or upper device takes the owner's name from its field row, as staging's do; its virtual JMRI name stays the generated one (`hartlib.level_devices`), the device's identity.

**Amended by ADR-033, naming-layers step 11 (2026-11-25):** every main and upper bean is made from its row by `hartlib.tables_build.master_beans`, the same function as staging's, under the row's `jmri_name`; `cats_panel.py` and `le_tables.py` hold no `IT:HART:C3:` pattern, so a swap is the row edit alone. The startup LogixNG that sets the virtual sensors clear and the virtual turnouts to their start comes from each row's `start` (`startup_logixng.start_logixng`). Their comments are in staging's form, ending `internal, not wired` and the planned device, a draft (owner, 2026-11-23).
