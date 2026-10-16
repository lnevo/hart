# Archive taxonomy — Desktop/HART (draft)

**Status:** Consolidation draft — inventory and browse only; no files moved (D12)  
**F-root browse:** [`html/archive/f-root-index.html`](../../html/archive/f-root-index.html) — **124 files** with skip / browse / archive dispositions  
**Inventory:** [`audits/desktop-inventory.md`](../../audits/desktop-inventory.md) · CSV: [`sor/desktop/hart_root_inventory.csv`](../../sor/desktop/hart_root_inventory.csv)  
**Manifest:** [`sor/desktop/class_f_ingest_manifest.csv`](../../sor/desktop/class_f_ingest_manifest.csv) · Regenerate: `python3 consolidation/scripts/classify_f_ingest.py`  
**Ingest plan:** [`audits/class-f-ingest-plan.md`](../../audits/class-f-ingest-plan.md)

## Classes (extended)

| Class | Meaning | Consolidation action |
|-------|---------|----------------------|
| **A** | Already in `hart` git (`docs/`, `jmri/`, `cats/`, …) | None — canonical in live repo today |
| **B** | Sibling git repo (`LCOS_ESP32_MQTT_Client`, `sts-docker`, `hart-ops`) | Submodule under `consolidation/external/` |
| **C** | Operational subtree on Desktop | Target: `hart-ops` or documented path |
| **D** | Root duplicate basename of `Car Cards/docs/` | Dedupe after hart-ops SoR verified |
| **E** | Root duplicate hash of file under Car Cards | Same as D |
| **F** | Root narrative, media, installers, misc | Browse in portal; archive bucket for later history project |

## Class F dispositions (owner 2026-08-31)

| Disposition | Count | Meaning |
|-------------|------:|---------|
| **browse** | 33 | Screenshots, downloads — sort in [F-root browse](../../html/archive/f-root-index.html) |
| **archive** | 68 | `HART_*` narrative, design PDFs, prototype media — history project later |
| **skip** | 23 | dmg, Thumbs.db, layout photo series, wiring schematics |

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

Published SoR: `hart-ops` publications via pipeline 15 rebuild scripts.

## Slim Desktop target (future — not now)

Per D12, **do not modify** `~/Desktop/HART/` during consolidation build.
