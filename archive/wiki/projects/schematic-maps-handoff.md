# Schematic maps: history of the build

This page is a dated record, condensed on 2026-11-18. It holds no live steps. The live pipeline, its three input layers (plan overrides, generation rules, preferences) and the decisions that still hold are in [`../pipelines/schematic-panels.md`](../../../wiki/pipelines/schematic-panels.md) (`make panels`). The plan and as-built notes are in [`schematic-maps.md`](schematic-maps.md).

Many files named below were retired along the way: the viewing trial tables, the carried overlay, the physical main and upper builder, the first generated CATS panels and the hand-drawn pixel tables used by the old polish, reconcile and NX scripts. The cut-over steps listed under 2026-11-15 and 2026-11-16 were for parked or obsolete tools (Stage 1, NX Discover, polish, reconcile) and are not to be followed.

## 2026-11-13: the proof and the split into three layers

- The spike (branch `agent/claude/schematic-spike`, draft PR #423, closed once the plugin took over) drew staging, main and upper as one sheet; the owner approved the look of the sample.
- The spike mixed three kinds of input in two options files. The hand-off's main point was to separate them: plan overrides, generation rules and preferences. Streams A1 (split the files), A2 (baseline drawing and fault list), A3 (publish the sheet), B1 (specification, now `docs/ops/SCHEMATIC_SPEC.md`), B2 (tested modules in `model-railroad-skills`), B3 (skill text and style reference), C1 (CATS panel), C2 and C2a (station pages), C3 (Layout Editor) and D1 (signals drawn from the Layout Editor panel's masts) were run in parallel; all are done.
- Hints that had to become rules (main route level through every switch, ladders with the yard track level, rows kept apart only where tracks overlap, hands of added switches from layer 1) were written as rules in the plugin: model-railroad-skills PR #18 (reproduces the approved sheet with no hints) and PR #19 (label room in the grid; the East Lead and South Yard length preferences became the owner's look, not a fix). Known gaps then: labels not checked for collisions, no capacity placeholder.
- Renames merged the same day: East Ext / West Ext (hart PR #425) and Mast 32L to Mast 16R (PR #441).

## 2026-11-14: numbers, styles and trial outputs

- Owner's switch numbers for main (101 to 135) and upper (201 to 245), odd only, set as a `relabel` in layer 1. Facing letters came and went (off since REV 5, ADR-022 amendment). Capacity counts, title block fields, mileposts, station detail sheets and interlocking limits (REV 6, plugin 0.1.8), mast 34R on the slope (REV 7, plugin 0.1.11), a wider upper level (REV 8). Hardening: font fallback, helix boxes and station brackets drawn before labels, run hints that name their tracks (plugin 0.1.4); review fixes for band directions (plugin 0.1.7).
- First generated outputs written beside the live ones for the owner to open: a Layout Editor panel drawn like the schematic with rounded bends (plugin `schematic le`), a CATS panel for the main and upper levels and then for all three levels with staging bound to the live JMRI objects (plugin `schematic cats --bindings`), with a desk parity test. Two masts differ from the live desk and were approved: Mast 24L guards OS Switch 23a, Mast 2035 guards Track K-1.
- Owner's side-by-side rule (ADR-023): all of it beside the live files, one cut-over.
- Hands for main and upper from the plan geometry (`hands.csv`); staging 9 and 13 left as the Layout Editor has them.

## 2026-11-15: panels fit the screen, labels, cut-over phases

- The Layout Editor panel fit the window and gained masts placed in the slot JMRI resolves to the same facing and protected blocks as the live panel (plugin 0.1.16 and 0.1.17); 38RA and 40RA stand at the helix-entrance anchors. The CATS desk was drawn one cell per grid step in a 1900 x 1150 window, with mast rules learned from the CATS source (plugin 0.1.15); the owner reviewed it in real CATS and approved it.
- The cut-over was planned in five phases: candidate, checks, scripts working on the candidate, sandbox rehearsal, cut-over. The hand-drawn pixel tables in the polish, reconcile and NX scripts were kept for a rehearsal and are being removed. A generated-panel marker label let those scripts take positions from the panel itself, and `HART_TABLES=<file>` let `tools/check.sh` run against any tables file.
- The owner approved the track but not the labels, which had been carried from the hand-drawn panel and overlapped. Decision: the builder generates every label, readout and switch number itself with a hard no-overlap check sized to what JMRI draws, one block contents icon per block, and the hand-panel labels are dropped (plugin label layer, then station buttons as "extras"). Main and upper go into the Layout Editor after the staging cut-over.
- Placeholder control points ("CP <lowest switch>") and the device map for main and upper (see [`../STATUS.md`](../../../wiki/STATUS.md)); the upper-deck plan with switches 61 to 91 is obsolete.

## 2026-11-16: three-level candidate, cut-over and CATS cut-over

- The candidate drew all three levels, then was stretched to the window's shape and went through an owner feedback round (crossovers at 45 degrees as JMRI 5.16 draws them, lamps centred in control circles, Switch 3 keeping W-1 level, Switch 13's Barn on leg C). The owner approved it in PanelPro that evening (schematic REV 10, plugin 0.1.25).
- Sandbox rehearsal with the helix joined changed staging's own SML and NX pairs (10RA, 10RB, 12R and 14R paired to 16L; 36RB to 40RB lost; Princess NX pairs changed). Owner decision: cut over unjoined (helix tracks ending at bumpers), main and upper keeping their own joins and 41 control-point masts. The generated panel went live (hart #577, #579, #581; plugin 0.1.27) and was deployed to the Pi, Windows and the website. Joining the helix was left for the release below.
- The generated CATS desks the owner approved on 2026-11-15 became the live desks; `build_cats_panel.py` writes `HART_CTC.xml`, `HART_ABS.xml` and `HART_CTC.bindings.json`, and the first generated panel files and `wire_digicon.py` were retired.

## 2026-11-17: the helix-join release

- Plan (fresh session): join the helix, split the 107 Loop and Switch 225 into corner blocks, fix the main and upper drawing leftovers, wire main and upper masts on the CATS desks, merge two branches with plugin 0.1.28 or later, rehearse, get the owner's review.
- The 225 and 107 Loop splits avoided a JMRI quirk (`LayoutBlock.addThroughPath` ignores incomplete connectivity); nothing to report upstream. Discover makes no round-the-loop pairs, which is JMRI's behaviour and accepted.
- The owner approved the release in a sandbox PanelPro and sandbox CATS: helix joined, main and upper CTC on the CTC desk (a route up the helix stops at 136RA or 136RB), NX, the Dispatcher System and the USS CTC parked, DRAFT mark off the schematic and station sheets. Same day: Switch 225 a block per corner on the CATS desks with its middle dark (plugin 0.1.31), and the Layout Editor geometry moved into plugin preferences (plugin 0.1.35). The current form of these decisions is in the pipeline page.
