# Parked features

Since the helix-join release (owner, 2026-11-17) three features are out of the active
`jmri/layouts/hart/output/tables.xml`, with all their data kept here. `tables_parked.xml` is a frozen snapshot of the
live elements: split verbatim, once, from `tables.xml` as deployed at commit **3bd3ac64** (main before the release;
the file's `source` attribute records it).

| Feature | What is parked | Count |
|---------|----------------|-------|
| `nx` Entry/Exit | `<entryexitpairs>` | 36 pairs |
| | the ISNX sensors (`nx_contract.ISNX_SYSTEM`) | 23 |
| | NX sensor slots on the HART Railroad panel (layoutturnout `sensorA`..`sensorD`, anchor `eastboundsensor` / `westboundsensor`) | 20 + 3 bindings |
| `dispatcher` Dispatcher System | `<sections>` and `<transits>` (the generated panel's Stage 1) | 197 sections, 187 transits |
| | the "Dispatcher System" Layout Editor panel | 1 panel |
| | section direction sensors `IS:IY:AUTO:*`, control sensors `IS:DSCT*`, MoveTo `IS:DSMT:*`, move-in-progress `IS:DSMP:*` | 377 sensors |
| | the 12 MoveTo station buttons and 12 move-in-progress lamps on HART Railroad | 24 icons |
| | memory `IMIS:ISMEM:versionNo`, Logix `IX:DSLX:1` and conditional `IX:DSLX:1C1` | 1 + 1 + 1 |
| | LogixNG ConditionalNG `IQC:AUTO:0003` "Hide Dispatcher System", its action `IQDA:AUTO:0003`, its entry in `IQ:AUTO:0001` | 1 + 1 + 1 |
| | the section named by each Signal Mast Logic destination (`associatedSection`) | 163 bindings |
| `uss` USS CTC machine | `<ctcdata>` (20 code buttons) | 1 |
| | the "USS CTC" Panel Editor panel | 1 panel |
| | CTC lever and indication sensors `IS<n>:<role>`, `IS:DEBUGCTC`, `IS:RELOADCTC`, `IS:FLEETING`, `IS:PRECONDITIONING_ENABLED` (JMRI's CTC code creates and reads it) | 264 sensors |
| | Logix `IX:CTC:REVDEF` and conditional `IX:CTC:REVDEF:C1` | 1 + 1 |
| | LogixNG ConditionalNG `IQC:AUTO:0002` "Hide USS CTC", its action `IQDA:AUTO:0002`, its entry in `IQ:AUTO:0001` | 1 + 1 + 1 |

Signal masts and Signal Mast Logic stay active, the 26 hidden virtual masts included. `IQC:AUTO:0001` (hide
WiThrottle) and `IQC:AUTO:0004` (hide HART Railroad under CATS) stay. So do `switches.csv`, `mast_cells.csv`, the
layout facts data, the block comments that mark the Dispatcher stations, and the USS yellow sensor icons the panel's
lamps use.

## The file

`tables_parked.xml` was written once by `python3 -m hartlib.parked freeze --from 3bd3ac64` (with
`PYTHONPATH=tools/hartlib/src`) and is kept as data: `make panels` does not touch it, and it is not edited by hand.
One `<feature>` per parked feature: `<tables>` holds its elements verbatim, in the section or panel they came from (a
sensors section holds only the parked sensors, a `LayoutEditor` element named "HART Railroad" holds only the parked
icons), and `<bindings>` names each slot, list entry or child the split cleared (panel, element, ident, slot,
value). It is not a JMRI file.

The cut-over build (`tools/schematic/build_layout_le.py --as-live`) leaves the same features out of the candidate
it builds from the last hand-drawn tables; it does not write this file.

Files outside tables.xml stay in the repo but are not shipped while their feature is parked
(`tools/hosts/sync_hart_package.sh`): the traininfo files and `dispatcheroptions.xml` (`jmri/layouts/hart/dispatcher/`),
the USS CTC icons and `GUIObjects.xml` (`jmri/layouts/hart/ctc/`), and `repair_dispatcher_traininfo.py`. Copies
already installed on a host stay until removed by hand.

## Scripts that serve the parked features

They stay so the features can be unparked; nothing active runs them for the parked feature. Paths are under
`jmri/layouts/hart/scripts/` unless named.

| Feature | Only for the parked feature |
|---------|-----------------------------|
| Dispatcher System | `run_dispatcher_stage1.py`, `run_panelpro_stage1.sh`, `run_panelpro_traininfo_repair.sh`, `repair_dispatcher_traininfo.py`, `retarget_dispatcher_traininfo_transits.py`, `fix_traininfo_detection.py`, `polish_hart_layout_editor.py` (puts the lamps and block contents labels back after Stage 1) |
| NX | `apply_nx_layer.py`, `discover_nx.py`, `run_nx_discover.sh`, `jmri/scripts/generate_nx_pairs.py` |

They work on the generated panel only (it holds the generated-panel marker, `hartlib.tables.GENERATED_PANEL_MARKER`)
and refuse any other: the hand-drawn panel's pixel tables and the one-off edit scripts are gone (the one-off scripts
are in `archive/jmri-scripts/`). Every position comes from the panel itself or from `--reference`, the tables before
Stage 1, which `run_panelpro_stage1.sh` passes:

- `reconcile_dispatcher_stations.py`: the 12 stations (block comments, MoveTo and move-in-progress sensors) and their
  clusters. Each cluster icon stays where it stands, or goes back where it stood on `--reference`; a missing progress
  lamp or station lamp takes its usual offset from the MoveTo button, and a station whose MoveTo button is on neither
  panel stops the run.
- `polish_hart_layout_editor.py`: each Stage 1 lamp where its sensor's lamp stood on `--reference` (else where the
  panel's own one lamp stands, else at the turnout circle's centre or the middle of the track), each block contents
  label on level 4 where it stood, every lamp display only. It refuses tables whose Dispatcher System is parked.
- `apply_nx_layer.py`: the ISNX sensors and their bindings in the mast slots. It adds or moves no NX icon (the
  generated panel shows none) and works with or without the Dispatcher System panel.
| USS CTC | `build_ctc_full_15col.py` (unsafe to re-run, ADR-005) |

Still used by active tools, so they must keep working while parked:

- `reconcile_dispatcher_stations.py`: `audit_panel_contracts.py` (in `tools/check.sh`) reads the stations through it.
- `polish_hart_layout_editor.py`: `audit_panel_contracts.py` checks the block contents labels with its rule.
- `nx_contract.py`: `audit_panel_contracts.py` (in `tools/check.sh`) and `hartlib.parked` import it.
- `gen_ctc_track_plan.py` and `uss_switch_only_columns.py`, which it imports: the layout facts and the CATS desk
  tests read the USS board grid through them.
- `apply_dispatcher_roster_profiles.py`: the host apply step.
- `ensure_dispatcher_roster_profiles.py`: `loco_roster_import.py` tells the operator to run it.
- `cleanup_uss_ctc_leftovers.py`: `apply_public_names_tree.py` runs it in a rename pass.

## Staging panel lamps

`staging_panel_lamps.json` holds the occupancy lamps and Dispatcher station clusters of the staging "HART Railroad"
panel. The owner decided on 2026-11-17 that they belong with the Dispatcher System, so the build
(`build_layout_le.py`, from the staging device map and `panel_items.json`) leaves them off. There are 79 elements:

- 20 track lamps
- 21 OS lamps, plus one for each second crossover half (23b, 7b)
- 12 stations, each with its MoveTo button, move-in-progress lamp and station occupancy lamp

They are written in the `panel_items.json` form (`tools/schematic/panel_items.py`). Each is anchored at its block's
drawn centre, at the offset the approved staging candidate gave it; each lamp's sensor is in its own entry (`BS S-R`
and so on). The lamp layout preferences stay in place: the South Yard lamp column (`lamp_columns` in
`staging.preferences.json`'s `le_labels`) and the label layer's room for lamps.

Put back on a copy of the device-map candidate on 2026-11-17, all 79 landed within 1 px of where the last
overlay-built candidate had them, so they do not have to be placed again. The 24 station icons are also in
`tables_parked.xml`, with their hand-drawn places.

To bring them back, append this file's `items` to `jmri/layouts/hart/data/schematic/panel_items.json` and rebuild.
Also give the plugin the station clusters as `extras` again (as the retired `le_overlay.station_extras` did; see git
history before the switch-over), so the label layer keeps clear of them: without them 14 block contents icons
(OS Switch 7, OS Switch 9, Barn, EH-2, EH-3, East Lead, East Lead East, K-1, K-2, McKees Rocks, McKeesport, Scale,
W-1, W-2) sit somewhere else than they did with the clusters. `polish_hart_layout_editor.py` adds a switch OS lamp
that is missing once the feature is back.

## Checks

- `python3 -m hartlib.parked check` (in `tools/check.sh`, with `PYTHONPATH=tools/hartlib/src`): tables.xml holds no
  element a split would still move and no reference to a parked name, and this file holds each parked feature's parts.
- That check also needs the file to record its source commit.
- The checks of a parked feature's data (layout facts, the USS CTC tests, the Dispatcher stations) read it put back
  into a copy of the tables (`hartlib.parked.with_parked`), so it stays consistent with the active tables.

## Unpark

1. Take the feature out of `PARKED` in `tools/hartlib/src/hartlib/parked.py`.
2. Put the feature's live snapshot from this file back into the tables (`hartlib.parked.restore` gives the
   elements and bindings in place), then `make panels` so the candidate holds the feature again.
3. The snapshot is the data that comes back; it matches the 3bd3ac64 geometry (helix unjoined). Refresh it against
   the current geometry with Dispatcher System Stage 1 (`run_panelpro_stage1.sh`: sections, transits, traininfo,
   stations) or NX Discover (`run_nx_discover.sh`), in a sandbox first (`tools/hosts/sandbox/README.md`).
4. Put the expected counts back (`audit_panel_contracts.py` EXPECTED_GRAPH, `panelpro_smoke_test.py`), and deploy:
   the folders above ship again.
5. Dispatcher System only: put the station check back in `tools/check.sh`
   (`reconcile_dispatcher_stations.py --check --no-sync`, which prints SKIPPED while the feature is parked) and add
   `polish_hart_layout_editor.py --check` beside it. Both were taken out while parked, when neither checked anything
   the approved panel fingerprint (`tools/schematic/check_approved.py le-panel`) does not.
