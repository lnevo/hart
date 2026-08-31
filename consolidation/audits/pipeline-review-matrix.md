# Pipeline review matrix — refactor, SoR, testing

**Date:** 2026-08-31  
**Central SoR index:** [`sor/CENTRAL_SOR.md`](../sor/CENTRAL_SOR.md)  
**Cutover standalone plans:** [`cutover/`](../cutover/)

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
| What needs testing? | Tier **A** automated (PASS); Tier **B** manual (hosts); Tier **C** hart-ops golden + STS session smokes. |

---

## Pipelines 1–9 (layout / panel / MQTT)

| # | Name | Relevant | Refactor reviewed | Consolidation SoR | Testing | Gaps |
|---|------|----------|-------------------|-------------------|---------|------|
| 1 | JMRI AnyRail | **No** (frozen) | Guide only | — | None | Not live path for hart |
| 2 | Public names | **Yes** | Guide + D2 scripts | `sor/names/` merged + snapshots | Tier **A** phase02, names_diff | Human review merged map |
| 3 | Digicon beans | **Yes** | Guide + crosswalk audit | `sor/signals/*.csv`, `sor/wiring/` | Tier **A** audit_strict, wiring | Appearance XML live-ref only |
| 4 | Native SML + NX | **Yes** | Guide + invariants | `sor/signals/le_signal_boundaries.csv` | Tier **A** sml 93 dest | SML in live tables XML |
| 5 | CATS Masters | **Yes** | Guide + cats-integration | `sor/cats/jmri_devices.csv` | Tier **B** CATS load/smoke | Hold panels live-ref |
| 6 | USS CTC | **Yes** | Guide + tables audit | chain doc only | Tier **B** USS load | GUIObjects live-ref |
| 7 | Dispatcher | **Yes** | Guide | chain doc only | Tier **B** graph counts | traininfo/ live-ref |
| 8 | Wiring docs | **Yes** | Guide + crosswalk | `sor/wiring/` xlsx + CSV | Tier **A** crosswalk | Desktop wiring mirror inventory only |
| 9 | LCOS firmware | **Yes** | Guide + TIER_B spec | `external/lcos-bridge/` | Tier **B** broker smoke | Event 125 closed (D10b) |
| — | Tables merge | **Yes** | Guide + audit | `sor/tables/README.md` | Tier **A** (chain) | No full tables.xml snapshot |
| — | MQTT mimic | **Yes** | Cross-cutting guide | uses names + tables ref | Tier **B** optional | Lab-only QA tool |

---

## Pipelines 11–16 (ops / Desktop)

| # | Name | Relevant | Refactor reviewed | Consolidation SoR | Testing | Gaps |
|---|------|----------|-------------------|-------------------|---------|------|
| 11 | Speed matching | **Parked** | Guide | — | None | Synthetic profiles only |
| 12 | Car cards | **Yes** | hart-ops + D11 ADR | `external/hart-ops/data/` | Tier **C** golden NW32800 | Car photos not in git |
| 13 | Waybills | **Yes** | Guide | hart-ops CSV | Tier **C** STS session | — |
| 14 | STS | **Yes** | Guide | `external/sts-docker`, `sts-helpers` | Tier **C** session smokes | No live seed apply in build |
| 15 | Publications | **Yes** | Guide + audit | hart-ops scripts + `docs/published/` | py_compile OK; full rebuild optional | Desktop class D dupes |
| 16 | Industries | **Yes** | Guide | hart-ops `industries/` | Tier **C** matrix review | — |

---

## Cross-cutting inventory & cutover

| Area | Relevant | Standalone in consolidation | Testing |
|------|----------|----------------------------|---------|
| Desktop F-root | Review/browse | manifest + F-root HTML | classify script |
| Desktop class C | **Yes** | hart-ops mirror + subtree CSV | golden + roster build |
| History archive | Future | cutover/history-archive/ | browse categories |
| Names D2 cutover | Future | cutover/names-d2/ + sor/names | Tier A map phase02 |
| Desktop slim | Future | cutover/desktop-slim/ | inventory complete |
| Layout hosts | Future | cutover/layout-hosts/ + Tier B doc | manual smokes |

---

## SoR gaps (consolidation snapshots to refresh)

Run `python3 consolidation/scripts/snapshot_live_sor.py`:

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

## Recommended test matrix before any cutover

| Tier | Command / action | Status |
|------|------------------|--------|
| A | `bash consolidation/validators/run_all.sh` | PASS (2026-08-31) |
| C | `cd external/hart-ops && pytest tests/test_golden_card.py` | PASS |
| C | Publications py_compile | PASS |
| B | Tier B manual smokes on lab host | Not run (documented) |
| C | STS begin_session / switch list | Not run (ops session) |

Regenerate this matrix after pipeline or SoR changes.
