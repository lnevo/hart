# Pipeline 14 — STS

Shipit Transportation System: HART seed database, warm-start, operating sessions, and switch lists.

**Status:** Live on the Pi at `http://RPi-JMRI.local:8980/sts/` (ADR-020); update it with `tools/hosts/pi_sts_update.sh`. The Mac's `external/sts-docker` (localhost:8980) and the sandbox (8981) are for preparing and testing, with data in `external/sts-docker-data` and helpers in `external/sts-helpers`; the steps below run against the Mac copy. Prepared data reaches the Pi as an STS backup restored there. The JMRI Home.html STS link uses the host the page was opened from, on port 8980.

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
