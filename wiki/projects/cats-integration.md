# Project — CATS CTC integration

- **Owner:** lnevo
- **Status:** Active — Brick first (ADR-004 **Accepted**)
- **ADR:** [`../decisions/ADR-004-cats-ctc.md`](../decisions/ADR-004-cats-ctc.md)
- **Code/docs:** [`cats/`](../../cats/)

## Locked

- JMRI: current (**5.15.4plus** / ≤5.16 for CATS 3.2)
- CTC command authority: **CATS**
- First plant: **Brick**

## Artifacts

| Path | Role |
|------|------|
| `cats/panels/HART_Brick.xml` | Starter Digicon panel (MQTT-bound Brick strip) |
| `cats/docs/BRICK_BINDINGS.md` | Cheat-sheet |
| `cats/scripts/launch_*.sh` | Designer / CATS launchers |

## Next

- [ ] Live test: occupy `Block 4-2` → CATS colors OS 100
- [ ] Live test: throw Switch 100 from CATS → MQTT motor
- [ ] Polish topology in Designer if grid geometry needs fix
- [ ] Expand to Plane → East End → Princess
