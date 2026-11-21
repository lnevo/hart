# ADR-027 — Staging is built from its device map

- **Status:** Accepted
- **Date:** 2026-11-17 (recorded 2026-11-19)
- **Deciders:** lnevo
- **Amended by:** ADR-029. `device_map_staging.csv` was retired (R9e); its rows are the level 1 rows of `devices.csv`.

## Context

The main and upper levels were built from a device map from the start. Staging's part of the Layout Editor panel was hand-drawn, and the builds read frozen copies of that drawing (`staging_le/`) through a conversion and an overlay. Two levels of one panel had two kinds of source.

## Decision

Every level of the "HART Railroad" panel is built from its device map (owner, 2026-11-17, [`STATUS.md`](../STATUS.md), "Staging from its device map"). The hand-drawn inputs, the conversion and the overlay are retired.

**Staging's files**, in `jmri/layouts/hart/data/schematic/`:
- `device_map_staging.csv`, in the columns of the main and upper map: turnouts, feedback, blocks, occupancy, masts and heads.
- `stations.csv`: the stations; the stations that share a `desk_code` are a desk area, staging's control points (since 2026-11-20; `control_points_staging.csv` is gone).
- `masts.csv` (every level, with a `level` column): the masts and their signal-plan facts.
- `panel_items.json`: the panel's own items.

**Field devices**
- Staging is in the field. Its turnouts, feedback sensors and detectors carry the railroad's own system names, and the map records them as they are in `tables.xml`.
- `check_device_master.py --check` (`staging_device_map.py --check` until 2026-11-20, when it took every level) holds the files to their rules and to `tables.xml`. `make panels` and `tools/check.sh` run it.

**Signals**
- The visible masts are placed by the rule in [ADR-024](ADR-024-signals-by-rule.md). That ADR records the interlockings, the mast types, the milepost origin and the line codes, and they are not repeated here. `build_masts.py` writes the masts into the files above.
- The heads are internal (`IH:HART:C1:`). The one wired head is IH432 on Mast 6LB, kept as a head row in the device map.
- The hidden routing masts are placed by rule as well (ADR-024, owner 2026-11-20); none is hand-kept since the helix-foot masts 38RA and 40RA went with the one-block helix tracks, and `staging_masts_virtual.csv` and `staging_signals_virtual.csv` are gone.

## Consequences

- A staging change is an edit to these files followed by `make panels`. A PanelPro Store still owns `tables.xml` (ADR-008).
- A changed mast set also needs `sync_signals.py`, stock discovery in a sandbox and the owner's approval (ADR-024).
- A wired staging head goes in as a head row whose `jmri_name` is the wired head, as main and upper swap a device in (ADR-028).

