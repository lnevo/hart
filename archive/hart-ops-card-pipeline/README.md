# Retired card_pipeline scripts (2026-11-10)

Moved out of `ops/hart-ops/card_pipeline/` because `bin/cars` (ADR-013) replaced them or their job is done:

| Script | Replaced by |
|--------|-------------|
| `generate_card_review_html.py`, `apply_card_review.py`, `output/card_review.html` | `bin/cars review` contact sheet and `bin/cars sheet-import` |
| `extract_image_metadata.py`, `ocr_card_fill_manifest.py`, `enrich_visual_metadata.py` | `bin/cars intake`, `kind` and `fill`, writing the car repository instead of `image_metadata.csv` |
| `generate_operations_article.py` | One-off; its article is in `archive/docs/` |
| `generate_aspect_sample_page.py` | One-off sticker-crop test page |

They import modules that stay in `card_pipeline/`; run one from there (`PYTHONPATH=ops/hart-ops/card_pipeline`) if it is ever needed again.
