# Project — CATS CTC integration

- **Owner:** lnevo
- **Status:** Active — live desks are **CATS CTC** + **CATS ABS** (Masters), not Gate 1 `HART.xml`
- **ADR:** [`../decisions/ADR-004-cats-ctc.md`](../decisions/ADR-004-cats-ctc.md)
- **Code/docs:** [`cats/`](../../cats/) · system: [`../../cats/docs/HART_DIGICON_SYSTEM.md`](../../cats/docs/HART_DIGICON_SYSTEM.md)

## Locked

- JMRI: current (**5.15.4plus** / ≤5.16 for CATS 3.2)
- CTC **route** authority: **CATS** (`HART_Master_CTC_hold.xml` HOLD_ONLY)
- Signal **aspects**: **JMRI SML** (`hart-aar` / AAR-1946). Without CATS, Unhold = ABS.
- Never run CATS CTC and the USS CTC machine (or Dispatcher System from inside CATS) at the same time.

## Live artifacts

| Path | Role |
|------|------|
| `cats/panels/HART_Master_CTC_hold.xml` | **Live CATS CTC** — routes/turnouts on; signals HOLD_ONLY; SML owns aspects |
| `cats/panels/HART_Master_ABS_hold.xml` | **Live CATS ABS** — HOLD_ONLY; SECSIGNAL bound to JMRI masts (paints SML) |
| `cats/panels/HART_Master.xml` | CTC geometry source (rebuild hold copy after edits) |
| `cats/panels/HART_Master_ABS.xml` | ABS geometry source (unbound; hold copy is what launches) |

Gate 1 Designer files (`HART.xml`, `HART_Brick.xml`, `HART_le.xml`, `HART_ctc.xml`) are history / experiments, not the ops board.

## Remaining

- [ ] Designer as dual-primary: leave parked unless we redraw; do not treat `HART.xml` as live
- [ ] Node 13 occupancy walk-down (hardware: 1301=118, 1304–1306=house, 1307=119)
- [ ] Master 4 schematic parked on `human/master4`; mapping in [`MASTER4_SCHEMATIC.md`](../MASTER4_SCHEMATIC.md). Live desks are pre-Master 4.

Gate 1 occupancy color checks (`Block 4-6` / `Block 4-2`) and Switch 100 throws from CATS were overtaken by the Master board + native SML QA (30/30). Re-open only if a plant mis-paints.

## Related

- Dispatcher guide: [`../../cats/docs/DISPATCHER_GUIDE_CTC.md`](../../cats/docs/DISPATCHER_GUIDE_CTC.md)
- Deploy: `./cats/scripts/sync_hart_package.sh --pi` (add `--win` / `--all`)
