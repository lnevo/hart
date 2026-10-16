# Class-F ingest plan (P4a)

**Status:** Consolidation draft — manifest and browse index built; **no files copied** (D12)  
**Decision:** P4a=Y in [`DECISIONS_RECORDED.md`](../DECISIONS_RECORDED.md)  
**Browse:** [`html/archive/f-root-index.html`](../html/archive/f-root-index.html)  
**Manifest:** [`sor/desktop/class_f_ingest_manifest.csv`](../sor/desktop/class_f_ingest_manifest.csv) — 124 rows  
**Regenerate:** `python3 consolidation/scripts/classify_f_ingest.py`

---

## Owner dispositions (2026-08-31)

| Disposition | Count | Rule |
|-------------|------:|------|
| **skip** | 23 | `Coke_Ovens.dmg`, `Thumbs.db`, `~$*`, IMG_894x–895x, wiring schematics, layout photos |
| **browse** | 33 | Screenshots, downloads, generic media — portal browse |
| **archive** | 68 | `HART_*` narrative, historical PDFs, named prototype media |

---

## Principles

1. **Selective** — not a bulk copy of Desktop root.
2. **Exclude installers** — `.dmg`, large binaries stay off git.
3. **Prefer dedupe** — skip files whose hash already exists under `Car Cards/` (class E) or `docs/` (class A).
4. **Browse first** — human sort of `browse` rows before any future ingest.

---

## Target buckets (consolidation tree — when history project runs)

| Bucket | Future path | Contents |
|--------|-------------|----------|
| **F-narrative** | `docs/archive/narrative/` | Timetables, narrative docx, historical writeups |
| **F-media** | `docs/archive/media/` | Layout photos, track schemes |
| **F-reference** | `docs/archive/reference/` | USGS/Google map captures, external PDFs |
| **F-skip** | — | Installers, duplicates, layout photo series |

Taxonomy: [`wiki/archive/INDEX.md`](../wiki/archive/INDEX.md)

---

## Script

`consolidation/scripts/classify_f_ingest.py` reads `hart_root_inventory.csv` class-F rows and writes:

- `sor/desktop/class_f_ingest_manifest.csv`
- `wiki/archive/F-ROOT-INDEX.md`
- `html/archive/f-root-index.html` (re-wrapped by `build_site.py` with full nav)

---

## Not in scope (consolidation build)

- Class C subtree moves (hart-ops already holds SoR copies)
- Wiring Documentation bench mirror (D4)
- DJ Trains folder (model collection — separate review)
- Copying files off Desktop

---

## Dependencies

| Item | Status |
|------|--------|
| P4a decision | **Approved** |
| hart-ops (P3a) | **In** `consolidation/external/hart-ops` |
| P3b submodules | **Done** |
