# Next round — consolidation (post-decisions)

**Recorded:** 2026-08-31 · [`DECISIONS_RECORDED.md`](DECISIONS_RECORDED.md)

## In progress / this round

| Task | Status | Output |
|------|--------|--------|
| Record D1–D10 | done | `DECISIONS_RECORDED.md` |
| Names CSV overlap audit | done | `audits/block-display-vs-map.md` |
| MQTT static-ref grep | done | `audits/mqtt-static-refs.md` + `validators/check_mqtt_no_static_lists.py` |
| LCOS working baseline doc | done | `cross-repo/lcos/WORKING_BASELINE.md` |
| ADR: single names SoR | done | `wiki/decisions/ADR-names-single-sor.md` |
| ADR: unused-modules policy | done | `unused-modules/README.md` |
| Pi portal note (D9) | done | `wiki/decisions/ADR-portal-hosting-deferred.md` |

## Up next (P2 consolidation)

1. **Names migration plan** — map-derived OS **covers all 23 legacy OS rows** (`propose_os_from_map.py`); promote phase02 read from map; retire `block_display_names.csv`.
2. **Wiring crosswalk** — close 10 ID gap (1132–1136 vs 1237–1241); document in `sor/wiring/`.
3. **Virtual stub masts** — **Option A approved** (document-only). See [`audits/proposed-virtual-masts.md`](audits/proposed-virtual-masts.md). D2 sub-decisions: [`wiki/decisions/D2-promotion-checklist.md`](wiki/decisions/D2-promotion-checklist.md).
4. **`unused-modules/`** — move retired one-shot cleanup patterns as templates (not live).
5. **LCOS submodule spec** — pin working commit + validation checklist before any bridge edits.

## Promotion gate (unchanged)

User approval + `bash consolidation/validators/run_all.sh` green + live STATUS/deploy if artifacts change.
