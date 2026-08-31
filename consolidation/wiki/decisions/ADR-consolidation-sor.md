# ADR — Consolidation source of record (draft)

**Status:** Draft — pending D2, D4 in [`DECISIONS_PENDING.md`](../../DECISIONS_PENDING.md).

## Principle

One canonical file per **fact type**. Generators read SoR; humans do not hand-edit generated XML/XLSX.

## Live vs consolidation

| Fact type | Live SoR (read-only) | Consolidation proposed |
|-----------|---------------------|------------------------|
| Public identity map | `jmri/layouts/hart/data/public_name_map.csv` | `sor/names/public_name_map.csv` |
| ~~Live name index~~ | ~~`block_display_names.csv`~~ **legacy (D2)** | migrate into map; retire on promotion |
| Writable tables | `tables/new_tables.xml` | Document only until promotion |
| Deploy bundle | `jmri/layouts/hart/output/tables.xml` | Never hand-edit |
| Digicon wiring catalog | `cats/data/signal_wiring.csv` | Snapshot in audits |
| Wiring pack | `docs/wiring/` | `sor/wiring/` drafts |
| CATS live desk | `cats/panels/HART_Master_*_hold.xml` | Regenerate only via scripts |

## Bench copies

- `~/Desktop/HART/Wiring Documentation/` — export mirror, not SoR
- `~/Desktop/HART/Car Cards/` — ops tooling (deferred tier C)
