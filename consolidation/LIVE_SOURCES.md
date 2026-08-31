# LIVE_SOURCES — read-only reference map

**Do not edit these paths** as part of consolidation work. Validators and audits may **read** them only.

Pipeline index: live [`wiki/pipelines/README.md`](../wiki/pipelines/README.md) (16 flows; NextTrain abandoned).

Legend: **RO** = treat as read-only for consolidation; **W** = live writable (do not touch from consolidation).

---

## Core layout and tables

| Path | Role | Consolidation | Pipeline |
|------|------|---------------|----------|
| `jmri/layout_paths.py` | `JMRI_LAYOUT` path resolver | RO | infra |
| `jmri/layouts/hart/output/hart_prod.xml` | LE monitor artifact | RO | 1 |
| `jmri/layouts/hart/output/tables.xml` | Deploy bundle (LE+SML+CTC+Dispatcher) | RO | 2–7 |
| `tables/tables.xml` | Legacy tables snapshot | **RO — never edit** | — |
| `tables/new_tables.xml` | Writable working tables source | W (live only) | 2–7 |

---

## Pipeline 2 — Public names

| Path | Role | Consolidation |
|------|------|---------------|
| `jmri/layouts/hart/data/public_name_map.csv` | Apply / identity map | RO |
| `jmri/layouts/hart/data/block_display_names.csv` | Live name index | RO |
| `jmri/layouts/hart/scripts/apply_public_names.py` | Rename beans | RO |
| `jmri/layouts/hart/scripts/refresh_bean_comments.py` | Comments | RO |
| `jmri/layouts/hart/scripts/sync_public_name_map.py` | Sync map from device sheet | RO |
| `jmri/layouts/hart/scripts/audit_panel_contracts.py` | Contract audit | RO (invoke via validator) |
| `jmri/layouts/hart/scripts/cleanup_uss_ctc_leftovers.py` | USS/Digicon cleanup | RO |

---

## Pipeline 3 — Digicon signal beans

| Path | Role | Consolidation |
|------|------|---------------|
| `cats/data/signal_wiring.csv` | 3-pin head catalog | RO |
| `cats/data/signal_head_plan.csv` | Virtual head plan | RO |
| `cats/data/signal_mast_plan.csv` | Mast plan | RO |
| `cats/scripts/build_hart_signal_heads.py` | Generate IH/SHSM | RO |
| `cats/resources/signals/hart-aar/` | Appearance XML | RO |
| `jmri/scripts/mqtt_signalhead_publisher.py` | MQTT ↔ SML jython | RO |

---

## Pipeline 4 — Native SML + NX

| Path | Role | Consolidation |
|------|------|---------------|
| `cats/data/le_signal_boundaries.csv` | LE boundaries | RO |
| `cats/scripts/run_sml_discover.sh` | SML Discover wrapper | RO |
| `cats/scripts/disable_digicon_sml_in_tables.py` | Disable Digicon SML dests | RO |
| `cats/scripts/validate_le_signalling.py` | Post-discover validation | RO |

---

## Pipeline 5 — CATS Masters

| Path | Role | Consolidation |
|------|------|---------------|
| `cats/panels/HART_Master_CTC_hold.xml` | **Live CTC desk** | RO |
| `cats/panels/HART_Master_ABS_hold.xml` | **Live ABS desk** | RO |
| `cats/panels/HART_Master4.xml` | Master4 geometry | RO |
| `cats/scripts/wire_hart_master4.py` | Wire Master4 | RO |
| `cats/scripts/build_hart_master_ctc_hold.py` | Build CTC hold | RO |
| `cats/scripts/lcos_mqtt_mimic.py` | MQTT mimic QA | RO |
| `cats/scripts/sync_hart_package.sh` | Deploy to Pi/Win | RO |

---

## Pipeline 6 — USS CTC

| Path | Role | Consolidation |
|------|------|---------------|
| `jmri/layouts/hart/ctc/GUIObjects.xml` | USS track diagram | RO |
| `jmri/layouts/hart/scripts/gen_ctc_track_plan.py` | Generate CTC plan | RO |

---

## Pipeline 7 — Dispatcher System

| Path | Role | Consolidation |
|------|------|---------------|
| `jmri/layouts/hart/dispatcher/traininfo/` | Traininfo XML (~1508) | RO |
| `jmri/layouts/hart/scripts/hart_dispatcher_startup.py` | Jython startup | RO |
| `jmri/layouts/hart/scripts/patch_dispatcher_facing.py` | Facing overlay | RO |

---

## Pipeline 8 — Wiring

| Path | Role | Consolidation |
|------|------|---------------|
| `docs/wiring/LCOS_Layout_Inventory_v85.xlsx` | LCOS inventory | RO |
| `docs/wiring/scripts/refresh_wiring_docs.py` | Regenerate pack | RO |
| `~/Desktop/HART/Wiring Documentation/` | Bench mirror | RO (external) |

---

## Pipeline 9 — LCOS (sibling repo)

| Path | Role | Consolidation |
|------|------|---------------|
| `../LCOS_ESP32_MQTT_Client/serial_to_mqtt.py` | Host bridge | RO |
| `../LCOS_ESP32_MQTT_Client/lcos_mqtt_bridge.cpp` | Firmware bridge | RO |

---

## Pipelines 12–16 (deferred — external)

| Path | Role |
|------|------|
| `~/Desktop/HART/Car Cards/` | Car cards, waybills, publications scripts |
| `~/sts/sts-docker` | STS runtime |
| `~/Desktop/HART/Industries/` | Industry routing matrix |

---

## Live rules (from AGENTS / AI_CONTEXT)

1. Writable tables: **`tables/new_tables.xml` only**
2. Never run CATS CTC and USS CTC together
3. Do not store JMRI tables from a CATS session
4. hart geometry scale **1:1** — no `fit_panel_*` unless asked
5. Deploy gate: `audit_panel_contracts.py --strict` before ship
