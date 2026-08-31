# ADR — Single car inventory SoR (outside Operations Pro)

**Status:** Accepted (consolidation) · promotion to live `wiki/` when hart-ops migrates  
**Date:** 2026-08-31  
**Context:** P3a hart-ops · golden car · STS seed · JMRI Operations Pro sync

## Decision

Maintain **one authoritative car inventory** in **hart-ops** (not in JMRI Operations Pro GUI). JMRI and STS are **consumers** with different filters.

## SoR stack (hart-ops `data/`)

| Layer | File | Role |
|-------|------|------|
| **1 — editable manifest** | `image_metadata.csv` | Reporting marks, OCR weights/capacities, photo refs, roster_id, notes |
| **2 — canonical XML** | `HART_MergedCarRoster.xml` | **Generated** full fleet inventory (freight + passenger + caboose + MOW on roster) |
| **3 — JMRI export** | `OperationsCarRoster.xml` | **Generated** from layer 2 — Operations Pro reads this; must include **all** cars |
| **4 — engine roster** | `OperationsEngineRoster.xml` | Locomotives only (separate from freight car SoR) |

**Do not** treat Pi-exported `OperationsCarRoster.xml` as upstream authority after migration. Operations Pro is a **sync target**, not the editor of record.

## Consumer rules

| Consumer | Input | Filter |
|----------|-------|--------|
| **Operations Pro (PanelPro)** | `OperationsCarRoster.xml` | **All cars** — passenger, caboose, MOW included |
| **Car card pipeline** | `image_metadata.csv` + Merged roster | Freight with `CarImagesFinal` in notes |
| **STS seed** | Merged roster + metadata | **STS inventory only** — exclude `PASSENGER_TYPES` (Baggage, Coach, Combine, Dining, Observation, Caboose, MOW); require final photo; MOW via `hart_seed_config.json` |
| **Golden smoke** | NW32800 on Operations export | Assert generated `OperationsCarRoster.xml` row matches metadata |

Passenger equipment and cabooses **belong in the SoR** and **sync to Operations Pro** but **do not** enter STS freight fleet unless explicitly added to STS inventory config.

## Build direction (target — invert today’s flow)

**Today (Desktop):** `OperationsCarRoster.xml` → `build_merged_car_roster.py` → Merged  
**Target (hart-ops):**

```
image_metadata.csv  (+ manual roster rows for non-photo cars)
        ↓
build_car_roster_sor.py   # replaces build_merged_car_roster.py
        ↓
HART_MergedCarRoster.xml
        ↓
export_operations_roster.py → OperationsCarRoster.xml
        ↓
Pi / Mac / Windows JMRI profiles (future cutover project — **not during consolidation**)
```

STS continues via `generate_hart_seed.py` reading Merged + metadata with existing type filters.

## Fields in SoR

All rolling stock inventory fields live in `image_metadata.csv` (or merged into it):

- `roster_id`, `reporting_marks`, `road_name`, `road_number`
- `car_type`, `car_class`, `color`
- `capy_lbs`, `ld_lmt_lbs`, `lt_wt_lbs`, `roster_weight_oz`, `roster_weight_tons`
- Photo pipeline: `source_image`, `cropped_image`, `crop_status`, `notes` (`final_ref=…`)
- Optional future: `sts_eligible` (default derive from type + final photo)

## Golden car

**NW32800** — assert against generated `OperationsCarRoster.xml` after SoR build.

## Consequences

- **`sync_roster_ops_from_pi.sh`** — leave as-is on live bench; Pi roster push is **cutover project**, not consolidation.
- Align [`audits/golden-car-sor.md`](../../audits/golden-car-sor.md) and pipeline 12 docs with this ADR.
- hart-ops holds SoR files and build scripts; **does not overwrite** Desktop/HART originals until cutover.

## References

- [`sor/cars/README.md`](../../sor/cars/README.md)
- [`cross-repo/hart-ops/MIGRATION_PLAN.md`](../../cross-repo/hart-ops/MIGRATION_PLAN.md)
- [`audits/golden-car-sor.md`](../../audits/golden-car-sor.md)
