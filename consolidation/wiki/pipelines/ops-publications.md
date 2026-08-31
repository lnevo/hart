> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only bench) | Build target |
|------|------------------------|--------------|
| Runbook | `wiki/pipelines/ops-publications.md` | this file |
| Rebuild scripts | `consolidation/external/hart-ops/publications/rebuild_*.py` | hart-ops |
| Published output | `consolidation/external/hart-ops/docs/published/` | hart-ops |
| Desktop root dupes | class **D** in [`audits/desktop-inventory.md`](../../audits/desktop-inventory.md) | cutover only |

**Tier:** C · **D12:** do not overwrite Desktop or live `hart/docs/`

---

# Pipeline 15 — Ops publications

Rebuild official HART crew/dispatcher paperwork from Python content dicts.

**Status:** **hart-ops** (`consolidation/external/hart-ops/publications/` → `docs/published/`).

## Run

```bash
bash consolidation/scripts/rebuild_publications.sh
```

Or individually:

```bash
cd consolidation/external/hart-ops
.venv/bin/python publications/rebuild_scale_operating_instructions.py
.venv/bin/python publications/rebuild_dispatcher_train_list.py
.venv/bin/python publications/rebuild_yardmaster_sequence.py
.venv/bin/python publications/rebuild_crew_instructions.py
.venv/bin/python publications/rebuild_station_map.py
.venv/bin/python publications/rebuild_local_station_maps.py
.venv/bin/python publications/rebuild_operator_primer.py
.venv/bin/python publications/update_tt23_station_map.py
```

Index: `docs/published/README.md`. Desktop root Word duplicates (class D) documented in [`audits/desktop-inventory.md`](../../audits/desktop-inventory.md).
