# Next round — consolidation

**Portal:** [`index.html`](index.html) · **F-root:** [`html/archive/f-root-index.html`](html/archive/f-root-index.html) · **Backlog:** [`BACKLOG.md`](BACKLOG.md)

---

## Scope

**Consolidation workspace only** — SoR snapshots, validators, pipeline guides, hart-ops submodule, review canvases. Live layout, Desktop/HART, Pi, and STS runtime are **out of scope** (D12 bench freeze). **No cutover execution** — cutover manifests under [`cutover/`](cutover/) are reference archive only.

---

## Completed

| Area | Output |
|------|--------|
| Meta-repo | `consolidation/external/*` submodules + manifest pins |
| hart-ops | github.com/lnevo/hart-ops submodule |
| Tranche A | manifest + pipeline guides 1–16 |
| Tranche B | `class_f_ingest_manifest.csv` (124 rows; skip/browse/archive) |
| Tranche B+ | F-root browse portal — `html/archive/f-root-index.html` |
| Tranche C | metadata-first roster + golden smoke (NW32800) |
| Tables merge | [`wiki/pipelines/tables-merge.md`](wiki/pipelines/tables-merge.md) + audit refresh |
| Decisions | D1–D12, ADRs, bench freeze |
| Validators | Tier A — ALL PASSED after mirror refresh |
| D2 review | Device map + legacy canvases — owner approved |
| Publications | Full rebuild via `rebuild_publications.sh` |
| Industry matrix | Review canvas — owner approved for now |

---

## Continue here (ongoing consolidation work)

Focus: **keep SoRs current and validators green** across all pipelines. Promotion to live and cutover are **not** on this list.

| Item | Path |
|------|------|
| Mirror + validate | `bash consolidation/scripts/mirror_all_live.sh` |
| Review canvases | `python3 consolidation/scripts/build_review_canvases.py` |
| Portal rebuild | `python3 consolidation/scripts/build_site.py` |
| Pipeline matrix | [`audits/pipeline-review-matrix.md`](audits/pipeline-review-matrix.md) |
| Tier B smokes | [`validators/TIER_B_MANUAL_SMOKES.md`](validators/TIER_B_MANUAL_SMOKES.md) — reference only until lab host |
| Class-F browse sort (optional) | `sor/desktop/class_f_ingest_manifest.csv` + F-root HTML |

---

## Commands

```bash
bash consolidation/scripts/mirror_all_live.sh
python3 consolidation/scripts/build_review_canvases.py
python3 consolidation/scripts/build_site.py
python3 consolidation/scripts/classify_f_ingest.py   # refresh F-root browse
cd consolidation/external/hart-ops && python tests/test_golden_card.py
bash consolidation/scripts/rebuild_publications.sh
```
