# ADR-029 — `tables.xml` is an output of one device master and a template

- **Status:** Accepted
- **Date:** 2026-11-20
- **Deciders:** lnevo
- **Builds on:** ADR-008 (one tables file), ADR-014 (hosts load `preference:tables.xml`), ADR-027 (staging from its device map), ADR-028 (main and upper on virtual devices)

## Context

Device facts are kept three times: `public_name_map.csv`, `device_map_staging.csv` and `device_map_main_upper.csv` each hold parts of them, and `tables.xml` holds them again. The DCC group is parsed from JMRI comments, and the build finds its own items by comment and name. Staging has no generator: `build_layout_le.py` builds on the live `tables.xml`, so for staging `tables.xml` is still a source. The inventory and design are in the project-health hand-off, row 9 ([`projects/project-health-handoff.md`](../projects/project-health-handoff.md)).

## Decision

**`tables.xml` is an output.** It is the file PanelPro and CATS load. Nothing reads it as a source. A pulled Store is the one exception: it is split back into the sources. (Owner, 2026-11-20.)

**The device master**
- `jmri/layouts/hart/data/devices.csv` holds every device on all three levels in one structure. Staging, main and upper differ only by column values.
- `devices.columns.csv` describes every column. A test checks it against the header.
- Every row has a `description`.
- `assignment` says how the device is in JMRI now: `field`, `virtual` (ADR-028), `none` (no bean yet) or `spare`. Swapping a physical device in for a virtual one edits that row only.
- `role` says what the device is (W6 row 8). Readers test `role`, never a name prefix.
- `written_by` names the script that owns the row, or is empty for a hand-kept row. The allowed values are one constant, so merging builders changes one place. Each script rewrites only its own rows.
- The DCC address is a column. Nothing parses it from a comment.
- JMRI comments are generated from the wiring columns, as they were first derived from the wiring documents. They are not stored as free text.
- The pre-ADR-005 alias names are dropped. Retired identity names are dropped. The two spare detectors stay as `spare` rows.

**The template**
- What PanelPro owns and the build does not generate (memories, the "Hide windows on start" LogixNG, clock and turnout-manager settings, `blockrouting`) is kept in one JMRI-format template file.
- Discovered Signal Mast Logic is its own file, written only by the discovery wrapper.
- What JMRI writes on every Store (the header comment, `jmriversion`, `filehistory`, the clock time, memory values) is a fixed envelope in the build and is dropped on a pull. The old file history is lost once.
- The saved block paths on the staging blocks are dropped once a sandbox PanelPro load shows JMRI rebuilds them from the panel.
- The deploy-time rewrite of `tables.xml` (`disable_digicon_sml_in_tables.py`) moves into the generator, so the hosts get exactly the committed bytes.

**Pulls**
- `make tables-pull` and `make tables-pull-pi` compare the Store with the generated file and send each change to its source. A rename made in PanelPro on a hand-kept row updates `devices.csv`. A change to a script-owned row fails the pull and names the script to change.
- Anything the pull cannot place fails the pull, naming each element. Nothing is guessed.

**Cut-over gate**
- The first generated `tables.xml` matches the committed one byte for byte after a defined normalisation. A sandbox PanelPro load and Store returns the same bytes. Every remaining difference is listed and explained before the switch.

The `AGENTS.md` rule "fix the data in `tables.xml`" becomes "fix the source data or the template".

## Consequences

- One place to change a device, for every level.
- `public_name_map.csv` and the two device maps are generated from the master during the change-over, then retired (R9e).
- An old Store or document that uses pre-ADR-005 names can no longer be converted automatically.
- Builders that write device rows must name themselves in `written_by`.

## Open

- R9b to R9e are built in that order ([`projects/project-health-handoff.md`](../projects/project-health-handoff.md)). The level-unification mast builder (step 2) waits on R9b.
