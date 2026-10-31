# Cutover — history archive (class F)

**Status:** Inventory + browse complete; **no file copy** to git yet

## Standalone consolidation artifacts

| Artifact | Purpose |
|----------|---------|
| `sor/desktop/class_f_ingest_manifest.csv` | 124 rows + category |
| `html/archive/f-root-index.html` | Categorized browse |
| `wiki/archive/F-ROOT-INDEX.md` | Markdown index |

## Dispositions (owner 2026-08-31)

| Disposition | Count | Future target (when cutover runs) |
|-------------|------:|-----------------------------------|
| browse | 33 | sort in portal; optional `docs/archive/media/` |
| archive | 68 | `docs/archive/narrative/`, `reference/` |
| skip | 23 | never ingest |

## Desktop source

`~/Desktop/HART/` root files — **unchanged**. Links are `file://` in portal only.

## Test before cutover

- Human review of browse categories
- LFS policy for large media
- Dedupe vs class D/E before any copy
