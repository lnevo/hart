> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record (consolidation view)

| Kind | Live path (read-only) | Proposed consolidation path |
|------|----------------------|----------------------------|
| Runbook | `wiki/pipelines/dispatcher-system.md` | `consolidation/wiki/pipelines/dispatcher-system.md` |
| Artifacts | See live guide below | `consolidation/sor/` when promoted |

---

# Pipeline 7 — Dispatcher System graph

CreateTransits (Stage 1) in PanelPro builds sections, transits, and traininfo so auto-dispatch can run station to station.

**Status:** Live. 2026-08-22 graph: **91 sections / 688 transits / 1508** HEAD_AND_TAIL traininfo. All listed stations are origins and destinations, including S-1…S-5.

## Inputs

- Hidden virtual masts + throat blocks ([`DISPATCHER_LAYOUT_HOOPS.md`](../DISPATCHER_LAYOUT_HOOPS.md))
- Block comments with `stop` on station bodies (throats: “not a station”, never “not a stop”)
- Roster speed profiles (synthetic today — pipeline 11)

## Outputs

- Sections / transits / traininfo in the tables bundle
- Overlay: `preference:jython/patch_dispatcher_facing.py` via `hart_dispatcher_startup.py` (keep until JMRI#15407)

## Run

1. **PanelPro only** (not CATS). Load hart tables.
2. Run Dispatcher System **Stage 1**. Watch for buried `JOptionPane` confirms.
3. Re-add manual Princess SML pairs (pipeline 4).
4. Post-scripts:

```bash
python3 jmri/layouts/hart/scripts/fix_traininfo_detection.py
python3 jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py
```

Operator: [`jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md`](../../jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md).

Facing invert overlay is **not** the END_BUMPER slot hack. Do not drop either without a replacement.

## Do not

- Stage 1 or Store tables from CATS
- `from __future__ import print_function` in `preference:jython/` (breaks stock Dispatcher System)
- Hold a WiThrottle on the same DCC address while AutoActiveTrain owns it
