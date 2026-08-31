# Central source of record — consolidation workspace

**Principle:** One canonical artifact per fact type in the **new tree**. Live and Desktop paths are read-only references until explicit promotion (future).

**Registry:** [`manifest.yaml`](../manifest.yaml) · **ADR:** [`wiki/decisions/ADR-consolidation-sor.md`](../wiki/decisions/ADR-consolidation-sor.md)

---

## Authority map (consolidation tree)

| Fact type | Consolidation SoR | Live reference (read-only) | Pipeline |
|-----------|-------------------|---------------------------|----------|
| Public identity map | `sor/names/public_name_map_merged.csv` | `jmri/.../public_name_map.csv` | 2 |
| Legacy name index (retire) | `sor/names/block_display_names.csv` snapshot | live CSV | 2 |
| Digicon wiring catalog | `sor/signals/signal_wiring.csv` | `cats/data/signal_wiring.csv` | 3 |
| Signal head plan | `sor/signals/signal_head_plan.csv` | `cats/data/signal_head_plan.csv` | 3 |
| Signal mast plan | `sor/signals/signal_mast_plan.csv` | `cats/data/signal_mast_plan.csv` | 3 |
| Wiring ↔ bean crosswalk | `sor/wiring/packed_id_crosswalk.csv` | derived | 3, 8 |
| LE signal boundaries | `sor/signals/le_signal_boundaries.csv` | `cats/data/le_signal_boundaries.csv` | 4 |
| Occupancy bindings | `sor/signals/occupancy_bindings.csv` | `cats/data/occupancy_bindings.csv` | 8 |
| CATS device map | `sor/cats/jmri_devices.csv` | `cats/data/jmri_devices.csv` | 5 |
| Writable tables chain | `sor/tables/README.md` + live XML refs | `tables/new_tables.xml` | cross |
| Deploy tables bundle | read-only ref | `jmri/.../output/tables.xml` | cross |
| Wiring xlsx pack | `sor/wiring/LCOS_Layout_Inventory_v85.xlsx` snapshot | `docs/wiring/` | 8 |
| Car inventory | `external/hart-ops/data/image_metadata.csv` | Desktop Car Cards | 12 |
| Merged roster | `external/hart-ops/data/HART_MergedCarRoster.xml` | generated | 12 |
| Waybills | `external/hart-ops/data/HART_Spot_Waybills.csv` | hart-ops | 13 |
| Publications scripts + output | `external/hart-ops/publications/`, `docs/published/` | hart-ops | 15 |
| Industry matrix | `external/hart-ops/industries/` | hart-ops | 16 |
| LCOS firmware | `external/lcos-bridge/` | sibling repo | 9 |
| STS runtime | `external/sts-docker/` + `external/sts-docker-data/` | sibling + `~/sts/*` | 14 |
| STS helpers | `external/sts-helpers/` | sibling repo | 14 |
| Layout ops mirror | `external/hart-runtime/` | `hart/` repo | cross |
| Desktop bench mirror | `external/desktop-data/` | `~/Desktop/HART/` | cross |
| Desktop root inventory | `sor/desktop/hart_root_inventory.csv` | `~/Desktop/HART/` | P4 |
| Desktop subtree inventory | `sor/desktop/hart_subtree_inventory.csv` | class C dirs | P4 |
| Class-F dispositions | `sor/desktop/class_f_ingest_manifest.csv` | F-root browse | P4 |

---

## Generated artifacts (never hand-edit)

| Artifact | Generator | Pipeline |
|----------|-----------|----------|
| `tables/new_tables.xml` | names, beans, SML scripts | 2–4 |
| `output/tables.xml` | section sync, CTC regen | cross, 6 |
| `HART_Master_*_hold.xml` | CATS build scripts | 5 |
| `ctc/GUIObjects.xml` | `gen_ctc_track_plan.py` | 6 |
| `dispatcher/traininfo/*` | Dispatcher Stage 1 | 7 |
| `OperationsCarRoster.xml` | hart-ops export | 12 |
| Published docx/pdf | hart-ops `publications/rebuild_*.py` | 15 |

---

## Not SoR (reference / parked / excluded)

| Item | Status |
|------|--------|
| Pipeline 1 AnyRail | **Frozen** — not live path for hart |
| Pipeline 11 speed matching | **Parked** — synthetic profiles |
| `tables/tables.xml` | Legacy snapshot — never edit |
| `~/Desktop/HART/` bulk | Inventory + browse only; future promotion manifests in [`cutover/`](../cutover/) (reference archive) |
| Car final photos (~GB) | Local path / LFS — not in git |
| LCOS BOM (D8) | Excluded |
| Gate 1 `HART.xml` CATS panels | History — not ops desk |

---

## Refresh snapshots

```bash
python3 consolidation/scripts/snapshot_live_sor.py
python3 consolidation/scripts/inventory_desktop_hart.py
python3 consolidation/scripts/inventory_desktop_subtrees.py
python3 consolidation/scripts/classify_f_ingest.py
```
