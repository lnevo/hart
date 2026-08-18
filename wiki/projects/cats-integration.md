# Project — CATS CTC integration

- **Owner:** lnevo
- **Status:** Active — Brick first (ADR-004 **Accepted**)
- **ADR:** [`../decisions/ADR-004-cats-ctc.md`](../decisions/ADR-004-cats-ctc.md)
- **Code/docs:** [`cats/`](../../cats/)

## Locked

- JMRI: current (**5.15.4plus** / ≤5.16 for CATS 3.2)
- CTC **route** authority: **CATS** (`HART_Master_CTC_hold.xml` HOLD_ONLY)
- Signal **aspects**: **JMRI SML** (AAR-1946). Without CATS, Unhold = ABS.
- First plant: **Brick**

## Artifacts

| Path | Role |
|------|------|
| `cats/panels/HART.xml` | **Primary** Designer Gate 1 + MQTT |
| `cats/panels/HART_le.xml` | LE WIP Gate 1–5 schematic + MQTT |
| `cats/panels/HART_Brick.xml` | Starter Digicon panel (MQTT-bound Brick strip) |
| `cats/docs/BRICK_BINDINGS.md` | Cheat-sheet |
| `cats/scripts/launch_*.sh` | Designer / CATS launchers |

## Next

- [ ] Live test Gate 1: occupy `Block 4-6` → red on HORIZONTAL Block 100-102 only
- [ ] Live test Gate 1: occupy `Block 4-2` → CATS colors OS 100
- [ ] Live test: throw Switch 100 from CATS → MQTT motor (points IO not wired yet)
- [ ] Mac-accept `HART_le.xml` Gate 2 (EME / 117b / Main East / 118 / 119)
- [ ] Expand Designer draw Gates 3–5 or promote LE board after accept
