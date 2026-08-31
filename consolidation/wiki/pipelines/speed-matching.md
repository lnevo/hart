> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record (consolidation view)

| Kind | Live path (read-only) | Proposed consolidation path |
|------|----------------------|----------------------------|
| Runbook | `wiki/pipelines/speed-matching.md` | `consolidation/wiki/pipelines/speed-matching.md` |
| Artifacts | See live guide below | `consolidation/sor/` when promoted |

---

# Pipeline 11 — Speed matching

Measured DecoderPro speed profiles so Dispatcher System station stops are realistic.

**Status:** Parked. Every live roster loco currently has the same **synthetic** 10-step / 400 mm/s profile (`ensure_dispatcher_roster_profiles.py`). Replace with measured tables when the circle is ready.

## Inputs

- Club SOP + scripts under [`jmri/docs/speedmatching/`](../../jmri/docs/speedmatching/)
- Detected loop (scripts are N-scale Kato 19″ / BDL168 `LS1`–`LS12` — **adapt** for HART)

## Outputs

- Roster speed profile on each DecoderPro loco

## Run

Project notes: [`wiki/projects/speedmatching.md`](../projects/speedmatching.md). Load **Matching**, then **Measuring** (reverse order errors).

Do not run the stock STRR geometry against HART without changing sensors, piece count, radius, and scale.
