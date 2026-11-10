# Review data (local only)

Kept in git, never published (ADR-009; `prepare_github_pages.py` skips this folder).

| File | Role |
|------|------|
| `hart_devices_review.json` | Device review snapshot, kept by hand; feeds `scripts/build_layout_index.py` and `tools/audit/tests/test_site_device_names.py` |
| `archive_review_log.jsonl` | Append-only log of archive and gallery edits made through `scripts/serve_portal.py` |

The F-root review of `~/Desktop/HART` and its scans moved to `archive/www-f-root-review/` on 2026-11-10.
