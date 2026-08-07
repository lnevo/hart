# ADR-003 — JMRI config isolation (panel-only change)

- **Status:** Accepted
- **Date:** 2026-08-07
- **Deciders:** lnevo

## Context

Live JMRI already has MQTT turnouts, block sensors, LogixNG helpers, and profile prefs. Rewriting the whole configuration would risk hardware mapping regressions.

## Decision

**HART changes the layout panel XML only** (geometry, blocks, labels, panel-local cleanup).

Keep from the existing configuration:

- MQTT turnout / sensor managers and hardware maps  
- Profile / connection setup  
- LogixNG window helpers / timebase / memories as already used  
- Live occupancy sensor **userNames** (e.g. `Block 2-3`) wired to MQTT  

Remove from the **hart panel** (not from a forced tables rewrite unless needed):

- Unreferenced **internal** sensors (`ISIS*`) left over from earlier pipelines  
- Always **keep** `ISCLOCKRUNNING`  

Do **not** in phases 0–2:

- Replace MQTT occupancy with new ISIS block sensors  
- Redeploy to Pi/minipc as the cutover (hart is developed in-repo first)  
- Edit `tables/tables.xml` (read-only source rule still applies)

## Consequences

- Bootstrap copies linear6 panel → hart outputs, then purges unused internals.  
- Cutover runbook (later phase) swaps which panel file the existing profile loads.  
- Agents must not invent a parallel MQTT namespace.

## Alternatives considered

- Greenfield JMRI profile — rejected for phases 0–2.  
- Regenerate all block sensors as ISIS — rejected; live MQTT occupancy stays.
