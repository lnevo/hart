# ADR-030 — The level is a column

- **Status:** Accepted
- **Date:** 2026-11-21
- **Deciders:** lnevo
- **Builds on:** ADR-021 (switch facts in data), ADR-024 (signals by rule), ADR-027 (staging from its device map), ADR-029 (one device master)

## Context

After level unification, several layout facts were still kept in a file per level, read by a script per level. Staging's switch facts were in `switches.csv` and `switch_legs.csv`, and the main and upper hands were in `hands.csv` and `local_switches_main_upper.csv`. The masts were in `staging_masts.csv` and `main_upper_masts.csv`, which have the same columns. Block exceptions and the owner's block splits were two files with the same key, and the helix had a file of its own. `devices.csv` still carried a copy of the retired name map in six `pnm_*` columns, and code still read a device's kind from its name.

## Decision

**A fact lives in one file for every level.** Staging, main and upper differ only in a row's `level` and its column values. There is no file, script or check per level. (Owner, 2026-11-21.)

- **Switches:** one `switches.csv`. Each row is one OS block (a crossover has a row per half), and `hand_source` says whether the hand comes from the plan or the owner (#843).
- **Block overrides:** one `block_overrides.csv` with a `kind` column. It holds the owner's splits and the wiring exceptions (#842).
- **Masts:** one `masts.csv`, with one builder and one sync check (Stage 2).
- **The helix** is treated like other blocks (#842):
  - Its two pieces, one per exported graph, are one block across the level cut.
  - Its name comes from its plan name: Helix Outer and Helix Inner.
  - The labels McKees Rocks and McKeesport are a `track_labels` preference that every output reads (schematic-maps 0.1.50). They are temporary until the layout expands.
- **One copy of each device fact:** the `pnm_*` columns are gone. A line block's `cp` lists every station or control point at its two ends, separated by ";", own level first, plus any station whose `tracks` names it. Nested stations are both listed. A block's sensor takes its block's `cp` (#844).
- **Kinds from columns:** readers take a device's kind, level and role from its `devices.csv` row (`layer`, `level`, `role`), never from its name. Jython running inside JMRI is the exception, since it cannot import `hartlib` (row 8, owner 2026-11-21; this reverses level unification step 9).

**What stays per sheet:** the JSON layer files (`plan_overrides.json`, `preferences.json` and `signals.json`) keep their `staging` and `main_upper` sections. These follow the plugin's two drawing sheets and the plan's two exported graphs, not a level rule (owner, 2026-11-21).

## Consequences

- A new level, or a level with real devices, adds rows and changes nothing else.
- Writers and checks no longer branch on level beyond the values a row carries.
- Each step is a pure refactor: `tables.xml`, the desks, the Layout Editor panel, the drawings and the approved fingerprints are byte-identical. The exceptions are generated keys and notes, each listed in its PR.
