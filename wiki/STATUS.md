# Live status — HART Digicon

Updated: 2026-08-18 — **Live launchers**: **CATS CTC** (`HART_Master_CTC_hold.xml`, `HOLD_ONLY`) and **CATS ABS** (`HART_Master_ABS.xml`, SECSIGNALs unbound "CATS " prefix — reference mimic). JMRI SML owns aspects either way. System overview: [`cats/docs/HART_DIGICON_SYSTEM.md`](../cats/docs/HART_DIGICON_SYSTEM.md).

## Signals — native SML live (2026-08-18)

- SML is **native**: 36 dests discovered by Layout Editor, stored `useLayoutEditor=yes` in `tables.xml`; the `apply_sml_cats_pairs.py` hand-pair injector and its startup Jython are retired (PAIRS kept as oracle for `cats/scripts/validate_le_signalling.py`). Re-running Discover is safe.
- Two-head homes retyped to custom **`hart-aar` `SL-2-digicon`** (in `cats/resources/signals/hart-aar/`; deployed by `sync_hart_package.sh`). Stock `SL-2-high-abs` pinned masts at Stop behind an Approach (its mapping only offered undisplayable Advance Approach / Approach Medium) — root cause of the "always red" signals. Dwarfs stay AAR-1946 `SL-1-low`.
- MQTT mimic QA green (30/30): `cats/screenshots/mimic_qa/run_native_sml_qa.py` — covers 100/102, 110, 111a, 114/115, K-1/K-2, A48 balloon occupancy, 117/117b, incl. diverging **Medium Clear** (R/G) and 3-aspect **Clear** chaining. Notes: `cats/screenshots/mimic_qa/native_sml_qa_notes.md`; runtime criteria dump: `jmri/layouts/hart/scripts/dump_sml_criteria.py`.
- **CATS "blank windows" bug fixed (2026-08-18)**: unpainted System Console / clock / WiThrottle windows were CATS `Screen.init` dying on the Swing EDT at panel load, not LogixNG. Two causes, both fixed: (1) K-1/K-2 boundary sections (43,6)/(43,7) had anonymous `<BLOCK />` edges → `ClassCastException` in `discoverAdvanceVitalLogic`; now named `OS 115 (Princess)`/`OS 114 (Princess)` in all four Masters. (2) drive-mode templates requested `Restricting`, which `hart-aar` masts don't define → `IllegalArgumentException`; `aar_aspect_bridge.py` now maps RES_\*→Stop and R283/R286→Medium Clear/Medium Approach (CATS lamps paint the diverging pair). Verified: CATS ABS loads clean on the Pi, all windows paint.
- **Held ownership (2026-08-18)**: `unhold_signal_masts.py` retired (removed from Mac/Pi profiles, sync, and installers). Masts boot Unheld, so SML runs ABS by default with no script; **Held is CATS CTC's channel**. Verified live on the Pi: CTC load holds all 25 masts at Stop; left-click entrance (`Princess West OS 113b`) → CATS unholds, SML posts Approach, MQTT head goes Yellow; click again → re-held, Stop, Red.

## JMRI CTC — full plant, 15 columns with Barn (2026-08-19)

- **Barn interlocking inserted** (cols 4-6, geographic order kept): full rebuild via `jmri/layouts/hart/scripts/build_ctc_full_15col.py` (replaces the incremental brick-plane/east-end scripts; those are kept for history). Columns west→east: 1-3 Brick/Plane (SW101, 100, 102), **4-6 Barn** (SW117 LH xover `Block 13-3`+`13-4`, SW116 `Block 3-1`, SW103 `Block 3-2`), 7-12 East End (SW107, 108, 111 xover, 109, 110, 112), 13-15 Princess (SW113 xover, 114, 115). **Princess levers renumbered 19-24 → 25-30.** 23 masts CTC-held.
- **Dwarf relocated to make Barn a real plant**: `West Yard East Yard T6` moved from the 116-117 boundary (TO117.B) to east of Switch 103 (TOR14.B) — its section now spans SW103 + SW116 + the 117 crossover, mirroring how the East End east home covers 111/112. SML re-discovered; westbound pairs from Yard Track 1 now run through the whole plant to the Plane homes.
- **Two new entrance dwarfs** (virtual masts `IF$vsm:AAR-1946:SL-1-low($1001/$1002)` — no hardware yet, swap to MQTT heads later): **`South Yard East OS 104`** at Switch 104's Yard Track 2 leg (governs up-the-ladder moves west into Barn; also splits the old over-long East Lead→Plane pairs) and **`West Yard North OS 116`** at Switch 116's C leg (governs West Yard ladder moves east into the plant). `East Lead → South Yard East OS 104` had to be added as a **manual fixed pair** (discovery declines it; criteria derived live via `ConnectivityUtil`: SW112 N, SW110 R, SW109 R).
- **Topology can't see north/south entrances**: `Topology.getTrafficLockingRules` only walks east/west neighbors, so the two ladder masts got hand-built TRL rules (col 9/10 right: SW116 R + SW103 N→`East End West Yard Track 1` / SW103 R→`East End South OS 110`; col 11/12 left: SW103 R routes to the Plane homes). Everything else auto-generated — including eastbound Barn routes threading the **uncontrolled** Switch 104 (occupancy-only, correct).
- Verified live on Barn: lever 12 Left + code → `West Yard East Yard T6` unholds to Restricting (Yard Track 1 route), `South Yard East OS 104` unholds but correctly sits at Stop (needs SW103 R); normalize + code re-holds (time locking). Lever 10 Right correctly **rejected** with SW116 Normal; after SW9 lever Reverse + code (Switch 116 is DIRECT feedback, no FB sensors) → accepted, `West Yard North OS 116` clears to Restricting. Switch-lever sensors are `IS<odd>:LEVER`, **ACTIVE = Normal, INACTIVE = Reverse**; a switch won't move while its signal lever is off Normal (correct USS behavior).
- **Panel track plan redrawn (2026-08-19)** via `jmri/layouts/hart/scripts/redraw_ctc_track_plan.py`: Barn SW117 and Princess SW113 now use the single LH scissor graphic (`USS/track/crossover/left/os-l-sc-*`) instead of two separated half-turnout icons, and the East End SW111 scissor moved down to the main row (y=80) so all crossovers sit *under* their OS lamps; secondary-track lamps (13-4, 1-6, 12-6) sit on the scissor's lower bar (y=101). The main row is one **contiguous track line**: `line050.gif` fillers between every column, plus OS lamps for the connector blocks — `Main West Brick-Plane` (4-6), `East Main Ext` (4-7), `Yard T6` (13-1), `Yard Track 1` (2-8), `East Lead` (1-7). Startup "Signals are non red in both directions" warning at CTC reload is benign: SML had cleared the unheld new dwarfs before the runtime took over and held everything.
- **Barn signals synced to LE + CATS (2026-08-19)**: the two new dwarfs' LE icons re-stored with proper scale 1.5 / rotation (270° OS 104, 90° OS 116 — they were flat/tiny before). CATS masters updated by `cats/scripts/update_barn_signals.py`: `West Yard East Yard T6` SECSIGNAL moved from (14,7) to east of Switch 103 at (21,7) RIGHT, `West Yard North OS 116` added at (18,7) TOP, `South Yard East OS 104` added at (21,7) BOTTOM (mirroring `East End South OS 110` at (31,7)); applied to `HART_Master.xml` and `HART_Master_ABS.xml` (with `CATS ` prefix), both hold variants rebuilt + validated, deployed `--all`.
- **Gotcha — LayoutEditor extends PanelEditor**: any `isinstance(ed, PanelEditor)` sweep (dispose/resize/deregister) also hits "My Layout" and "Dispatcher System". A reload sweep disposed both on 2026-08-19; restored by extracting their `<LayoutEditor>` elements from the stored `tables.xml` into a wrapper file and `cm.load()`-ing it. Also: `cm.storeConfig()` writes tables only — panels need `cm.storeUser()`.
- **Gotcha — panel reloads duplicate stored panels**: disposing a Panel Editor does *not* deregister it from ConfigureManager; after two GUI reloads the store wrote 3 copies of "Panel " into `tables.xml`. Fixed by `cm.deregister()` of ghost editors before storing. Check `<paneleditor` count after any store that followed a panel reload.
- Previous 12-column state (Princess lever-24 verification, INCONSISTENT-feedback gotcha, `Switch 1-1/1-2/1-3 FB` naming) — see git history of this section; all still applies with the new lever numbers.

## JMRI CTC pilot — Brick + Plane (2026-08-19)

- **Stock JMRI CTC** (Tools ▸ CTC, [help](https://www.jmri.org/help/en/package/jmri/jmrit/ctc/CTC.shtml)) piloted on the Pi as a possible CATS alternative: 3 O.S. sections — col 1 SW1/SIG2 = Switch 101 (OS 101 Brick, yard exits `Brick West Yard 1/2` govern left-to-right), col 2 SW3/SIG4 = Switch 100 (OS 100 Brick, `Brick East Main West` right-to-left), col 3 SW5/SIG6 = Switch 102 (OS 102 Plane, `Plane East East Main Ext`/`Plane East OS 102` right-to-left). Uni-directional sections (sparse Digicon ABS = homes on one side only).
- Built **programmatically** with `jmri/layouts/hart/scripts/build_ctc_brick_plane.py` (same factory + `Topology` auto-generate the editor uses — no manual editor entry). Traffic locking rules auto-derived from SML: 2 per section, correctly cross-referencing switch alignments (e.g. yard exits need SW100 Normal; westward Main West routes need SW100 Reverse and pick destination by SW102). Config + generated USS panel now live in `tables.xml` (`<ctcdata>` + PanelEditor "Panel "); repo copies: `jmri/layouts/hart/output/tables.xml`, `jmri/layouts/hart/ctc/GUIObjects.xml`.
- **Verified live**: runtime start holds all 5 masts at Stop (signals normal); signal lever Right + code button → traffic locking validates, unholds yard masts, SML clears `Brick West Yard 1` to Slow Clear while `Yard 2` stays at Stop (turnout not lined), R indicator lights, opposing mast stays held; normalize runs **time locking** (indicators out-of-correspondence ~3 s) then re-holds. Switch lever + code commands the turnout and waits for TWOSENSOR field correspondence.
- Gotchas: JMRI's `CreateGUIObjectsXMLFile` writes `Red-on/Red-off.gif` but the files are lowercase → "Icon Not Found" on Linux; fixed in our `GUIObjects.xml`. Code buttons are edge-triggered (set sensor Inactive→Active). Runtime doesn't auto-start: Tools ▸ CTC ▸ Run CTC Logic (or add a Start Up action); `IS:RELOADCTC` Active reloads config in place. FB sensor numbering is offset: Switch 100→`Switch 4-1 FB`, 101→`4-2`, 102→`4-3`.
- **Never run JMRI CTC runtime and CATS CTC at the same time** — both drive Held on the same masts. CATS ABS (unbound viewer) is fine alongside.

## Dispatcher System (2026-08-18) — set up, awaiting live test

- JMRI **Dispatcher System** (`jython/DispatcherSystem`, [help](https://www.jmri.org/help/en/html/scripthelp/DispatcherSystem/DispatcherSystem.shtml)) Stage 1+2 run on the Pi against `tables.xml` (replaces last session's hand-built transit). Stations = blocks with `stop` in the comment: **West Main Ext, Main West, Main East, McKees Rocks, McKeesport, East Main Ext, Main West Brick-Plane, East Lead** (8) — covers the full mainline circuit with intermediate stops, so a complete loop can be chained. Generated: station buttons/icons on My Layout, a "Dispatcher System" command panel, 41 sections, 102 transits, 220 traininfo files (fwd+rvs per pair), and a `Run Dispatcher` Logix (`IX:DSLX:1`) that starts the run threads from the panel button.
- **Stub tracks cannot be stations**: K-1, K-2, West Yard 1/2 ("Track 1/2"), and the Yard Tracks fail Stage 1 transit generation ("missing signal mast in block X") because CreateTransits requires each station block to be covered by a `mastA:mastB` section — stubs have no mast at the buffer end. Making them stations would require adding (virtual) stub-end masts and re-discovering SML.
- **Never run Stage 1 or store panels from inside CATS.** CATS embeds JMRI on the same profile, so a store from a CATS session persists CATS runtime beans into `tables.xml` — 25 `IF$vsm:CATS1/CATS2` virtual masts (which then fail to load in plain JMRI: "Signal definition not found: CATS1") plus `IMDECODER_*` memories. Happened 2026-08-18; file was surgically cleaned and verified under PanelPro. Configure JMRI from PanelPro only.
- **SML survived regeneration**: Stage 1 deletes + re-discovers; result matched our 34 discovered pairs, and the 2 manual K-stub pairs (`113a→K-2`, `113b→K-1`) were re-added — 36 total, verified after restart.
- **Train detection**: DispatcherSystem hardcodes Entire Train (`setResistanceWheels(True)`) into every traininfo it generates — this is why it "kept getting overwritten". Fixed to `TRAINDETECTION_HEADANDTAIL` by `jmri/layouts/hart/scripts/fix_traininfo_detection.py`; **rerun it after any Stage 1 rerun**.
- **2091 speed profile**: synthesized linear profile (10 steps, 400 mm/s at full) written into the Pi roster via the JMRI API — required by the system (registration lists only speed-profiled locos, traininfo uses `usespeedprofile=yes`). Replace with a measured profile (Roster ▸ Speed Profiling) for accurate station stops.
- Dispatcher options: `autoturnouts=yes` + `useturnoutconnectiondelay=yes` added (Stage 2 requirements); rest already correct (`usesignaltype=signalmast`, roster trains, auto-allocate, HO scale).
- Cleanups en route: K-1/K-2 block lengths set (609.6 mm); en-dashes removed from `Yard T6` comment and the `Main West Brick-Plane` block name (DispatcherSystem scripts crash on non-ASCII).
- **To test (layout on)**: launch PanelPro (not CATS) on the Pi → Dispatcher System panel ▸ *Run Dispatcher System* ▸ OK → place 2091 at a station ▸ *Setup Train in Section* (pick block, train, facing) → *Run Dispatch* ▸ click destination station button. *Simulate Dispatched Trains* dry-runs without hardware.
- **Hands off the phone throttle during a dispatch.** Root cause of the 2026-08-18 "train runs backwards" incidents: JMRI shares one throttle per loco address, and `AutoActiveTrain`'s direction is the *live throttle direction bit* — the auto engineer asserts it once at dispatch start, never continuously. Any WiThrottle direction press (or re-acquiring the loco, which re-sends the phone's last direction) flips the shared bit, and the next dispatcher speed command drives the train the wrong way (`runInReverse=yes` + `forward=True` observed live). Registration/facing answers were correct all along. Rule: release 2091 from WiThrottle before dispatching, and never nudge a stalled auto train with the phone — terminate and re-dispatch instead.
- Temporary: `jmri_cmd_watcher.py` is in the TCS_MQTT startup for agent-driven automation; remove with `python3 cats/scripts/patch_jmri_startup.py remove --profile /home/pi/.jmri/TCS_MQTT.jmri/profile/profile.xml --script jmri_cmd_watcher.py` when done testing.

## Repo / remote

- GitHub: https://github.com/lnevo/hart  
- Local workspace folder: `Panel` (same git root)  
- Agent branch pattern: `agent/<id>/<topic>` — see [`AGENTS_GIT.md`](AGENTS_GIT.md)  
- Cloud Agents: link `lnevo/hart` at [Cloud Agents dashboard](https://cursor.com/dashboard/cloud-agents)

## Product decision (stop the abstract chase)

| Deliverable | Role |
|-------------|------|
| **`cats/panels/HART_Master_CTC_hold.xml`** | **CATS CTC** — routes/turnouts on; signals HOLD_ONLY; JMRI SML owns aspects |
| **`cats/panels/HART_Master_ABS_hold.xml`** | **CATS ABS** — signals HOLD_ONLY; turnouts on |
| **`cats/panels/HART_Master.xml`** | CTC geometry source (rebuild CTC hold; no desktop icon) |
| **`cats/panels/HART_Master_ABS.xml`** | ABS geometry source (rebuild ABS hold; no desktop icon) |
| `cats/panels/sheets/HART_sheet_West_Yard2.xml` | Legacy sheet WIP — **do not checkpoint**; Masters are the live copy |
| `cats/panels/HART_ctc.xml` | Earlier CTC schematic experiment |
| `render_ctc_panel.py` PNG | **Review art only** — cannot open in CATS |

See [`cats/docs/HART_DIGICON_SYSTEM.md`](../cats/docs/HART_DIGICON_SYSTEM.md) and [`cats/docs/DIGICON_VS_CTC_PNG.md`](../cats/docs/DIGICON_VS_CTC_PNG.md).

## Collaboration (Mac ↔ Cloud)

| Role | Owns |
|------|------|
| **Mac / local** | Builder cell-role fixes, live CATS load, occupancy path accept, screenshots |
| **Cloud** | Help on builder/verify when asked; do not overwrite Mac ops branch with PNG-only commits |

Active tip for ops work: this working tree / branch with `build_hart_digicon_from_le.py` Gate‑1 spine fix.

## Now

| Panel | Role | Rebuild |
|-------|------|---------|
| `cats/panels/HART_ctc.xml` | **Ops Digicon** — CTC interlockings | `python3 cats/scripts/build_hart_digicon_ctc.py --mqtt` |
| `cats/panels/HART_le.xml` | LE-pack experiment | `python3 cats/scripts/build_hart_digicon_from_le.py --mqtt` |
| `cats/panels/HART.xml` | Designer Gate 1 | `python3 cats/scripts/wire_designer_ctc_rules.py --mqtt` |

### Gate 1 spine (ops board — required)

```
Main West ═══[ OS 100 ]═══ Block 100-102 (HORIZONTAL) ═══[ OS 102 ]═══ East Main Ext
                  ╲
                   OS 101 (yard)
```

- OS100 plant: continuing **RIGHT** into 100-102; diverge **BOTTOM** to OS101  
- Contiguous West Yard / South Yard / East End ladders (approach+plant pairs)

### Still open

- [ ] Live MQTT: `M2S405` → red only on Block 100-102; `M2S401` → OS 100 only  
- [ ] Wire turnout `ROUTECOMMAND` / `SELECTEDREPORT` from `turnout_bindings.csv`  
- [ ] Princess / East End visual polish after path-accept  
- [ ] Designer redraw or retire as dual-primary

## Manual launch (local Mac only)

```bash
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_le.xml
python3 cats/scripts/validate_cats_panel.py cats/panels/HART_le.xml
# optional schematic review PNG (not a substitute for CATS):
python3 cats/scripts/render_cats_panel.py cats/panels/HART_le.xml /tmp/le.png
```

Do **not** use `CATS_LAUNCH_VIA=app`. Keep-alive LaunchAgent stays disabled.
