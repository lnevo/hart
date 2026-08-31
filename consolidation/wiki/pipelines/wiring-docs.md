> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only) | Consolidation draft |
|------|------------------|---------------------|
| Runbook | `wiki/pipelines/wiring-docs.md` | this file |
| Canonical pack | `docs/wiring/` (git) | `sor/wiring/` snapshots + crosswalk |
| Bench mirror | `~/Desktop/HART/Wiring Documentation/` | export-only (D4) |
| Wiring CSV | `cats/data/signal_wiring.csv` | remap table in `sor/wiring/packed_id_crosswalk.csv` |

**Decision D4:** git `docs/wiring/` is canonical; Desktop bench is export mirror.

---

# Pipeline 8 — Wiring documentation

Refresh LCOS inventory workbooks and the per-node PowerPoint from hart CSVs.

**Status:** Live.

## Inputs

- `cats/data/occupancy_bindings.csv`
- `cats/data/signal_wiring.csv`, `signal_head_plan.csv`, `signal_mast_plan.csv`
- `docs/wiring/imported/` snapshots
- `public_name_map.csv` (proposed strings)

## Outputs

- `docs/wiring/LCOS_Layout_Inventory_v85.xlsx`
- `docs/wiring/signals_asbuilt_abs_v2.xlsx`
- `docs/wiring/signals_split_v8.xlsx` (frozen RGB plan + notes)
- `docs/wiring/Wiring_Schematic.pptx`

## Run (live — promotion only)

```bash
python3 docs/wiring/scripts/refresh_wiring_docs.py
python3 docs/wiring/scripts/create_wiring_schematic_ppt.py
```

Copy workbooks + pptx to Desktop pack after XML apply so bench matches beans.

## Consolidation: wiring ↔ bean crosswalk

Ten wiring packed IDs and ten deploy IH IDs fail **naive** digit match (72% overlap). Mast-aware remap resolves **100%** — see [`audits/wiring-crosswalk-gap.md`](../../audits/wiring-crosswalk-gap.md).

```bash
python3 consolidation/scripts/build_wiring_crosswalk.py   # writes sor/wiring/packed_id_crosswalk.csv
python3 consolidation/validators/check_wiring_crosswalk.py
```

When `docs/wiring/` is next regenerated (explicit promotion), align `signal_wiring.csv` packed column to live IH or drop stale node×100 rows.

## Do not

- Edit live `docs/wiring/` from consolidation without promotion
- Treat Desktop `ARCHIVE/` one-off Python as the live generator
- Refresh Desktop before JMRI XML apply if the pack must match beans
- Put packed MQTT on helix **D5**

Detail: [`docs/wiring/README.md`](../../../docs/wiring/README.md)
