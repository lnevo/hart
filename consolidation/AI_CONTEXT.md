# Consolidation AI context

Draft handoff for agents working in **`hart/consolidation/`** only. Live landmines remain in root [`docs/AI_CONTEXT.md`](../docs/AI_CONTEXT.md) — read both.

## Mission

Build the **new authoritative HART tree** under `consolidation/` + `consolidation/external/*`. Live `jmri/`, `cats/`, `tables/`, and `~/Desktop/HART/` are **read-only** during the build (D12).

## Active layout (live reference)

- **Layout name:** `hart` (`export JMRI_LAYOUT=hart`)
- **Monitor file:** `jmri/layouts/hart/output/hart_prod.xml`
- **Deploy bundle:** `jmri/layouts/hart/output/tables.xml`
- **Writable tables (live only):** `tables/new_tables.xml` — do not edit from consolidation

## Consolidation-specific

| Topic | Live behavior | Consolidation action |
|-------|---------------|----------------------|
| MQTT heads | Live roster from `track/signalmast/#` | `validators/check_mqtt_no_static_lists.py` |
| NextTrain / Sheets | Abandoned for hart | Note in pipeline index |
| AnyRail for hart | Frozen | Pipeline 1 deprecated |
| Master4 CATS | Live desk | `wiki/pipelines/cats-masters.md` |
| OpenLCB routes 0001–0004 | Removed (one-shot) | `unused-modules/tables/` (D5) |
| END_BUMPER stubs | Required for Dispatcher/SML | Document; do not drop |
| EH MQTT labels | Geographic vs channel swapped | wiring crosswalk audit |
| Car roster SoR | **hart-ops** `data/image_metadata.csv` | D11 — not Operations Pro GUI |
| F-root Desktop files | 124 class-F at bench root | [`html/archive/f-root-index.html`](html/archive/f-root-index.html) |

## External modules (only here)

```
consolidation/external/
  hart-ops/      publications, car cards, industries
  lcos-bridge/   LCOS firmware
  sts-docker/    STS runtime
  sts-helpers/   seed / switch lists
```

No clones under `$HOME` (e.g. no `~/hart-ops`).

## Commands

```bash
bash consolidation/validators/run_all.sh
python3 consolidation/scripts/build_site.py
python3 consolidation/scripts/classify_f_ingest.py
cd consolidation/external/hart-ops && python card_pipeline/build_car_roster_sor.py
```

## Navigation

- Portal: [`index.html`](index.html)
- Backlog: [`BACKLOG.md`](BACKLOG.md)
- Decisions: [`DECISIONS_RECORDED.md`](DECISIONS_RECORDED.md)
