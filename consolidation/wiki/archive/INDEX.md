# Archive taxonomy — Desktop/HART (draft)

**Status:** Consolidation draft · **P4a approved** — selective ingest plan ready; not executed until promotion  
**Inventory:** [`audits/desktop-inventory.md`](../../audits/desktop-inventory.md) · CSV: [`sor/desktop/hart_root_inventory.csv`](../../sor/desktop/hart_root_inventory.csv)  
**Ingest plan:** [`audits/class-f-ingest-plan.md`](../../audits/class-f-ingest-plan.md)

## Classes (extended)

| Class | Meaning | Action (when approved) |
|-------|---------|------------------------|
| **A** | Already in `hart` git (`docs/`, `jmri/`, `cats/`, …) | None — canonical |
| **B** | Sibling git repo (`LCOS_ESP32_MQTT_Client`, `sts-docker`, future `hart-ops`) | Submodule under `consolidation/external/` (P3b) |
| **C** | Operational subtree on Desktop | Migrate to `hart-ops` or documented path (P3a) |
| **D** | Root duplicate basename of `Car Cards/docs/` | Delete Desktop copy after confirming git/hart-ops SoR |
| **E** | Root duplicate hash of file under Car Cards | Same as D |
| **F** | Root narrative, media, installers, misc | Selective ingest → `docs/archive/` (P4a) |

## Class C — subtrees (2026-08-31 scan)

| Path | Files | Size | Future home |
|------|------:|-----:|-------------|
| `Car Cards/` | 30,695 | ~3.3 GB | **hart-ops** (pipelines 12–15) |
| `Wiring Documentation/` | 2,288 | ~57 MB | bench mirror of `docs/wiring/` (D4) |
| `Industries/` | 8 | ~1 MB | **hart-ops** (pipeline 16) |
| `DJ Trains/` | 14 | ~43 MB | review — model collection, not layout SoR |

## Class D — root duplicates (safe to dedupe after SoR move)

- `HART Railroad Scale Operating Instructions.docx`
- `Neville_Island_Dispatcher_Train_List.docx`
- `Neville_Island_Yardmaster_Sequence.docx`
- `TT-23_Route23_NevilleQueen_RevisionA_v6.pptx`

Published SoR: `Car Cards/docs/` via pipeline 15 rebuild scripts.

## Class F — ingest buckets (proposed, not executed)

| Bucket | Examples | Proposed git home |
|--------|----------|-------------------|
| **F-narrative** | `HART_Railroad_Narrative_Updated.docx`, timetables | `docs/archive/narrative/` |
| **F-media** | `IMG_894*.png`, track schemes | `docs/archive/media/` + LFS policy TBD |
| **F-reference** | USGS/Google map PNGs, historical PDFs | `docs/archive/reference/` |
| **F-installer** | `Coke_Ovens.dmg` | do not ingest — keep off git |

**124** class-F root files — full list in CSV. Regenerate: `python3 consolidation/scripts/inventory_desktop_hart.py`

## Slim Desktop target (cutover project — not now)

Per D12 bench freeze, **do not modify** `~/Desktop/HART/` during consolidation. Target state for later:

```
~/Desktop/HART/
  README.md          ← links to hart git, hart-ops, sts, wiring bench sync
  Car Cards/         ← symlink or removed after hart-ops migration
  Wiring Documentation/  ← export mirror only
```

**P3a/P4a approved** — ingest and Desktop changes deferred to **cutover project**. No live `docs/` writes during consolidation.
