> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

# Project — CATS CTC integration

- **Owner:** lnevo
- **Status:** Active — live desks are **CATS CTC** + **CATS ABS** (Masters), not Gate 1 `HART.xml`
- **ADR:** [`ADR-004-cats-ctc.md`](../../../wiki/decisions/ADR-004-cats-ctc.md)
- **Live wiki:** [`wiki/projects/cats-integration.md`](../../../wiki/projects/cats-integration.md)

## Source of record

| Kind | Live (read-only) | Notes |
|------|------------------|-------|
| CTC hold board | `cats/panels/HART_Master_CTC_hold.xml` | **Live ops CTC** |
| ABS hold board | `cats/panels/HART_Master_ABS_hold.xml` | **Live ops ABS** |
| Geometry sources | `HART_Master.xml`, `HART_Master_ABS.xml` | Rebuild hold copies after edits |
| Gate 1 Designer | `HART.xml`, `HART_Brick.xml`, … | History / experiments — **not ops** |
| System doc | `cats/docs/HART_DIGICON_SYSTEM.md` | Digicon + SML split |

## Locked

- JMRI: current (**5.15.4plus** / ≤5.16 for CATS 3.2)
- CTC **route** authority: **CATS** (`HART_Master_CTC_hold.xml` HOLD_ONLY)
- Signal **aspects**: **JMRI SML** (`hart-aar` / AAR-1946). Without CATS, Unhold = ABS.
- Never run CATS CTC and the USS CTC machine (or Dispatcher System from inside CATS) at the same time.

## Related pipelines

| # | Pipeline | Link |
|---|----------|------|
| 5 | CATS Masters | [cats-masters](../pipelines/cats-masters.md) |
| 3 | Digicon signal beans | [digicon-signal-beans](../pipelines/digicon-signal-beans.md) |
| 4 | Native SML | [native-sml](../pipelines/native-sml.md) |
| — | MQTT mimic QA | [mqtt-mimic](../pipelines/mqtt-mimic.md) |

## Remaining

- Designer as dual-primary: parked unless redraw; do not treat `HART.xml` as live
- Node 13 walk-down done; EH-1/EH-3 MQTT channels swapped vs geographic labels — do not change topics

## Deploy (live — not from consolidation)

```bash
./cats/scripts/sync_hart_package.sh --pi   # add --win / --all when needed
```

Detail: [`cats/README.md`](../../../cats/README.md) · Dispatcher: [`cats/docs/DISPATCHER_GUIDE_CTC.md`](../../../cats/docs/DISPATCHER_GUIDE_CTC.md)
