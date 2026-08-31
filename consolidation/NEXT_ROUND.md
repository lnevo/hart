# Next round — consolidation

**Portal:** [`index.html`](index.html) · **F-root:** [`html/archive/f-root-index.html`](html/archive/f-root-index.html) · **Backlog:** [`BACKLOG.md`](BACKLOG.md)

---

## Scope

**Consolidation workspace only** — build docs, validators, audits, hart-ops, and submodule pins. Live layout, Desktop/HART, Pi, and STS runtime are **out of scope** for this effort (D12 bench freeze).

---

## Completed

| Area | Output |
|------|--------|
| Meta-repo | `consolidation/external/*` submodules + manifest pins |
| hart-ops | github.com/lnevo/hart-ops @ `761c1f9` |
| Tranche A | manifest + pipeline guides 12–16 |
| Tranche B | `class_f_ingest_manifest.csv` (124 rows; skip/browse/archive) |
| Tranche B+ | F-root browse portal — `html/archive/f-root-index.html` |
| Tranche C | metadata-first roster + golden test (NW32800) |
| Tables merge | [`wiki/pipelines/tables-merge.md`](wiki/pipelines/tables-merge.md) + audit refresh |
| Decisions | D1–D12, ADRs, bench freeze |
| Validators | Tier A — run `run_all.sh` after changes |

---

## Continue here (consolidation branch work)

| Item | Path |
|------|------|
| Tier A validators | `bash consolidation/validators/run_all.sh` |
| Class-F browse sort (optional) | `sor/desktop/class_f_ingest_manifest.csv` + F-root HTML |
| D2 draft validation | `sor/names/public_name_map_merged.csv` |
| Tier B smoke docs | `validators/TIER_B_MANUAL_SMOKES.md` (reference only during freeze) |
| Portal rebuild | `python3 consolidation/scripts/build_site.py` |
| History archive (future) | `HART_*` class-F rows → separate project when ready |

---

## Commands

```bash
bash consolidation/validators/run_all.sh
python3 consolidation/scripts/build_site.py
python3 consolidation/scripts/classify_f_ingest.py   # refresh F-root browse
cd consolidation/external/hart-ops && python card_pipeline/build_car_roster_sor.py
```
