# ADR-005 — Public equipment names (switch / signal / track)

- **Status:** Accepted (CTC-number convert + SML Discover + NX Discover 2026-08-27)
- **Date:** 2026-08-20
- **Deciders:** lnevo
- **Amends:** [ADR-002](ADR-002-naming-contract.md) — **Barn** is Switch 7 / 7b; **West Yard** is the yard at Brick; signal names are numbers with `Mast`/`Head` prefixes; plates **W-1 / W-2**, **S-R** (run-through) and **S-1…S-4**, **EH-1 / EH-2 / EH-3**

## Context

Public names grew as geographic sentences (`West Yard West East Main Ext`) because West Yard was the first CATS plant drawn well. Switch numbers 100–119 are already the railroad. MQTT system names (`M2T408`, `IH438`) are hardware and must stay.

## Decision — one grammar

| Kind | Pattern | Example |
|------|---------|---------|
| Switch | `Switch <n>` | `Switch 1` (CTC odd; DCC stays old number in comment) |
| OS block | `OS <n>[a\|b]` (CP in the bean comment) | `OS 7b` |
| Track body | `OS <Name>` | `OS Scale`, `OS S-R` |
| Occupancy sensor | `BS …` (comment stays `Block n-n`) | `BS Switch 3`, `BS S-R` |
| Main between CPs | `OS <west>–<east>` | `OS Brick-Plane` |
| Yard track | `OS` + plate | `OS W-1`, `OS S-3`, `OS EH-1` |
| Stub | `OS` + letter-number | `OS K-1` |
| Signal mast | `Mast <n><L\|R>[A\|B]` or `Mast` + 4-digit field | `Mast 8LA`, `Mast 2L`, `Mast 2035` |
| Signal head | `Head` + mast, or + ` Top` / ` Bottom` | `Head 2L Top`, `Head 2035` |
| Feedback | `FB Switch <n> N\|R` | `FB Switch 1 N` |

**L** = westbound (USS signal lever Left). **R** = eastbound (Right).  
**A/B** only when that lever lists two masts.  
Princess balloon intermediates: field **2035** (was 120L) and **2036** (was 120R).

## Live inventory (2026-08-27)

CTC-number convert applied to `output/tables.xml` / `hart_prod.xml`. Live userNames match the device-map grammar (`Switch 1`, `Mast 2L`, `OS S-R`, `BS McKees Rocks`, `Mast 2035`/`Mast 2036`). Occupancy lookups (`occupancysensor`, LE/USS jewels) use `BS …`; comments keep `Block n-n`. Dispatcher MoveTo sensors are `MoveToOS_<station>_stored`. MQTT `systemName`s and `ISNX:*` unchanged. Native SML re-Discovered 2026-08-27 (**33 sources / 93 dests**). NX re-Discovered same day (**39 pairs**, SML mode). CTC Logic smoke: 12 columns / 23 SIDI masts.

## Pre-convert baselines (2026-08-20 snapshot is git history)

Live recapture is **2026-08-26**. The 2026-08-20 files locked pre-ADR-005 names; do not treat them as live.

| Artifact | What it locks |
|----------|----------------|
| [`data/baselines/`](../../jmri/layouts/hart/data/baselines/) | Hardware ids, SML pairs, CTC SIDI/TRL, LE mast bindings, block→sensor, CATS bindings (live names) |
| `capture_public_name_baseline.py` | Re-snapshot from `output/tables.xml` + live CATS CTC hold |
| `validate_le_signalling.py --xml output/tables.xml --dests --compare-stored` | native SML dests vs stored |
| `audit_panel_contracts.py` | working / deployment / standalone drift = 0 |
| `check_hart_phase02.py` | Phase 0–2 (public names are live `OS 7b`, not `OS 7b`) |
| `validate_cats_panel.py` | Live masters PASS |

After a rename: `systemName` columns identical; public strings follow the CSV `proposed`; occupancy `Block N-N` unchanged.

## Mapping SoR

[`jmri/layouts/hart/data/public_name_map.csv`](../../jmri/layouts/hart/data/public_name_map.csv)

For the next pass: edit **`proposed`** on the live identity rows; leave historical alias rows pointing at the same `proposed`. ADR-002’s `block_display_names.csv` is a live-name index, not the apply map.

## Attack (executed 2026-08-21)

Cutover from `public_name_map.csv` via `apply_public_names.py` (text-safe, longest-first). Hardware ids unchanged. CTC-number convert + SML Discover + NX Discover + CTC Logic smoke + `--pi --win` done 2026-08-27. Optional later: node 13 occupancy walk-down. Do not change MQTT topics.

1. Walk-down node 13 (1301=118, 1304–1306=house, 1307=119). Freeze the CSV.  
2. `apply_public_names.py` for beans that have **no generator**: JMRI `userName` on blocks / masts / heads in `tables.xml`, plus CTC SIDI / TRL dest strings already stored there. Turnouts already match.  
3. For generated panels: **change the script, then regenerate** — do not string-replace the output. USS diagram = `gen_ctc_track_plan.py`. CATS Digicon = `wire_hart_master4.py` then `build_hart_master_abs_hold.py`.  
4. Update look-up scripts and data CSVs (polish, validators, occupancy/signal CSVs) so they key on the new names.  
5. Re-discover SML (dests are mast userNames) and NX (`run_nx_discover.sh`; `ISNX:*` stays frozen).  
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
| `gen_ctc_track_plan.py` | `SIGNALS` mast keys; lamp labels OS Scale / T6 / OS S-R / OS East Lead |
| `polish_hart_layout_editor.py` | Mast xy keys; `REMOVED_LABELS` includes `OS East Lead` |
| `cats/scripts/add_digicon_le_signal_icons.py` | Same mast keys as polish |
| `reconcile_dispatcher_stations.py` | Station `OS East Lead` + icon xy |
| `audit_panel_contracts.py` | `OS East Lead` stop contract |
| `annotate_mqtt_sensors_and_dispatcher.py` | Section graph / transit comments (`OS East Lead`, `OS 7b`) |
| `panelpro_smoke_test.py` | Station list `OS East Lead` |
| `jmri/scripts/check_hart_phase02.py` | Requires `OS 7b` |
| `build_ctc_full_15col.py` | SIDI mast lists (unsafe to re-run until updated) |
| `wire_hart_master4.py` | CATS `BLOCK` / `SECSIGNAL` SoR |
| `apply_sml_cats_pairs.py` | SML pair + block dests |
| `validate_cats_panel.py` | Required `OS 13–119 (West Yard)` |
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
| `cats/data/plants_from_hart.csv` |
| `jmri/layouts/hart/data/block_lengths.csv` |
| `jmri/layouts/hart/README.md` |

**Guides after convert:** `jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md`, `cats/docs/DISPATCHER_GUIDE_CTC.md`, `jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md`. Other `cats/docs/*` as needed.

**One-shot — do not re-run; leave or comment-only**

`revert_barn_ladder_signals.py`, `build_ctc_brick_plane.py`, `build_ctc_east_end_princess.py`, `compose_hart_sheet_west_yard2_*.py`, `patch_ctc_locking.py` (TRL dests already new Princess names; comments only).

**Do not convert**

MQTT `M2T*` / `M2S*` / `IH*` / `IF$shsm`, occupancy sensor userNames (`Block 13-5`), FB userNames (`Switch 13-1 FB N`), CTC `IS*:`, `wiki/STATUS.md` history. Station label **West Yard** on the CTC gold band stays (the yard, not a CP).

## Consequences

Dispatchers say “code 117 Reverse, 117 Left” and see **Mast 8LA** / **Mast 8LB**. Maintainers still find hardware as `Block 13-3` / `M2T1308` / `IH1337`.
