# Retired card_pipeline scripts (2026-11-10)

Moved out of `ops/hart-ops/card_pipeline/` because `bin/cars` (ADR-013) replaced them or their job is done:

| Script | Replaced by |
|--------|-------------|
| `generate_card_review_html.py`, `apply_card_review.py`, `output/card_review.html` | `bin/cars review` contact sheet and `bin/cars sheet-import` |
| `extract_image_metadata.py`, `ocr_card_fill_manifest.py`, `enrich_visual_metadata.py` | `bin/cars intake`, `kind` and `fill`, writing the car repository instead of `image_metadata.csv` |
| `generate_operations_article.py` | One-off; its article is in `archive/history/docs/` |
| `generate_aspect_sample_page.py` | One-off sticker-crop test page |
| `car_visual.py`, `clean_manifest.py`, `make_framed_logo.py`, `ocr_compare.py` | Nothing referenced them (repo audit, 2026-11-18): an old visual helper, an `image_metadata.csv` cleaner, a one-off logo frame and an OCR engine comparison |

They import modules that stay in `card_pipeline/`; run one from there (`PYTHONPATH=ops/hart-ops/card_pipeline`) if it is ever needed again.
