# Desktop HART snapshots (consolidation)

Read-only scans of `~/Desktop/HART` — **not** git SoR.

| File | Generator |
|------|-----------|
| `hart_root_inventory.csv` | `scripts/inventory_desktop_hart.py` |
| `class_f_ingest_manifest.csv` | `scripts/classify_f_ingest.py` |
| Audit narrative | `audits/desktop-inventory.md` |

## F-root browse (categorized)

**Portal:** [`html/archive/f-root-index.html`](../../html/archive/f-root-index.html)

| Disposition | Count | Categories |
|-------------|------:|------------|
| browse | 33 | screenshots, eBay/listings, social, iPhone, reference photos, other |
| archive | 68 | narrative, reference, prototype media |
| skip | 23 | installers, layout photo series, wiring drafts, temp files |

Regenerate: `python3 consolidation/scripts/classify_f_ingest.py`

Operational subtrees (class **C**) → **hart-ops** / sibling repos under `consolidation/external/`.
