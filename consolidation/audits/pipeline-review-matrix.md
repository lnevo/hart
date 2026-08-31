# Pipeline review matrix — refactor, SoR, testing

**Date:** 2026-08-31 (finalize pass)  
**Central SoR index:** [`sor/CENTRAL_SOR.md`](../sor/CENTRAL_SOR.md)

Legend:
- **Relevant:** active for hart layout today
- **SoR in consolidation:** snapshot or authority under `consolidation/` / `external/`
- **Refactor reviewed:** guide + audit exist; script copies or submodule pin documented
- **Tier A/B/C:** automated or manual test coverage

---

## Summary

| Question | Answer |
|----------|--------|
| All pipelines reviewed for refactor? | **Yes — documented.** Refactor **copies** exist where needed; live scripts unchanged by design (D12). |
| Central SoR for all parts? | **Mostly.** CSV/XLSX SoR snapshotted to `sor/`; hart-ops/STS/LCOS in `external/`; large generated XML stays live-ref + validators. |
| What's not relevant? | Pipeline **1** (frozen AnyRail), **11** (parked speed match), Gate 1 CATS panels, LCOS BOM (D8), NextTrain/Sheets. |
| What needs testing? | Tier **A** automated **PASS**; Tier **C** golden + publications **PASS**; Tier **B** manual **deferred** (hosts); STS session **deferred**. |
| D2 names review | **Complete** — owner approved; no live promotion scheduled. |
| Cutover | **Not scheduled** — [`cutover/`](../cutover/) is reference archive only. |

---

## Pipelines 1–9 (layout / panel / MQTT)

| # | Name | Relevant | Refactor reviewed | Consolidation SoR | Testing | Gaps |
|---|------|----------|-------------------|-------------------|---------|------|
| 1 | JMRI AnyRail | **No** (frozen) | Guide only | — | None | Not live path for hart |
| 2 | Public names | **Yes** | Guide + D2 scripts | `sor/names/` merged + snapshots | Tier **A** phase02, names_diff | D2 review **done**; promotion future |
| 3 | Digicon beans | **Yes** | Guide + crosswalk audit | `sor/signals/*.csv`, `sor/wiring/` | Tier **A** audit_strict, wiring | Appearance XML live-ref only |
| 4 | Native SML + NX | **Yes** | Guide + invariants | `sor/signals/le_signal_boundaries.csv` | Tier **A** sml 93 dest | SML in live tables XML |
| 5 | CATS Masters | **Yes** | Guide + cats-integration | `sor/cats/jmri_devices.csv` | Tier **B** CATS load/smoke | Hold panels live-ref; B deferred |
| 6 | USS CTC | **Yes** | Guide + tables audit | chain doc only | Tier **B** USS load | GUIObjects live-ref; B deferred |
| 7 | Dispatcher | **Yes** | Guide | chain doc only | Tier **B** graph counts | traininfo/ live-ref; B deferred |
| 8 | Wiring docs | **Yes** | Guide + crosswalk | `sor/wiring/` xlsx + CSV | Tier **A** crosswalk | Desktop wiring mirror inventory only |
| 9 | LCOS firmware | **Yes** | Guide + TIER_B spec | `external/lcos-bridge/` | Tier **B** broker smoke | Event 125 closed (D10b); B deferred |
| — | Tables merge | **Yes** | Guide + audit | `sor/tables/README.md` | Tier **A** (chain) | No full tables.xml snapshot |
| — | MQTT mimic | **Yes** | Cross-cutting guide | uses names + tables ref | Tier **B** optional | Lab-only QA tool |

---

## Pipelines 11–16 (ops / Desktop)

| # | Name | Relevant | Refactor reviewed | Consolidation SoR | Testing | Gaps |
|---|------|----------|-------------------|-------------------|---------|------|
| 11 | Speed matching | **Parked** | Guide | — | None | Synthetic profiles only |
| 12 | Car cards | **Yes** | hart-ops + D11 ADR | `external/hart-ops/data/` | Tier **C** golden NW32800 **PASS** | Car photos not in git |
| 13 | Waybills | **Yes** | Guide + script inventory | hart-ops CSV | Tier **C** STS session deferred | — |
| 14 | STS | **Yes** | Guide | `external/sts-docker`, `sts-helpers` | Tier **C** session smokes deferred | No live seed apply in build |
| 15 | Publications | **Yes** | Guide + audit | hart-ops scripts + `docs/published/` | rebuild + py_compile **PASS** | Desktop class D dupes |
| 16 | Industries | **Yes** | Guide | hart-ops `industries/` | Tier **C** canvas review **done** | — |

---

## Reference archive (not scheduled)

Historical cutover manifests — documented for a future explicit promotion request, not active work:

| Area | Consolidation copy | Notes |
|------|-------------------|-------|
| History archive | `cutover/history-archive/` | browse categories |
| Names D2 batch | `cutover/names-d2/` + `sor/names/` | Tier A map phase02 green |
| Desktop slim | `cutover/desktop-slim/` | inventory complete |
| Layout hosts | `cutover/layout-hosts/` | Tier B doc only |
| Class C migration | `cutover/class-c-migration/` | hart-ops mirror |

---

## SoR refresh

Run as part of `bash consolidation/scripts/mirror_all_live.sh` or standalone:

```bash
python3 consolidation/scripts/snapshot_live_sor.py
```

| Live path | Consolidation target | Pipeline |
|-----------|---------------------|----------|
| `cats/data/signal_*.csv` | `sor/signals/` | 3–4 |
| `cats/data/occupancy_bindings.csv` | `sor/signals/` | 8 |
| `cats/data/jmri_devices.csv` | `sor/cats/` | 5 |
| `docs/wiring/*.xlsx` | `sor/wiring/` | 8 |
| `jmri/.../public_name_map.csv` | `sor/names/` | 2 |

**Not snapshotted (generated / too large):** `tables/*.xml`, CATS hold XML, `traininfo/`, car photos.

---

## Refactor policy (what we did vs did not do)

| Did | Did not |
|-----|---------|
| Document every pipeline with SoR table | Edit live `jmri/`, `cats/`, `tables/` |
| Copy SoR CSVs to `consolidation/sor/` | Copy 3.3 GB Desktop Car Cards |
| Submodule pins for hart-ops, LCOS, STS | Remove or slim Desktop |
| Script **copies** in `consolidation/scripts/` | Replace live scripts in place |
| Validators read live, write audits only | Run host deploy or STS seed apply |

---

## Validation status (consolidation build)

| Tier | Command / action | Status |
|------|------------------|--------|
| A | `bash consolidation/validators/run_all.sh` | **PASS** (2026-08-31T21:04Z) |
| C | `cd external/hart-ops && python tests/test_golden_card.py` | **PASS** |
| C | `bash consolidation/scripts/rebuild_publications.sh` | **PASS** |
| C | Publications py_compile | **PASS** |
| B | Tier B manual smokes on lab host | **Deferred** (documented) |
| C | STS begin_session / switch list | **Deferred** (needs Docker session) |

Regenerate this matrix after pipeline or SoR changes.
