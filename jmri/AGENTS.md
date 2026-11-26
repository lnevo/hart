# JMRI in this repo

Rules for work under `jmri/`, on top of the root [`AGENTS.md`](../AGENTS.md).

- New JMRI track: **Mainline → Yes** (`mainline="yes"`). Geometry **1:1**. Hart has no `export_options.json`.
- PanelPro owns `tables.xml`. Never store JMRI tables from a CATS session. A Store made on a host comes back through the [`tables-pull` skill](../.claude/skills/tables-pull/SKILL.md).
- Scripts with the most need of tests start here: `jmri/scripts/signal_coordinator.py` and `jmri/layouts/hart/scripts/panel_status.py`. Jython scripts never import `hartlib`.
- Parked features (Entry/Exit, the Dispatcher System with its occupancy lamps, stations and yard throats, the USS CTC machine) live in `jmri/layouts/hart/parked/`. Do not list or fix them; their rules for the day they return are in [`docs/parked/UNPARK.md`](../docs/parked/UNPARK.md).
- Launch or "fix paint" scripts never command field turnouts or publish `track/cmd`.
