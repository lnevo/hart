# Golden smoke — car cards (Tier C spec)

**Status:** Consolidation spec · automation when **hart-ops** repo exists (P3a approved)  
**Pipeline:** 12 · Guide: [`wiki/pipelines/car-cards.md`](../../wiki/pipelines/car-cards.md)  
**SoR detail:** [`audits/golden-car-sor.md`](../../audits/golden-car-sor.md)

## Golden car (designated)

**`NW32800`** — N&W 52′ flatcar · photo `IMG_9106.png` · asset `card_pipeline/assets/NW32800.png`

Already hardcoded in Desktop `generate_single_card.py` and review fixtures. Confirm or override in golden-car audit.

## Preconditions

- Desktop tree: `~/Desktop/HART/Car Cards/` (until hart-ops migration)
- Python venv: `Car Cards/.venv/`
- Roster assert: generated `data/OperationsCarRoster.xml` (all cars → Ops Pro)
- SoR: `data/image_metadata.csv` → `HART_MergedCarRoster.xml`

## Golden path (manual)

```bash
cd ~/Desktop/HART/Car\ Cards
.venv/bin/python card_pipeline/generate_single_card.py
# Optional full sheet:
.venv/bin/python card_pipeline/generate_all_cards.py
```

Note: `generate_single_card.py` has **no `--car-id` flag** today; it always emits `HART_Card_NW32800.docx`. Add CLI when hart-ops repo is scaffolded.

## Pass criteria

1. `generate_single_card.py` exits 0.
2. Output docx opens without corruption.
3. Car number **32800**, road **N&W** match SoR row `NW32800` in generated `OperationsCarRoster.xml`.
4. Embedded photo matches `CarImagesFinal/IMG_9106.png` (via `assets/NW32800.png`).
5. Logo and layout match last approved sample (store hash in hart-ops when repo exists).

## Future automation (hart-ops)

| Artifact | Role |
|----------|------|
| `tests/golden/NW32800.docx` | committed golden output (small) |
| `tests/test_golden_card.py` | regen + compare text/hash |
| CI | Tier C — run on hart-ops PRs only |

## Not in scope

- OCR / image crop scripts (separate smokes)
- Waybill matrix (pipeline 13)
- STS seed merge (pipeline 14)
- Locomotive / promo rows in metadata (see golden-car-sor audit)
