# Print outputs — car cards & spot waybills

| File | Role | In git |
|------|------|--------|
| `HART_Equipment_Card_Template.docx` | Mail-merge master on poker sticker sheet | yes |
| `HART_Spot_Waybills.docx` | Generated spot waybill deck | yes |
| `card_review.html` | Visual review grid | yes |
| `HART_All_Car_Cards.docx` | Full fleet print run (~345 MB) | **mirror only** |

Regenerate:

```bash
python card_pipeline/generate_card_template.py
python card_pipeline/generate_waybill_cards.py
python card_pipeline/generate_all_cards.py   # large; writes HART_All_Car_Cards.docx
```

Full deck: `ops/car-cards/print/HART_All_Car_Cards.docx`
