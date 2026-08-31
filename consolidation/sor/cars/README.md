# Car inventory SoR (consolidation)

**ADR:** [`wiki/decisions/ADR-car-roster-single-sor.md`](../../wiki/decisions/ADR-car-roster-single-sor.md)  
**Authority:** `consolidation/external/hart-ops/data/`

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

## Build (hart-ops)

```bash
cd consolidation/external/hart-ops
python card_pipeline/build_car_roster_sor.py
python -m pytest tests/test_golden_card.py
```

Golden smoke: **NW32800**

## STS vs Operations Pro

| Equipment | In SoR | Operations Pro | STS fleet |
|-----------|--------|----------------|-----------|
| Freight with final photo | Yes | Yes | Yes |
| Passenger, caboose | Yes | Yes | **No** (by design) |
| MOW on roster | Yes | Yes | Config-only via seed JSON |
| Locomotives | Engine roster | DecoderPro | Separate |

## Counts (2026-08-31 hart-ops)

| Artifact | Count |
|----------|------:|
| Merged roster cars | 98 |
| Golden test | NW32800 PASS |
