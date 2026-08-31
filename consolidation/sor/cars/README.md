# Car inventory SoR (consolidation draft)

**ADR:** [`wiki/decisions/ADR-car-roster-single-sor.md`](../../wiki/decisions/ADR-car-roster-single-sor.md)  
**Live today:** `~/Desktop/HART/Car Cards/data/` → future **`hart-ops/data/`**

## One inventory, three exports

```
image_metadata.csv  ──build──►  HART_MergedCarRoster.xml  (canonical full fleet)
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
         OperationsCarRoster.xml   car cards          STS seed
         (ALL cars → Ops Pro)      (photo freight)    (freight subset)
```

## File roles

| File | Authority | Edited by |
|------|-----------|-----------|
| `image_metadata.csv` | **Yes** — marks, weights, OCR, photos | OCR pipeline + visual review |
| `HART_MergedCarRoster.xml` | Generated | `build_car_roster_sor.py` |
| `OperationsCarRoster.xml` | Generated | `export_operations_roster.py` |
| `OperationsEngineRoster.xml` | Separate loco roster | DecoderPro / ops |

## STS vs Operations Pro

| Equipment | In SoR | Operations Pro | STS fleet |
|-----------|--------|----------------|-----------|
| Freight with final photo | Yes | Yes | Yes |
| Passenger, caboose | Yes | Yes | **No** (by design) |
| MOW on roster | Yes | Yes | Config-only via seed JSON |
| Locomotives | Engine roster | DecoderPro | Separate |

## Snapshot (2026-08-31 Desktop)

| Artifact | Count |
|----------|------:|
| `image_metadata.csv` rows | 82 |
| `OperationsCarRoster.xml` cars | 79 |
| `HART_MergedCarRoster.xml` cars | 98 |

Merged includes metadata-only freight not yet on the legacy ops export.

## Promotion

Rebuild and verify in **hart-ops** only. Cutover to JMRI profiles and Desktop retirement is a **separate project** (D12).
