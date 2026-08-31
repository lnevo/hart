> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only) | Consolidation draft |
|------|------------------|---------------------|
| Runbook | `wiki/pipelines/public-names.md` | this file |
| **Apply map (SoR)** | `jmri/layouts/hart/data/public_name_map.csv` | `sor/names/public_name_map_merged.csv` (D2b notes) |
| Legacy index | `jmri/layouts/hart/data/block_display_names.csv` | `sor/names/block_display_names.csv` snapshot — **retire on promotion (D2a)** |
| ADR | `wiki/decisions/ADR-005-public-equipment-names.md` | `wiki/decisions/ADR-names-single-sor.md` |

**Decision D2:** single authority = **`public_name_map.csv`**. Generator order unchanged.

---

# Pipeline 2 — Public names + comments

Apply the live naming grammar to JMRI beans and generated panels. Hardware MQTT `systemName`s stay frozen (`M2T*`, `M2S*`, `IH*`, `IS*:`, `ISNX:*`). LCC turnout aliases `MTT100`–`MTT119` are required twins.

**Status:** Live. [ADR-005](../../../wiki/decisions/ADR-005-public-equipment-names.md) · consolidation [ADR-names-single-sor](../decisions/ADR-names-single-sor.md).

## Inputs

- [`public_name_map.csv`](../../../jmri/layouts/hart/data/public_name_map.csv) — Device Map identity, `proposed` renames, hardware IDs, comments
- Device-map comments (node / OU / ports / `DCC: NNN`)
- Legacy: `block_display_names.csv` — still read by live `check_hart_phase02.py` until D2 promotes

## Outputs

- `userName` on turnouts, sensors, blocks, heads, masts in `tables/new_tables.xml` and hart `output/`
- Occupancy comments `Block n-n`; wiring comments on hardware beans
- Names baked into USS / CATS **after regenerate**, not by string-replace of generated XML

## Run (live — promotion only)

```bash
export JMRI_LAYOUT=hart
python3 jmri/layouts/hart/scripts/sync_public_name_map.py
python3 jmri/layouts/hart/scripts/apply_public_names.py          # dry-run first
python3 jmri/layouts/hart/scripts/apply_public_names.py --apply
python3 jmri/layouts/hart/scripts/refresh_bean_comments.py --apply
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
```

Beans **with a generator** (USS diagram, CATS Masters, signal heads): change the script or CSV, then regenerate. Do not search-replace generated XML.

## Consolidation validators (read-only)

| Check | Script |
|-------|--------|
| OS names derivable from map | `scripts/propose_os_from_map.py` |
| phase02 with map-derived OS | `scripts/check_hart_phase02_from_map.py` |
| Names snapshot diff | `validators/check_names_diff.py` |

Writable tables only: `tables/new_tables.xml` (never `tables/tables.xml`).

## Do not

- Change MQTT topics or `systemName`s
- Put leftover Switch 100–119 in public names
- Add one-off deletes to `cleanup_uss_ctc_leftovers.py` as a forever list (see `unused-modules/`)
