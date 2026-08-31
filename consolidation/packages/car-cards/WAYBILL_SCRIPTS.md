# Waybill generation scripts (pipelines 13 + 14)

Keep these scripts in the consolidation workspace. **Do not deploy** layout hosts from here.

## Spot / industry waybills (pipeline 13)

| Script | Output | Input SoR |
|--------|--------|-----------|
| `hart-ops/card_pipeline/generate_waybill_cards.py` | `card_pipeline/output/HART_Spot_Waybills.docx` | `data/HART_Spot_Waybills.csv`, `data/spot_assignments.csv` |
| `hart-ops/card_pipeline/generate_cc_waybill_labels.py` | `docs/print/waybills/` or `--output` | STS shipments JSON |

Regenerate spot deck:

```bash
bash consolidation/packages/car-cards/run_generate_print.sh
# or:
cd consolidation/external/hart-ops
.venv/bin/python card_pipeline/generate_waybill_cards.py
```

## STS session waybills — missing / not yet printed

| Script | When to use |
|--------|-------------|
| `generate_cc_waybill_labels.py --refresh` | Export live shipments from STS Docker DB → print labels for **all open shipments** |
| `generate_cc_waybill_labels.py --json path/to/cc_shipments.json` | Reprint from saved JSON without DB |
| `sts-helpers/diagnostics/rebuild_waybill_pages.php` | Re-render **stored session waybill pages** (sessions 1…500) after print layout changes — does not create new bills |
| STS web UI `printable_ccwaybill.php` | In-session print (runtime; not duplicated here) |

### Refresh STS shipments + print labels (consolidation lab)

```bash
# STS must be running (consolidation compose)
cd consolidation/external/sts-docker
docker compose -f docker-compose.yml \
  -f ../sts-docker-data/docker-compose.consolidation.yml up -d

cd ../hart-ops
export HART_CAR_CARDS_ROOT="../desktop-data/car-cards"
.venv/bin/python card_pipeline/generate_cc_waybill_labels.py --refresh \
  --json docs/print/waybills/cc_shipments.json \
  --output docs/print/waybills/HART_CC_Waybill_Labels_current.docx
```

### Rebuild session N waybill pages (already generated, not printed)

```bash
# After STS container is up; re-aggregates frozen session store
docker exec -u www-data sts-docker-web-1 \
  php /var/www/html/sts/../diagnostics/rebuild_waybill_pages.php
```

(Session helpers live in sts-docker runtime; copy `sts-helpers/diagnostics/rebuild_waybill_pages.php` into container or mount helpers for lab.)

## Session number workflow

1. **`begin_session.sh --session N`** — creates/locks session artifacts under `sts-docker-data/backups/`
2. **Warm-start / traffic scripts** — populate orders for session N
3. **`generate_cc_waybill_labels.py --refresh`** — pull shipments **not yet printed** from DB (same query as STS Reports → CC/WB Waybills)
4. **Print** sticker docx; mark printed in STS UI as needed
5. **`rebuild_waybill_pages.php`** — fix page breaks for sessions 1…N without changing snapshot bodies

## Archived session label decks (git)

`hart-ops/docs/print/waybills/`:

- `HART_CC_Waybill_Labels_Sessions_1-4.docx`
- `HART_CC_Waybill_Labels_Duplicates_S3-S4.docx`
- `HART_Session4_Waybill_Labels_Page.docx`
- `HART_CC_Waybill_Inventory.csv` / `.json`

## Related

- [`README.md`](README.md) — car cards workspace
- [`../../wiki/pipelines/13-waybills.md`](../../wiki/pipelines/13-waybills.md) (if present)
- [`../sts/README.md`](../sts/README.md)
