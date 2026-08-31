# Class-F ingest plan (P4a approved)

**Status:** Consolidation draft only — **no live `docs/` writes** until promotion  
**Decision:** P4a=Y in [`DECISIONS_RECORDED.md`](../DECISIONS_RECORDED.md)  
**Manifest (2026-08-31):** [`sor/desktop/class_f_ingest_manifest.csv`](../sor/desktop/class_f_ingest_manifest.csv) — 124 rows, 54 flagged for human review. Regenerate: `python3 consolidation/scripts/classify_f_ingest.py`

---

## Principles

1. **Selective** — not a bulk copy of Desktop root.
2. **Exclude installers** — `.dmg`, large binaries stay off git.
3. **Prefer dedupe** — skip files whose hash already exists under `Car Cards/` (class E) or `docs/` (class A).
4. **LFS for large media** — PNG/JPG/PDF over ~1 MB → `docs/archive/` with LFS policy TBD at promotion.

---

## Target buckets (live paths after promotion)

| Bucket | Live path | Contents |
|--------|-----------|----------|
| **F-narrative** | `docs/archive/narrative/` | Timetables, narrative docx, historical writeups |
| **F-media** | `docs/archive/media/` | Layout photos, track schemes, operator logos not in Car Cards |
| **F-reference** | `docs/archive/reference/` | USGS/Google map captures, external PDFs |
| **F-skip** | — | Installers, duplicates, unknown one-offs |

Taxonomy reference: [`wiki/archive/INDEX.md`](../wiki/archive/INDEX.md)

---

## Phase 1 — auto-classify (script to add at promotion)

Extend `inventory_desktop_hart.py` or add `classify_f_ingest.py`:

| Rule | Bucket |
|------|--------|
| Extension `.dmg`, `.pkg`, `.exe` | **F-skip** |
| Basename matches class D list | **F-skip** (already in Car Cards/docs) |
| SHA256 matches class E | **F-skip** |
| `.docx`, `.pdf`, `.pptx`, `.xlsx` (non-D) | **F-narrative** |
| `.png`, `.jpg`, `.webp`, `.gif` | **F-media** |
| Name contains `USGS`, `Google Maps`, `topo` | **F-reference** |

Output: `sor/desktop/class_f_ingest_manifest.csv` with columns `path,bucket,action,notes`.

---

## Phase 2 — human review (before copy)

Review manifest rows where:

- Filename is generic (`IMG_*.jpg`, `s-l960.webp`)
- Size > 10 MB
- Unknown extension

Owner approves manifest; agent/operator runs copy only on approved rows.

---

## Phase 3 — promote to live (explicit user command)

```bash
# Example — not run until "promote archive ingest"
mkdir -p docs/archive/{narrative,media,reference}
# rsync or cp from manifest approved rows only
git lfs track "docs/archive/media/**"
```

Update [`wiki/archive/INDEX.md`](../wiki/archive/INDEX.md) with ingest date and row counts.

---

## Sample classifications (first 20 from inventory)

| File | Proposed bucket |
|------|-----------------|
| `1956-07-07PWV27-seabass.pdf` | F-reference |
| `1VFNT00010012.jpg` | F-media |
| `2022-10-16 *Google Maps*.png` | F-reference |
| `2022-10-16 *USGS*.png` | F-reference |
| `ammonium sulphate.png` | F-media |
| `basic_schematic.pptx` | F-narrative |
| `ChartiersTrackScheme.jpg` | F-media |
| `Coke_Ovens.dmg` | **F-skip** |
| `flannery-*.jpg` | F-media |

Full 124 rows remain in CSV until classify script runs.

---

## Dependencies

| Item | Status |
|------|--------|
| P4a decision | **Approved** |
| hart-ops migration (P3a) | Approved — independent; F ingest goes to **hart** `docs/archive/` |
| P3b submodules | Deferred — no blocker |

---

## Not in scope

- Class C subtree moves (hart-ops migration)
- Wiring Documentation bench mirror (D4)
- DJ Trains folder (model collection — separate review)
