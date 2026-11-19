# ADR-023 — Generated panels and pages sit beside the ones they replace

- **Status:** Accepted
- **Date:** 2026-11-14
- **Deciders:** lnevo

## Context

The schematic-maps plugin's logical view will feed more than the system schematic ([`projects/schematic-maps.md`](../projects/schematic-maps.md)):
- a CATS panel for the main and upper levels (C1);
- generated station pages (C2a and later);
- a regenerated Layout Editor panel, which waits until the schematic is finished.

Each of these has a counterpart in use today:
- the staging CATS desk: `cats/panels/HART_CTC.xml` and `HART_ABS.xml` (the hand-drawn `HART_Digicon.xml` is archived);
- the Layout Editor panel in `jmri/layouts/hart/output/tables.xml`;
- the hand-drawn crew pages under `www/crew/maps/`.

Nothing had said whether a generated output replaces its counterpart or sits beside it.

## Decision

Every generated panel or page sits beside the one it would replace, and takes its place only after the owner approves it, one at a time.

- **CATS panels:** generated panels are new files with their own names (for example `cats/panels/HART_Main_Upper_*.xml`). The live desks are untouched and are not deployed in their place. Whether to merge into one desk or keep one desk per level is decided after the owner approves the panel in CATS Designer.
- **Layout Editor:** a regenerated panel first goes in as a separate panel, or in a trial copy of `tables.xml`. The owner compares it with the current panel in PanelPro. It replaces the current one only when the owner says so, through a PanelPro Store and `make tables-pull` (ADR-008, ADR-014).
- **Station pages:** a generated page is published at a separate preview path (for example `www/crew/maps/<station>/generated.html`) or kept as a local preview. The hand-drawn page stays live, and the crew map index links only to it, until the owner approves the generated page for that station.
- Each generated file stays next to the file it would replace, with a `--check` where it is derived, and nothing generated reaches the Pi, Windows or the site in place of a live file before the swap.

## Consequences

- During a trial there are two versions of a panel or page. The generated one is named so it can't be mistaken for the live one.
- A swap is its own reviewed change. It names the file it replaces and removes or archives the old one.
- The 3D-printed station maps (`docs/benchwork/station_maps_3d/`) are made separately and are not covered.
