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

Signal masts and Signal Mast Logic stay active, the hidden virtual masts included (10 since 2026-11-20: the yard-end and Dispatcher rear masts went with the yard throats, below, and the helix-foot masts 38RA and 40RA with the one-block helix tracks). `IQC:AUTO:0001` (hide
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
it builds from the live `tables.xml` (which holds none of them since the release); it does not write this file.

Files outside tables.xml stay in the repo but are not shipped while their feature is parked
(`tools/hosts/sync_hart_package.sh`): the traininfo files and `dispatcheroptions.xml` (`jmri/layouts/hart/dispatcher/`),
the USS CTC icons and `GUIObjects.xml` (`jmri/layouts/hart/ctc/`), and `repair_dispatcher_traininfo.py`. Copies
already installed on a host stay until removed by hand.

## Scripts that serve the parked features

They stay so the features can be unparked; nothing active runs them for the parked feature. Paths are under
`jmri/layouts/hart/scripts/` unless named. Three are in this folder (owner, 2026-11-19), shown as `parked/…`: no host
runs them and the deploy never shipped them. Their tests stay in `jmri/layouts/hart/scripts/tests/`.

| Feature | Only for the parked feature |
|---------|-----------------------------|
| Dispatcher System | `run_dispatcher_stage1.py`, `run_panelpro_stage1.sh`, `run_panelpro_traininfo_repair.sh`, `repair_dispatcher_traininfo.py`, `parked/retarget_dispatcher_traininfo_transits.py`, `fix_traininfo_detection.py`, `parked/polish_hart_layout_editor.py` (run by `run_panelpro_stage1.sh`; puts the lamps and block contents labels back after Stage 1), `parked/occupancy_lamps_display_only.py` (the lamps' display-only check, test in `parked/tests/`) |
| NX | `parked/apply_nx_layer.py` (imports `nx_contract.py` from the scripts folder), `discover_nx.py`, `run_nx_discover.sh`, `jmri/scripts/generate_nx_pairs.py` |
| USS CTC | `build_ctc_full_15col.py` (unsafe to re-run, ADR-005) |

Still used by active tools, so they must keep working while parked:

- `reconcile_dispatcher_stations.py`: `audit_panel_contracts.py` (in `tools/check.sh`) reads the stations through it.
- `nx_contract.py`: `audit_panel_contracts.py` (in `tools/check.sh`) and `hartlib.parked` import it.
- `gen_ctc_track_plan.py` and `uss_switch_only_columns.py`, which it imports: the layout facts and the CATS desk
  tests read the USS board grid through them.
- `apply_dispatcher_roster_profiles.py`: the host apply step.
- `ensure_dispatcher_roster_profiles.py`: `loco_roster_import.py` tells the operator to run it.
- `cleanup_uss_ctc_leftovers.py`: it was run in a rename pass by `apply_public_names_tree.py`, retired 2026-11-20.

The three scripts that edit the panel work on the generated panel only (`hartlib.tables.require_generated_panel`: it
holds the generated-panel marker, `hartlib.tables.GENERATED_PANEL_MARKER`) and refuse any other: the hand-drawn
panel's pixel tables and the one-off edit scripts are gone (the one-off scripts are in `archive/jmri-scripts/`). Every
position comes from the panel itself or from `--reference`, the tables before Stage 1, which `run_panelpro_stage1.sh`
passes:

- `reconcile_dispatcher_stations.py`: the 12 stations (block comments, MoveTo and move-in-progress sensors) and their
  clusters. Each cluster icon stays where it stands, or goes back where it stood on `--reference`; a missing progress
  lamp or station lamp takes its usual offset from the MoveTo button, and a station whose MoveTo button is on neither
  panel stops the run.
- `parked/polish_hart_layout_editor.py`: each Stage 1 lamp where its sensor's lamp stood on `--reference` (else where the
  panel's own one lamp stands, else at the turnout circle's centre or the middle of the track), a lamp on a sensor
  the reference panel shows none for removed (Stage 1 adds one on every block sensor, the main and upper levels'
  too), each block contents label on level 4 where it stood, every lamp display only.
- `parked/apply_nx_layer.py`: the ISNX sensors and their bindings in the mast slots. It adds or moves no NX icon (the
  generated panel shows none) and works with or without the Dispatcher System panel.

While the Dispatcher System is parked, `reconcile_dispatcher_stations.py` and `parked/polish_hart_layout_editor.py` print
SKIPPED and change nothing.

Stage 1 changes nothing else on the panel. Stock `CreateIcons` (`jython/DispatcherSystem/CreateIcons.py`:
`removeIconsAndLabels`, `addIcons`) removes and re-adds only the block contents labels, the block sensors' lamps,
the MoveTo and move-in-progress icons, and labels with its control texts ("Run Dispatcher System" and so on, which
it puts on the "Dispatcher System" panel). It leaves the mast icons, the captions and the panel's attributes as
the build wrote them. So the repair has no mast or caption pass: the hand-drawn panel's polish `--overlap-cleanup`
(which re-hid the virtual masts) and its caption styles are not needed after Stage 1.

## Staging panel lamps

`staging_panel_lamps.json` holds the occupancy lamps and Dispatcher station clusters of the staging "HART Railroad"
panel. The owner decided on 2026-11-17 that they belong with the Dispatcher System, so the build
(`build_layout_le.py`, from the staging device map and `panel_items.json`) leaves them off. There are 79 elements:

- 20 track lamps
- 21 OS lamps, plus one for each second crossover half (23b, 7b)
- 12 stations, each with its MoveTo button, move-in-progress lamp and station occupancy lamp

They are written in the `panel_items.json` form (`tools/schematic/panel_items.py`). Each is anchored at its block's
drawn centre, at the offset the approved staging candidate gave it; each lamp's sensor is in its own entry (`BS S-R`
and so on). Since 2026-11-21 (owner) the lamps are parked on every level with all their code and checks: the South
Yard lamp column (`lamp_columns` in the `le_labels` of `preferences.json`'s `staging` section, which only kept room
for them) is gone, the display-only check `occupancy_lamps_display_only.py` and its test are in this folder
(`parked/tests/`), out of `tools/check.sh`, and the lamp-offset check of `test_le_cutover.py` is retired. Their
sensors stay in tables.xml: only the panel icons are parked. Bringing them back means giving `lamp_columns` back too.

Put back on a copy of the device-map candidate on 2026-11-17, all 79 landed within 1 px of where the last
overlay-built candidate had them, so they do not have to be placed again. The 24 station icons are also in
`tables_parked.xml`, with their hand-drawn places.

To bring them back, append this file's `items` to `jmri/layouts/hart/data/schematic/panel_items.json` and rebuild.
Also give the plugin the station clusters as `extras` again (as the retired `le_overlay.station_extras` did; see git
history before the switch-over), so the label layer keeps clear of them: without them 14 block contents icons
(OS Switch 7, OS Switch 9, Barn, EH-2, EH-3, East Lead, East Lead East, K-1, K-2, McKees Rocks, McKeesport, Scale,
W-1, W-2) sit somewhere else than they did with the clusters. `parked/polish_hart_layout_editor.py` adds a switch OS lamp
that is missing once the feature is back.

## Checks

- `python3 -m hartlib.parked check` (in `tools/check.sh`, with `PYTHONPATH=tools/hartlib/src`): tables.xml holds no
  element a split would still move and no reference to a parked name, and this file holds each parked feature's parts.
- That check also needs the file to record its source commit.
- The checks of a parked feature's data (layout facts, the USS CTC tests, the Dispatcher stations) read it put back
  into a copy of the tables (`hartlib.parked.with_parked`), so it stays consistent with the active tables.

## Unpark

1. While the feature is still in `PARKED`, write a copy of the live `tables.xml` with its snapshot from this file
   put back: `hartlib.parked.with_parked_file([feature])` (`with_parked`, through `restore`, puts the elements and
   bindings in place; it does nothing for a feature already out of `PARKED`).
2. Take the feature out of `PARKED` in `tools/hartlib/src/hartlib/parked.py`, then build on that copy
   (`build_layout_le.py --as-live --tables <copy>`): the build starts from the tables it is given, and the live
   `tables.xml` holds none of the parked data. Its items on the "HART Railroad" panel (NX slots, MoveTo buttons
   and lamps) are not drawn by the build; Stage 1 or NX Discover in step 3 puts them back.
3. The snapshot is the data that comes back; it matches the 3bd3ac64 geometry (helix unjoined). Refresh it against
   the current geometry with Dispatcher System Stage 1 (`run_panelpro_stage1.sh`: sections, transits, traininfo,
   stations) or NX Discover (`run_nx_discover.sh`), in a sandbox first (`tools/hosts/sandbox/README.md`).
4. Put the expected counts back (`audit_panel_contracts.py` EXPECTED_GRAPH, `panelpro_smoke_test.py`), and deploy:
   the folders above ship again.
5. Dispatcher System only: put its two checks back in `tools/check.sh`,
   `reconcile_dispatcher_stations.py --check --no-sync` and `parked/polish_hart_layout_editor.py --check`. Both print SKIPPED
   while the feature is parked, so they were taken out; the approved panel fingerprint
   (`tools/schematic/check_approved.py le-panel`) covers the panel meanwhile.
6. Dispatcher System only: put the hidden yard throats back first (next section). Stage 1 needs them.

## Hidden yard throats (removed 2026-11-20)

The owner dropped them on 2026-11-20. They existed only for the parked Dispatcher System, so **unparking the
Dispatcher must restore the throat blocks and their rear and yard-end masts**. They are defined in full at commit
**5a5bff0a** (the last commit with them; `origin/main` 43b0aa32 has them too). Take each file's rows from there:
`git show 5a5bff0a:<path>`.

- **Blocks** (12, each a short block at one end of its yard track, sharing that track's detector and drawn at 15.748 in,
  400 mm). The rows are the level 1 block rows of `jmri/layouts/hart/data/devices.csv` (before ADR-029, `device_map_staging.csv`), each a block row plus its name in
  the occupancy row's `blocks ...` note. The yard track's `trial_name` took the middle share, `Track <edge> 2/3`, or
  `1/2` for East Lead and `2/2` for K-1. In `block_lengths.csv` they had source `stub`, and the tools of that commit
  read them: `plan_lengths.py` fixed lengths, speed-profile detector sums and the electrical drawings.

  | Block | System name | Trial name | Detector |
  |-------|-------------|------------|----------|
  | Track S-R West / East | IB:AUTO:0061 / 0060 | Track e10 1/3 / 3/3 | BS S-R |
  | Track S-1 West / East | IB:AUTO:0052 / 0053 | Track e22 1/3 / 3/3 | BS S-1 |
  | Track S-2 West / East | IB:AUTO:0054 / 0055 | Track e27 1/3 / 3/3 | BS S-2 |
  | Track S-3 West / East | IB:AUTO:0056 / 0057 | Track e20 1/3 / 3/3 | BS S-3 |
  | Track S-4 West / East | IB:AUTO:0058 / 0059 | Track e19 1/3 / 3/3 | BS S-4 |
  | Track East Lead East | IB:AUTO:0062 | Track e26 2/2 | BS East Lead |
  | Track K-1 West | IB:AUTO:0063 | Track e15.0 1/2 | BS K-1 |

- **Masts** (virtual one-low, at the throat boundaries; in `staging_masts_virtual.csv` and
  `staging_signals_virtual.csv` of 5a5bff0a~1, `le_signal_boundaries.csv` (retired in e4b0c379; read it at e4b0c379~1) and `public_name_map.csv`):
  - yard-end masts, each facing its yard track into its throat 40 cm from the ladder switch:
    - 16L, 16R (S-R, $1016, $1017);
    - 18L, 18R (S-1, $1008, $1012);
    - 20L, 20R (S-2, $1009, $1013);
    - 22L, 22R (S-3, $1010, $1014);
    - 26L, 26R (S-4, $1011, $1015);
  - Dispatcher rear masts:
    - 36L ($1025), Track East Lead East into Track East Lead;
    - 40RB ($1026), Track K-1 West into Track K-1.
  - Put them in by a rule in `build_masts.py`, or bring back the hand-kept files and the code that read
    them (`read_virtual` in `build_staging_masts.py` at 5a5bff0a, now `build_masts.py`; both were removed when nothing was left in them).
- **tables.xml**: each throat's `<block>` (both passes) and `<layoutblock>`. Its block paths were moved onto its
  track: the track's path to the throat became the throat's path to its OS block (with the turnout setting), and
  the OS block's path to the throat now points at the track. Take them from `tables.xml` at 5a5bff0a.
- Then `make panels`, `sync_signals.py --check`, stock discovery in a sandbox and the owner's approval, as for any
  staging change (ADR-024).

Exception to ADR-010 (owner, 2026-11-20): the notes for a parked feature live with its parked data, so `DISPATCHER_LAYOUT_HOOPS.md` is here and not in `docs/`.
