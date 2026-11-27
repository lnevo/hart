# ADR-033: Generated values, then the owner's, then frozen wiring

- **Status:** Accepted (2026-11-24, when the owner started the [hand-off](../projects/naming-layers-handoff.md))
- **Date:** 2026-11-24
- **Deciders:** lnevo
- **Amends:** ADR-027 (staging from its device map), ADR-028 (main and upper virtual devices), ADR-029 amendment (the device master's key)
- **Builds on:** ADR-026 (AnyRail plan 5.3c), ADR-030 (the level is a column)

## Context

Staging was drawn by hand and named over time; main and upper were built later through a generator. The code still carries that history:

- **Staging is "the field".** `FIELD_LEVEL = "1"` in `hartlib.devices`. The generator finds staging's blocks from the plan through the same block process as main and upper (`block_layer`), but stops on any staging device that has no owner row in `devices_field.csv`. Staging's turnouts, aliases and feedback come from the owner's rows and `wiring.csv`, not from the generator. About 17 scripts under `tools/schematic/` and `tools/hartlib/` test the level to tell the two apart.
- **The name is the identity.** Both device files key a row on `(level, layer, user_name)`. A name change, from a new AnyRail file or a new naming rule, makes a different device, and the owner's cells for the old name stop the build.
- **The owner's values sit in several files.** Device cells in `devices_field.csv` (staging only); staging's track names and bumpers in `plan_overrides.json` (the `name` and `end` edits); switch numbers in the `relabel` edits; splits in `block_overrides.csv`; hands in `switches.csv` (`hand_source owner`).
- **A physical swap is not a data change.** `cats_panel.py` and `le_tables.py` build main and upper beans as virtual names (`IT:HART:C3:<n>`), so a physical `jmri_name` stops `make panels`. That tied the cleanup to the wiring work.

The wiring side already works as intended: `make wiring-freeze` writes `wiring.csv`, the generator keeps its pins, and `check_wiring_frozen.py` fails on any other change.

## Decision

Every device on every level gets its values from three layers, always in this order (owner, 2026-11-24):

| Layer | What it holds | Where |
|---|---|---|
| 1. Generated | Every device the plan has, with a generated name, label, virtual JMRI name and proposed wiring | `devices_generated.csv`, written by the builders from the AnyRail plan and the naming rules |
| 2. Owner | Any value the owner has set: user name, track and bumper name, label, comment, system name, DCC address | The owner files behind `hartlib`'s name store (`devices_field.csv` and the files keyed by ID) |
| 3. Frozen wiring | Node and pin of a wired device | `wiring.csv`, written only by `make wiring-freeze` |

- **An owner value always wins.** A non-empty owner cell replaces the generated one. A regenerate never changes it. No level is special: staging is a level where the owner has named everything, main and upper are levels where the owner has named little yet.
- **Nothing is named before the owner is ready** (owner, 2026-11-24). A value the owner has not set stays generated or blank. The control points in `interlockings.csv` are owner values.
- **A device has an ID that is not its name** (owner, 2026-11-24: keep it simple). The generator derives it from the plan: a switch by its number and half, a block by the objects at its ends, a detector by its block, a mast by the switch, leg and direction it protects. Every file that holds rows about a device keys them on the ID. The user name is an ordinary column.
- **One name store, and every read through `hartlib`** (owner, 2026-11-24). `hartlib` gives every device's name: generated, then the owner's, then the display label. The Layout Editor panel, the CATS desks, the schematic and `tables.xml` take names only from it. The schematic plugin gets them in the folder `hartlib` writes for it (`layer_files.view`), so it draws the owner's name if one is defined and the generated one otherwise. `plan_overrides.json` keeps the switch numbers and drawing settings, and holds no names. No script outside `hartlib` opens a layout data file; Jython inside JMRI reads only generated outputs.
- **Signals are devices like any other.** Masts and heads follow the same layers. JMRI keys Signal Mast Logic by mast user name and stays stock, so a mast rename needs a new SML discovery and the owner's panel approval; the build warns before it.
- **Copies in other systems are listed, not rewritten.** Operations Pro and STS keep their own names; a rename lists the copies in the repo's Operations Pro files.
- **Renames and re-imports.** A new naming rule changes generated names only; owner names stay. A new AnyRail file is matched by ID, and the build lists the IDs that are new and those that are gone. A gone ID that still has owner values stops the build and is listed until the owner moves or drops them (owner, 2026-11-24); it is never renamed silently.
- **Frozen wiring is fixed, labels are not.** Once a control point is frozen, the generator stops proposing its pins. Its names, labels and comments are still the owner's layer and can change at any time.
- **A physical swap is one owner edit.** The owner sets the device's `system_name` (and so `jmri_name`) in its owner row. The ID and user name stay the same, so the panels, desks and SML follow it. No reader builds a JMRI name from a pattern.

## Consequences

- One flow for every level. `FIELD_LEVEL` and the level tests go; the parked [builder merge](../../archive/history/wiki/projects/builder-merge.md) (one bean, row and mast process) becomes part of this work instead of waiting for main and upper wiring.
- Staging's current names, comments and system names become owner values on generated rows, and its track names leave `plan_overrides.json`. `tables.xml`, the desks and the panels do not change.
- The first main or upper swap no longer needs a code change.
- A device the plan no longer has cannot keep its owner values by accident.
- Each step is a refactor with byte-identical layout outputs, except where its PR lists a diff (the bean comments the owner already chose to unify on 2026-11-23).
