# Print archive — session waybill labels

Generated CC/WB shipment labels (poker sticker format) and inventory exports.

| File | Description |
|------|-------------|
| `HART_CC_Waybill_Labels_Sessions_1-4.docx` | Sessions 1–4 label sheets |
| `HART_CC_Waybill_Labels_Duplicates_S3-S4.docx` | Duplicate pass S3–S4 |
| `HART_Session4_Waybill_Labels_Page.docx` | Session 4 single page |
| `HART_CC_Waybill_Inventory.csv` / `.json` | Label inventory |

Regenerate from STS data:

```bash
python card_pipeline/generate_cc_waybill_labels.py --refresh
```

Sticker template: `card_pipeline/assets/Poker Size Sticker Sheet Template.docx` (local only; download link in `operator_logos/SOURCES.md`)
