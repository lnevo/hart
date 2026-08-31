> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record (consolidation view)

| Kind | Live path (read-only) | Proposed consolidation path |
|------|----------------------|----------------------------|
| Runbook | `wiki/pipelines/sts.md` | `consolidation/wiki/pipelines/sts.md` |
| Artifacts | See live guide below | `consolidation/sor/` when promoted |

---

# Pipeline 14 — STS

Shipit Transportation System: HART seed database, warm-start, operating sessions, and switch lists.

**Status:** Live. Runtime: `~/sts/sts-docker`. Host toolkit: `~/Desktop/HART/Car Cards/sts-docker-helpers/`. JMRI Home.html links to `http://10.0.0.53:8980/sts/`.

## Inputs

- `sts-docker-helpers/seed/` (`hart_seed_config.json`, roster/waybill CSVs)
- `Car Cards/data/` (resolved by seed: roster XML, waybills, spots)
- `CarImagesFinal/` for car photos in generated seed

## Outputs

- MySQL `hart_seed` (and session backups under `~/sts/sts-backups`)
- Switch lists at `http://localhost:8980/switchlists/index.html`
- Session editor `http://localhost:8980/sts/editor.html`

## Run

From `~/Desktop/HART/Car Cards/` (wrappers) or `sts-docker-helpers/bin/`:

```bash
./apply_hart_seed.sh --generate --merge-fleet
./apply_warm_start.sh
./begin_session.sh --run-stg-scully --switchlists
./generate_switchlists.sh --format=phased
```

Canonical PHP runtime is **`sts-docker/sts/`**. Diagnostics live in `sts-docker-helpers/diagnostics/`, not in the web tree. Read `Car Cards/AGENTS.md` then `sts-docker/AGENTS.md`.

Switch-list styles and gaps: `sts-docker-helpers/docs/SWITCHLIST_BUILDING.md`.
