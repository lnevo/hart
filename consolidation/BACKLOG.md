# Consolidation backlog

**Updated:** 2026-08-31 (finalize pass)

**Central SoR:** [`sor/CENTRAL_SOR.md`](sor/CENTRAL_SOR.md) · **Pipeline matrix:** [`audits/pipeline-review-matrix.md`](audits/pipeline-review-matrix.md)

---

## Done (1–42)

Core workspace, portal, F-root categories, hart-ops, validators, audits.

---

## Done (43–48) — inventory + standalone cutover

| # | Item | Output |
|---|------|--------|
| 43 | Live SoR snapshots | `sor/signals/`, `sor/cats/`, `sor/wiring/` xlsx + `snapshot_manifest.csv` |
| 44 | Class C subtree inventory | `hart_subtree_inventory.csv`, `desktop-subtree-inventory.md` |
| 45 | Central SoR index | `sor/CENTRAL_SOR.md` |
| 46 | Cutover standalone projects | `cutover/*` (5 projects, manifests, no live edits) |
| 47 | Pipeline review matrix | `audits/pipeline-review-matrix.md` |
| 48 | Portal: cutover + SoR nav | build_site |

---

## Done (49–54) — standalone mirrors

| # | Item | Output |
|---|------|--------|
| 49 | HART runtime mirror | `external/hart-runtime/` (~55 MB) |
| 50 | Desktop data mirror | `external/desktop-data/` (~530 MB) |
| 51 | `mirror_all_live.sh` | One-command refresh + validate |
| 52 | `consolidation_paths.py` | Validators prefer mirrors |
| 53 | `WORKSPACE.md` + env example | Standalone docs |
| 54 | `standalone-gaps.md` refresh | Cutover readiness updated |

---

## Done (55–60) — deploy packages

| # | Item | Output |
|---|------|--------|
| 55 | Deploy packages tree | `packages/{infra,lcos-bridge,layout-hosts,car-cards,sts}/` |
| 56 | Layout host sync from consolidation | `sync_from_consolidation.sh` |
| 57 | LCOS bridge deploy scripts | `run_bridge.sh`, `run_bridge.ps1` |
| 58 | Car cards incoming pipeline | `setup_car_cards_workspace.sh`, `run_process.sh`, `HART_CAR_CARDS_ROOT` |
| 59 | DJ Trains mirror | `desktop-data/dj-trains/` |
| 60 | `process_car_images.py` in hart-ops | card pipeline complete |

---

## Done (61–66) — finalize validation pass

| # | Item | Output |
|---|------|--------|
| 61 | Full mirror + Tier A refresh | `mirror_all_live.sh` — ALL PASSED (2026-08-31T21:04Z) |
| 62 | Tier C golden smoke | `tests/test_golden_card.py` — NW32800 OK |
| 63 | Publications rebuild | `rebuild_publications.sh` — 8 scripts OK |
| 64 | Review canvases + portal | `build_review_canvases.py`, `build_site.py` |
| 65 | D2 device map review | Owner approved — canvases + `d2_legacy_match.csv` |
| 66 | Industry matrix review | Owner approved — canvas OK for now |

---

## Deferred (needs hosts or explicit future request)

| Item | Notes |
|------|-------|
| Tier B manual smokes | CATS/USS/LCOS — documented in `TIER_B_MANUAL_SMOKES.md`; not run during build |
| STS Tier C session | begin_session / switch lists — needs Docker ops session |
| Live promotion (D2, cutover) | **Not scheduled** — consolidation build continues; see `cutover/` reference archive only |
| Legacy raw Images one-time import | `DESKTOP_MIRROR_RAW=1` only if needed |

---

## Rhythm (repeat after SoR or pipeline changes)

```bash
bash consolidation/scripts/mirror_all_live.sh
bash consolidation/validators/run_all.sh
python3 consolidation/scripts/build_review_canvases.py
python3 consolidation/scripts/build_site.py
```
