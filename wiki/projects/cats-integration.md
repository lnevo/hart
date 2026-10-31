# Project — CATS CTC integration

- **Owner:** lnevo
- **Status:** Active — live desks are **CATS CTC** + **CATS ABS**
- **ADR:** [`../decisions/ADR-004-cats-ctc.md`](../decisions/ADR-004-cats-ctc.md)
- **Code/docs:** [`cats/`](../../cats/) · system: [`../../docs/ctc/HART_DIGICON_SYSTEM.md`](../../docs/ctc/HART_DIGICON_SYSTEM.md)

## Locked

- JMRI: current (**5.15.4plus** / ≤5.16 for CATS 3.2)
- CTC **route** authority: **CATS** (`HART_CTC.xml` HOLD_ONLY)
- Signal **aspects**: **JMRI SML** (Basic `two-searchlight` / `one-low`). Without CATS, Unhold = ABS.
- Never run CATS CTC and the USS CTC machine (or Dispatcher System from inside CATS) at the same time.

## Live artifacts

| Path | Role |
|------|------|
| `cats/panels/HART_CTC.xml` | **Live CATS CTC** — routes/turnouts on; signals HOLD_ONLY; SML owns aspects |
| `cats/panels/HART_ABS.xml` | **Live CATS ABS** — HOLD_ONLY; SECSIGNAL bound to JMRI masts (paints SML) |
| `cats/panels/HART_Digicon.xml` | Designer save; the only panel to edit. `wire_digicon.py` builds both desks |

## Notes

Node 13 occupancy walk-down is done (1301=OS Switch 11, 1304=EH-3, 1305=EH-2, 1306=EH-1, 1307=OS Switch 9). EH-1/EH-3 MQTT channels stay swapped vs geographic labels (`Block 13-7` = EH-1, `Block 13-5` = EH-3). Plant map: [`DIGICON_SCHEMATIC.md`](../DIGICON_SCHEMATIC.md).

## Related

- Dispatcher guide: [`../../docs/ctc/DISPATCHER_GUIDE_CTC.md`](../../docs/ctc/DISPATCHER_GUIDE_CTC.md)
- Deploy: `./cats/scripts/sync_hart_package.sh --pi` (add `--win` / `--all`)
