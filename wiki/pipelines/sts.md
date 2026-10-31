# Pipeline 14 — STS

Shipit Transportation System: HART seed database, warm-start, operating sessions, and switch lists.

**Status:** Live. Runtime: `external/sts-docker`. Data: `external/sts-docker-data`. Helpers: `external/sts-helpers`. JMRI Home.html links to `http://10.0.0.53:8980/sts/`.

## Inputs

- `external/sts-helpers/seed/` (`hart_seed_config.json`, roster/waybill CSVs)
- `external/sts-helpers/seed/inputs/` (resolved by seed: roster XML, waybills, spots)
- `ops/car-cards/car-images/CarImagesFinal/` for car photos in generated seed

## Outputs

- MySQL `hart_seed` (and session backups under `external/sts-docker-data/backups`)
- Switch lists at `http://localhost:8980/switchlists/index.html`
- Session editor `http://localhost:8980/sts/editor.html`

## Run

From the project root:

```bash
bash tools/ops/sts_compose.sh up -d
cd external/sts-helpers
./apply_hart_seed.sh --generate --merge-fleet
./apply_warm_start.sh
./begin_session.sh --run-stg-scully --switchlists
./generate_switchlists.sh --format=phased
```

Canonical PHP runtime is **`external/sts-docker/sts/`**. Diagnostics live in `external/sts-helpers/diagnostics/`, not in the web tree. Read `external/sts-docker/AGENTS.md`.

Switch-list styles and gaps: `external/sts-helpers/docs/SWITCHLIST_BUILDING.md`.
