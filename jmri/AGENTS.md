# JMRI in this repo

Rules for work under `jmri/`, on top of the root [`AGENTS.md`](../AGENTS.md).

- New JMRI track: **Mainline → Yes** (`mainline="yes"`). Geometry **1:1**. Hart has no `export_options.json`.
- PanelPro owns `tables.xml`. Never store JMRI tables from a CATS session. A Store made on a host comes back through the [`tables-pull` skill](../.claude/skills/tables-pull/SKILL.md).
- Scripts with the most need of tests start here: `jmri/scripts/signal_coordinator.py` and `jmri/layouts/hart/scripts/panel_status.py`. Jython scripts never import `hartlib`.
- Parked features (Entry/Exit, the Dispatcher System with its occupancy lamps, stations and yard throats, the USS CTC machine) live in `jmri/layouts/hart/parked/`. Do not list or fix them; their rules for the day they return are in [`docs/parked/UNPARK.md`](../docs/parked/UNPARK.md).
- Launch or "fix paint" scripts never command field turnouts or publish `track/cmd`.
- The LCOS bridge (`serial_to_mqtt`) runs on the Pi as the `lcos-bridge` systemd service (`~/lcos-bridge`, `./bridge start|stop|status|log`). Never leave it stopped or start a second one; a lab test that needs the Nano's port stops it first and starts it again before the turn ends.
- JMRI's own signal mast logic discovery (stock Discover, Stage 1 in a sandbox rehearsal) is the reference. Judge signal logic by what it stores, not by a home-made SML model, and build no SML prediction tool; raise a disagreement only when the owner finds one (owner, 2026-11-16: "I'd prefer to go with SML discovery if that makes things work more correctly, if I find a disagreement later we can discuss it"). The earlier model disagreed with discovery and failed on the hand-drawn tables, so its red results meant nothing.
- Staging-yard masts are all virtual. Gained or lost SML pairs among them need no review: take stock discovery, mention the pair count in one line at most, and ask nothing (owner, 2026-11-17: "these are all virtual masts and in the yard, we're spending a lot of time on that").
- `jmri/layouts/hart/operations/Operations.xml` is the master, and the deploy installs it on every host. Keep `mainMenu` and `closeOnSave` on `<settings>` true (the owner's Operations Pro "Add Operations to main menu" and "Close window on save"); a false silently reverts the owner's choice on each deploy, as after the 2026-11-02 rebuild. If Operations vanishes from PanelPro's menu bar, check these two first; the entry appears only after a restart.
