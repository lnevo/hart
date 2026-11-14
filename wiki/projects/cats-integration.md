# Project — CATS CTC integration

- **Owner:** lnevo
- **Status:** Active — live desks are **CATS CTC** + **CATS ABS**
- **ADR:** [`../decisions/ADR-004-cats-ctc.md`](../decisions/ADR-004-cats-ctc.md)
- **Code/docs:** [`cats/`](../../cats/) · system: [`../../docs/ctc/HART_DIGICON_SYSTEM.md`](../../docs/ctc/HART_DIGICON_SYSTEM.md)

## Locked

- JMRI: current (**5.16**, the newest CATS 3.2 supports)
- CTC **route** authority: **CATS** (`HART_CTC.xml` HOLD_ONLY)
- Signal **aspects**: **JMRI SML** (Basic `two-searchlight` / `one-low`). Without CATS, Unhold = ABS.
- Never run CATS CTC and the USS CTC machine (or Dispatcher System from inside CATS) at the same time.

## Upgrading JMRI

`jmri/resources/jmri-web/servlet/home/Home.html` is a full copy of stock JMRI 5.16's `web/servlet/home/Home.html` plus one HART block (STS, LCOS Mimic and Speed-match live links under Utilities). The installer (`cats/scripts/install_jmri_web_override.sh`) puts it in `JMRI_UserFiles/web/servlet/home/`, where it shadows the stock page. After an upgrade the new stock home page stays hidden until the copy is rebased:

1. Diff the new stock `web/servlet/home/Home.html` (from the JMRI tag, e.g. `~/dev/JMRI`) against our copy.
2. Start from the new stock file and carry the HART block onto it.
3. Keep the two `var HART_APPS_HOST = "";` and `var HART_MIMIC_PORT = "";` lines exactly as written; the installer fills them with sed.
4. Update the "based on stock JMRI" comment at the top of the block to the new version.
5. Run `python3 -m unittest discover -s cats/scripts/tests`, then deploy.

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
- Deploy: `./tools/hosts/sync_hart_package.sh --pi` (add `--win` / `--all`)
