# ADR-005 — Public equipment names (switch / signal / track)

- **Status:** Accepted (rename executed 2026-08-21; SML re-discover still pending live PanelPro)
- **Date:** 2026-08-20
- **Deciders:** lnevo
- **Amends:** [ADR-002](ADR-002-naming-contract.md) — **Barn** is Switch 117 / 117b; **West Yard** is the yard at Brick; signal names are numbers; T1/T6/T9 are retired; Engine House 1/2/3 top-to-bottom

## Context

Public names grew as geographic sentences (`West Yard West East Main Ext`) because West Yard was the first CATS plant drawn well. Switch numbers 100–119 are already the railroad. Occupancy sensors (`Block 4-2`) and MQTT system names (`M2T408`, `IH438`) are hardware and must stay.

## Decision — one grammar

| Kind | Pattern | Example |
|------|---------|---------|
| Switch | `Switch <n>` | `Switch 100` |
| OS block | `OS <n>[a\|b] (<CP>)` | `OS 117b (Barn)` |
| Track body | `<Name>` | `South Yard Scale`, `South Yard West` |
| Main between CPs | `<Track> <west>–<east>` | `Main West Brick–Plane` |
| Yard track | `<Yard> <n>` | `West Yard 1`, `South Yard 3` |
| Stub | letter-number | `K-1`, `K-2` |
| Signal mast | `<n><L\|R>[A\|B]` | `117LA`, `100L` |
| Signal head | mast, or mast + ` Top` / ` Bottom` | `100L Top` |

**L** = westbound (USS signal lever Left). **R** = eastbound (Right).  
**A/B** only when that lever lists two masts. A = first / through or upper track; B = second / diverging or lower.  
One mast on that lever: no letter (`100L`, `111L`, `110R`).

### Control points (public)

| CP | Switches |
|----|----------|
| Brick | 100, 101 |
| Plane | 102 |
| **Barn** | 117, 117b |
| South Yard | 103, 104, 105, 106 |
| East End | 107, 108, 109, 110, 111, 112 |
| Princess | 113, 114, 115 |

**West Yard** is the yard at Brick: **West Yard 1** and **West Yard 2** (plates W-1 / W-2), access via **Switch 101**.

Hand-throw in the field today: **116, 117, 118, 119**. **107–109 are not hand-throw.**

### South Yard Scale / West / run-through / East

T1 / T6 / East Lead were scaffold names. The three lead bodies belong to South Yard.

| Territory | Limits | Public name |
|-----------|--------|-------------|
| **Scale** | Plane (102, diverging) to 117 | `South Yard Scale` |
| **South Yard West** | 117 to 116 (west of 103) | `South Yard West` |
| **Run-through** | **East of 103** to **110 / 112** | `South Yard 1` |
| **South Yard East** | **East of 110 / 112** toward Princess | `South Yard East` |

| Circuit | Today | Public |
|---------|-------|--------|
| Block 4-8 | Yard T1 | `South Yard Scale` |
| Block 13-3 | OS 117 (West Yard) | `OS 117 (Barn)` |
| Block 13-1 | Yard T6 | `South Yard West` |
| Block 3-1 | OS 116 (West Yard) | `OS 116` |
| Block 13-2 | OS 118 (West Yard) | `OS 118` (MQTT 1301) |
| Block 13-8 | OS 119 (West Yard) | `OS 119` (MQTT 1307) |
| Block 3-2 | OS 103 (South Yard) | `OS 103 (South Yard)` |
| Block 2-8 | Yard Track 1 | `South Yard 1` (run-through to 110/112) |
| Block 1-7 | East Lead | `South Yard East` |

### Engine House — 1 / 2 / 3 top to bottom

Public names stay **Engine House 1 / 2 / 3** = **Yard T9 / T10 / T11**. CATS `ET-*` is not used to number the house.

Occupancy ids are MQTT (`1300` = Block 13-1). House tracks are **1304 / 1305 / 1306**. Switch 118 is **1301**; Switch 119 is **1307**. LE already points those blocks at those sensors. Walk-down before convert.

| Circuit | Sensor | MQTT |
|---------|--------|------|
| South Yard West (T6) | Block 13-1 | M2S1300 |
| Switch 118 | Block 13-2 | M2S1301 |
| OS 117 | Block 13-3 | M2S1302 |
| OS 117b | Block 13-4 | M2S1303 |
| Engine House 1 | Block 13-5 | M2S1304 |
| Engine House 2 | Block 13-6 | M2S1305 |
| Engine House 3 | Block 13-7 | M2S1306 |
| Switch 119 | Block 13-8 | M2S1307 |

### Frozen (never rename)

MQTT system names (`M2T*`, `M2S*`), occupancy userNames (`Block 4-2`), FB userNames (`Switch 4-1 FB N` — node/port, not switch 4), signal-head systemNames (`IH438`), mast systemNames (`IF$shsm:…`), CTC internals (`IS4:CB`). Optional: FB *comment* = `Switch 100`.

## Pre-convert baselines (captured 2026-08-20)

Do not treat these as live names after convert. Re-run capture and diff.

| Artifact | What it locks |
|----------|----------------|
| [`data/baselines/`](../../jmri/layouts/hart/data/baselines/) | Hardware ids, SML pairs (36), CTC SIDI (12) / TRL (40), LE mast bindings (23), block→sensor, CATS bindings |
| `capture_public_name_baseline.py` | Re-snapshot from `output/tables.xml` |
| `validate_le_signalling.py --xml output/tables.xml --dests --compare-stored` | 36 dests; 2 manual Princess balloon pairs |
| `audit_panel_contracts.py` | working / deployment / standalone drift = 0 |
| `check_hart_phase02.py` | Phase 0–2 (still requires old `OS 117b (West Yard)` until convert) |
| `validate_cats_panel.py` | Live masters PASS; stale `HART.xml` / `_le` / `_designer_wired` fail on `Main West Brick–Plane` en-dash — known, not a convert gate |

After convert: `systemName` columns identical; public strings follow the CSV; occupancy `Block N-N` unchanged.

## Mapping SoR

[`jmri/layouts/hart/data/public_name_map.csv`](../../jmri/layouts/hart/data/public_name_map.csv)

ADR-002’s `block_display_names.csv` is superseded for this pass.

## Attack (executed 2026-08-21)

Cutover from `public_name_map.csv` via `apply_public_names.py` (text-safe, longest-first). Hardware ids unchanged. Remaining live steps: walk-down node 13, PanelPro SML Discover, load + Run CTC Logic, deploy `--pi --win`. Do not change MQTT topics.

1. Walk-down node 13 (1301=118, 1304–1306=house, 1307=119). Freeze the CSV.  
2. `apply_public_names.py` for beans that have **no generator**: JMRI `userName` on blocks / masts / heads in `tables.xml`, plus CTC SIDI / TRL dest strings already stored there. Turnouts already match.  
3. For generated panels: **change the script, then regenerate** — do not string-replace the output. USS diagram = `gen_ctc_track_plan.py`. CATS Digicon = `wire_hart_sheet_west_yard2.py` then `build_hart_master_abs_hold.py`.  
4. Update look-up scripts and data CSVs (polish, validators, occupancy/signal CSVs) so they key on the new names.  
5. Re-discover SML (dests are mast userNames).  
6. `validate_le_signalling.py` + `check_hart_phase02.py` + `validate_cats_panel.py` + load PanelPro + Run CTC Logic.  
7. Deploy `--pi --win`. Do not change MQTT topics.

### Script / data inventory

**Missing — write at convert**

| Item | Job |
|------|-----|
| `jmri/layouts/hart/scripts/apply_public_names.py` | Read the CSV; replace `current` → `proposed` on JMRI `userName` only. Dry-run first. |

**Must update before any regenerate / re-wire (live)**

| Script | Hardcoded names |
|--------|-----------------|
| `gen_ctc_track_plan.py` | `SIGNALS` mast keys; lamp labels Yard T1 / T6 / Yard Track 1 / East Lead |
| `polish_hart_layout_editor.py` | Mast xy keys; `REMOVED_LABELS` includes `East Lead` |
| `cats/scripts/add_digicon_le_signal_icons.py` | Same mast keys as polish |
| `reconcile_dispatcher_stations.py` | Station `East Lead` + icon xy |
| `audit_panel_contracts.py` | `East Lead` stop contract |
| `annotate_mqtt_sensors_and_dispatcher.py` | Section graph / transit comments (`East Lead`, `OS 117b (West Yard)`) |
| `panelpro_smoke_test.py` | Station list `East Lead` |
| `jmri/scripts/check_hart_phase02.py` | Requires `OS 117b (West Yard)` |
| `build_ctc_full_15col.py` | SIDI mast lists (unsafe to re-run until updated) |
| `wire_hart_sheet_west_yard2.py` | CATS `BLOCK` / `SECSIGNAL` SoR |
| `apply_sml_cats_pairs.py` | SML pair + block dests |
| `validate_cats_panel.py` | Required `OS 116–119 (West Yard)` |
| `build_hart_signal_heads.py` | Mast userNames |
| `sim_hart_train_mqtt.py` | Route step block names |
| `lcos_mqtt_mimic.py` | Plant labels 116–119 = West Yard |
| `jmri_to_cats_digicon.py` | Block aliases |

**Data CSVs (same strings as XML)**

| File |
|------|
| `cats/data/occupancy_bindings.csv` |
| `cats/data/signal_mast_plan.csv` |
| `cats/data/signal_head_plan.csv` |
| `cats/data/signal_wiring.csv` |
| `cats/data/le_signal_boundaries.csv` |
| `cats/data/turnout_bindings.csv` |
| `cats/data/jmri_devices.csv` |
| `cats/data/plants_from_hart.csv` (still lists West Yard as a CP) |
| `jmri/layouts/hart/data/block_lengths.csv` |
| `jmri/layouts/hart/README.md` (still points at `block_display_names.csv`) |

**Guides after convert:** `jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md`, `cats/docs/DISPATCHER_GUIDE_CTC.md`, `jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md`. Other `cats/docs/*` as needed.

**One-shot — do not re-run; leave or comment-only**

`revert_barn_ladder_signals.py`, `build_ctc_brick_plane.py`, `build_ctc_east_end_princess.py`, `compose_hart_sheet_west_yard2_*.py`, `patch_ctc_locking.py` (TRL dests already new Princess names; comments only).

**Do not convert**

MQTT `M2T*` / `M2S*` / `IH*` / `IF$shsm`, occupancy sensor userNames (`Block 13-5`), FB userNames (`Switch 13-1 FB N`), CTC `IS*:`, `wiki/STATUS.md` history, `block_display_names.csv` (superseded). Station label **West Yard** on the CTC gold band stays (the yard, not a CP).

## Consequences

Dispatchers say “code 117 Reverse, 117 Left” and see **117LA** / **117LB**. Maintainers still find hardware as `Block 13-3` / `M2T1308` / `IH1337`.
