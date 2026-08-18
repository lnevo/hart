# Live status — HART Digicon

Updated: 2026-08-18 — **Live launchers**: **CATS CTC** (`HART_Master_CTC_hold.xml`, `HOLD_ONLY`) and **CATS ABS** (`HART_Master_ABS.xml`, SECSIGNALs unbound "CATS " prefix — reference mimic). JMRI SML owns aspects either way. System overview: [`cats/docs/HART_DIGICON_SYSTEM.md`](../cats/docs/HART_DIGICON_SYSTEM.md).

## Signals — native SML live (2026-08-18)

- SML is **native**: 36 dests discovered by Layout Editor, stored `useLayoutEditor=yes` in `tables.xml`; the `apply_sml_cats_pairs.py` hand-pair injector and its startup Jython are retired (PAIRS kept as oracle for `cats/scripts/validate_le_signalling.py`). Re-running Discover is safe.
- Two-head homes retyped to custom **`hart-aar` `SL-2-digicon`** (in `cats/resources/signals/hart-aar/`; deployed by `sync_hart_package.sh`). Stock `SL-2-high-abs` pinned masts at Stop behind an Approach (its mapping only offered undisplayable Advance Approach / Approach Medium) — root cause of the "always red" signals. Dwarfs stay AAR-1946 `SL-1-low`.
- MQTT mimic QA green (30/30): `cats/screenshots/mimic_qa/run_native_sml_qa.py` — covers 100/102, 110, 111a, 114/115, K-1/K-2, A48 balloon occupancy, 117/117b, incl. diverging **Medium Clear** (R/G) and 3-aspect **Clear** chaining. Notes: `cats/screenshots/mimic_qa/native_sml_qa_notes.md`; runtime criteria dump: `jmri/layouts/hart/scripts/dump_sml_criteria.py`.
- **CATS "blank windows" bug fixed (2026-08-18)**: unpainted System Console / clock / WiThrottle windows were CATS `Screen.init` dying on the Swing EDT at panel load, not LogixNG. Two causes, both fixed: (1) K-1/K-2 boundary sections (43,6)/(43,7) had anonymous `<BLOCK />` edges → `ClassCastException` in `discoverAdvanceVitalLogic`; now named `OS 115 (Princess)`/`OS 114 (Princess)` in all four Masters. (2) drive-mode templates requested `Restricting`, which `hart-aar` masts don't define → `IllegalArgumentException`; `aar_aspect_bridge.py` now maps RES_\*→Stop and R283/R286→Medium Clear/Medium Approach (CATS lamps paint the diverging pair). Verified: CATS ABS loads clean on the Pi, all windows paint.
- **Held ownership (2026-08-18)**: `unhold_signal_masts.py` retired (removed from Mac/Pi profiles, sync, and installers). Masts boot Unheld, so SML runs ABS by default with no script; **Held is CATS CTC's channel**. Verified live on the Pi: CTC load holds all 25 masts at Stop; left-click entrance (`Princess West OS 113b`) → CATS unholds, SML posts Approach, MQTT head goes Yellow; click again → re-held, Stop, Red.

## Dispatcher System (2026-08-18) — set up, awaiting live test

- JMRI **Dispatcher System** (`jython/DispatcherSystem`, [help](https://www.jmri.org/help/en/html/scripthelp/DispatcherSystem/DispatcherSystem.shtml)) Stage 1+2 run on the Pi against `tables.xml` (replaces last session's hand-built transit). Stations = blocks with `stop` in the comment: **West Main Ext, McKees Rocks, McKeesport**. Generated: station buttons/icons on My Layout, a "Dispatcher System" command panel, 41 sections, 12 transits, 24 traininfo files (fwd+rvs per pair), and a `Run Dispatcher` Logix (`IX:DSLX:1`) that starts the run threads from the panel button.
- **SML survived regeneration**: Stage 1 deletes + re-discovers; result matched our 34 discovered pairs, and the 2 manual K-stub pairs (`113a→K-2`, `113b→K-1`) were re-added — 36 total, verified after restart.
- **Train detection**: DispatcherSystem hardcodes Entire Train (`setResistanceWheels(True)`) into every traininfo it generates — this is why it "kept getting overwritten". Fixed to `TRAINDETECTION_HEADANDTAIL` by `jmri/layouts/hart/scripts/fix_traininfo_detection.py`; **rerun it after any Stage 1 rerun**.
- **2091 speed profile**: synthesized linear profile (10 steps, 400 mm/s at full) written into the Pi roster via the JMRI API — required by the system (registration lists only speed-profiled locos, traininfo uses `usespeedprofile=yes`). Replace with a measured profile (Roster ▸ Speed Profiling) for accurate station stops.
- Dispatcher options: `autoturnouts=yes` + `useturnoutconnectiondelay=yes` added (Stage 2 requirements); rest already correct (`usesignaltype=signalmast`, roster trains, auto-allocate, HO scale).
- Cleanups en route: K-1/K-2 block lengths set (609.6 mm); en-dashes removed from `Yard T6` comment and the `Main West Brick-Plane` block name (DispatcherSystem scripts crash on non-ASCII).
- **To test (layout on)**: launch PanelPro (not CATS) on the Pi → Dispatcher System panel ▸ *Run Dispatcher System* ▸ OK → place 2091 at a station ▸ *Setup Train in Section* (pick block, train, facing) → *Run Dispatch* ▸ click destination station button. *Simulate Dispatched Trains* dry-runs without hardware.
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
