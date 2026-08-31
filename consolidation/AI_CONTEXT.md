# Consolidation AI context

Draft handoff for agents working in **`hart/consolidation/`** only. Live landmines remain in root [`docs/AI_CONTEXT.md`](../docs/AI_CONTEXT.md) — read both.

## Active layout

- **Live layout:** `hart` (`export JMRI_LAYOUT=hart`)
- **Load file:** `jmri/layouts/hart/output/hart_prod.xml` (monitor); deploy bundle is `output/tables.xml`
- **Writable tables:** `tables/new_tables.xml` only

## Consolidation-specific

| Topic | Live behavior | Consolidation action |
|-------|---------------|----------------------|
| MQTT heads | Live roster from `track/signalmast/#` | Document in pipeline 3; validate in `validators/check_wiring_crosswalk.py` |
| NextTrain / Sheets | Abandoned for hart | Note in pipeline index; do not revive |
| AnyRail for hart | Frozen | Pipeline 1 deprecated |
| Master4 CATS | Live desk | Draft docs in `wiki/pipelines/cats-masters.md` |
| OpenLCB routes 0001–0004 | Removed (one-shot) | Do not re-add to immortal lists (D5) |
| END_BUMPER stubs | Required for Dispatcher/SML | Document; do not drop in refactors |
| EH MQTT labels | Geographic vs channel swapped | STATUS fact; document in wiring crosswalk |

## Validator commands

```bash
bash consolidation/validators/run_all.sh
```

## Browse site

Open `consolidation/index.html` in a browser.

## Decisions

See [`DECISIONS_PENDING.md`](DECISIONS_PENDING.md) — batch approval required before promotion.
