> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only bench) | Build target |
|------|------------------------|--------------|
| Runbook | `wiki/pipelines/sts.md` | this file |
| Runtime | `external/sts-docker` | submodule @ pin |
| Helpers | `external/sts-helpers` | submodule @ pin |
| Roster / waybills | `external/hart-ops/data/` | hart-ops SoR |
| Legacy bench | `~/Desktop/HART/Car Cards/` | read-only (D12) |

**Tier:** C · **D12:** no live seed apply during consolidation

---

# Pipeline 14 — STS

Shipit Transportation System: HART seed database, warm-start, sessions, switch lists.

**Status:** Meta-repo submodules. **Do not apply seed to live Docker** during consolidation bench freeze.

## Inputs

- `external/sts-helpers/seed/` (`hart_seed_config.json`, CSV inputs)
- `external/hart-ops/data/` (roster XML, waybills, `image_metadata.csv`)
- `HART_CAR_IMAGES_FINAL` for car photos in generated seed

## Wrappers (hart-ops)

```bash
cd external/hart-ops
./bin/apply_hart_seed.sh --generate --merge-fleet   # cutover / lab only
./bin/apply_warm_start.sh
./bin/begin_session.sh --run-stg-scully --switchlists
```

Canonical PHP runtime: **`external/sts-docker/sts/`**. Read `external/sts-helpers` and `external/sts-docker` AGENTS.md.

Switch-list docs: `external/sts-helpers/docs/SWITCHLIST_BUILDING.md`.
