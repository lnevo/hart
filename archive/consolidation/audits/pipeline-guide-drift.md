# Audit — pipeline guide drift (live vs consolidation)

**Date:** auto-generated

Live [`wiki/pipelines/`](../../wiki/pipelines/) is read-only reference.
Consolidation [`wiki/pipelines/`](../wiki/pipelines/) is the build target — **intentional diffs expected** (SoR headers, hart-ops paths, D12 notes).

## Summary

| Metric | Count |
|--------|------:|
| Shared guides | 15 |
| Byte-identical | 0 |
| Intentionally diverged | 15 |
| Consolidation-only | 2 |
| Live-only (excluded) | 0 |

## Diverged (consolidation is authoritative for build)

- `car-cards.md`
- `cats-masters.md`
- `digicon-signal-beans.md`
- `dispatcher-system.md`
- `industry-routing.md`
- `jmri-anyrail.md`
- `lcos-firmware.md`
- `native-sml.md`
- `ops-publications.md`
- `public-names.md`
- `speed-matching.md`
- `sts.md`
- `uss-ctc.md`
- `waybills.md`
- `wiring-docs.md`

## Consolidation-only guides

- `mqtt-mimic.md`
- `tables-merge.md`

## When to sync

Do **not** blind-run `sync_pipeline_guides.py` — it overwrites consolidation drafts.
Merge live changes manually into consolidation guides when live wiki updates.

Regenerate this report:

```bash
python3 consolidation/scripts/audit_pipeline_guide_drift.py
```
