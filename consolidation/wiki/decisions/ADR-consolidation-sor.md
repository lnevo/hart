# ADR — Consolidation source of record

**Status:** Accepted (consolidation) · 2026-08-31  
**Locks:** D2, D4 · [`DECISIONS_RECORDED.md`](../../DECISIONS_RECORDED.md)

## Principle

One canonical file per **fact type**. Generators read SoR; humans do not hand-edit generated XML/XLSX.

## Live vs consolidation

| Fact type | Live SoR (read-only) | Consolidation draft |
|-----------|---------------------|---------------------|
| Public identity map | `jmri/layouts/hart/data/public_name_map.csv` | `sor/names/public_name_map_merged.csv` (D2b) |
| Legacy name index | `block_display_names.csv` | retire on promotion (D2a) |
| Writable tables | `tables/new_tables.xml` | documented chain only |
| Deploy bundle | `jmri/layouts/hart/output/tables.xml` | never hand-edit |
| Digicon wiring | `cats/data/signal_wiring.csv` | `sor/wiring/packed_id_crosswalk.csv` |
| Wiring pack | `docs/wiring/` (git) | `sor/wiring/` snapshots |
| CATS live desk | `cats/panels/HART_Master_*_hold.xml` | regenerate via scripts only |
| Desktop ops | `~/Desktop/HART/` subtrees | `sor/desktop/hart_root_inventory.csv` |

## Bench copies (not SoR)

| Path | Role |
|------|------|
| `~/Desktop/HART/Wiring Documentation/` | export mirror (D4) |
| `~/Desktop/HART/Car Cards/` | Tier C ops — future `hart-ops` (P3 pending) |
| `~/Desktop/HART/Industries/` | Tier C matrix |

Detail: [`audits/desktop-inventory.md`](../../audits/desktop-inventory.md)
