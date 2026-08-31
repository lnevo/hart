> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only bench) | Build target |
|------|------------------------|--------------|
| Runbook | `wiki/pipelines/industry-routing.md` | this file |
| Matrix | `consolidation/external/hart-ops/industries/HART_Industry_Routing_Matrix.xlsx` | hart-ops |
| Legacy bench | `~/Desktop/HART/Industries/` | read-only (D12) |

**Tier:** C · Feeds waybills (13) and STS seed (14)

---

# Pipeline 16 — Industry routing

Maintain supplier/customer/commodity matrix for waybills and STS seed.

**Status:** **hart-ops** (`consolidation/external/hart-ops/industries/`).

## Run

```bash
cd consolidation/external/hart-ops/industries
python3 validate_and_update_matrix.py
```

Sync conceptually with `data/HART_Spot_Waybills.csv` when lanes change. Desktop `Industries/` untouched until cutover.
