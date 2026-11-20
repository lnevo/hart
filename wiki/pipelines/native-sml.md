# Pipeline 4 — Native SML + NX

Layout Editor Discover writes Signal Mast Logic (and NX pairs) into the tables bundle. JMRI re-paths SML on load when `useLayoutEditor=yes`.

**Status:** Signal Mast Logic is live. The NX pairs are parked: since the helix-join release (November 2026): not in the active panel; data kept in `jmri/layouts/hart/parked/`. The NX parts below apply once unparked. Current tables hold 82 sources / 180 dests (all from Discover; counted 2026-11-17, after the device-map switch-over); the parked file holds the 36 NX pairs (re-Discovered from an empty list 2026-11-15 after NX Mast 8RA moved to A45 east).

NX is **SML mode** (`nxType="signalmastlogic"`). JMRI computes auto-turnouts at runtime (`useLayoutEditor=yes`); they are **not** stored in `tables.xml`. Digicon dests boot **Enabled=no**. Brick pairs without a stored dest use live connectivity.

`ISNX:*` systemNames are frozen CTC numbers (`ISNX:100L` = `NX Mast 2L`). Do not re-run `jmri/layouts/hart/parked/apply_nx_layer.py` against live tables unless you have pulled `nx_contract.py` — an old copy would mint `ISNX:Mast 2L`.

## Inputs

- LE mast bindings + [`jmri/layouts/hart/data/le_signal_boundaries.csv`](../../jmri/layouts/hart/data/le_signal_boundaries.csv)
- Frozen NX ids: [`jmri/layouts/hart/scripts/nx_contract.py`](../../jmri/layouts/hart/scripts/nx_contract.py)
- Facing: `python3 jmri/layouts/hart/scripts/apply_le_sml_facing.py`
- Stub `END_BUMPER` mast slots: [`DISPATCHER_LAYOUT_HOOPS.md`](../DISPATCHER_LAYOUT_HOOPS.md)

## Outputs

- SML dests in `jmri/layouts/hart/output/tables.xml`
- `ISNX:*` pairs (systemNames frozen)

## Run

```bash
# PanelPro, not CATS. Modal dialogs — do not hide them.
./jmri/layouts/hart/scripts/run_sml_discover.sh
# wrapper also: python3 jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py
./jmri/layouts/hart/scripts/run_nx_discover.sh   # if NX needs a refresh
```

Signal logic is checked by running stock Discover / Stage 1 in the sandbox rehearsal and comparing the stored pairs with the previous tables (`data/baselines/sml_pairs.csv`); the home-made prediction script was retired on 2026-11-16. Every SML dest comes from Discover; there are no manual pairs. The two Princess pairs `Mast 36RA→Mast 40LA` and `Mast 36RB→Mast 38LA` were retired on 2026-11-15: Discover refuses them ("Signal mast in the wrong direction") because 40LA and 38LA are westbound homes and 36RA/36RB govern eastbound, and no section, NX pair or route used them ([`DISPATCHER_LAYOUT_HOOPS.md`](../DISPATCHER_LAYOUT_HOOPS.md)). Digicon source dests must stay **Enabled=no** in stored tables until the MQTT publisher enables them.

The PanelPro wrappers share `tools/hosts/panelpro_session.sh`: every Start Up item that runs code is off for the run except a short allowlist (`tools/hosts/panelpro_profile.py`), the PanelPro they started is stopped on a timeout, Ctrl-C or SIGTERM, and the profile comes back from `profile.xml.hart-run.bak`. After a `kill -9`, quit that PanelPro and run `python3 tools/hosts/panelpro_profile.py restore --profile <profile.xml>`; until then the wrappers, deploy and `launch_cats.sh` refuse. NX Discover paints every occupancy sensor INACTIVE in PanelPro before discovery (no MQTT publish, but JMRI's own listeners react), so run it with the layout idle. The Brick smoke is opt-in (`HART_NX_SMOKE=1`); `HART_NX_THROW=1` with it sets a real route and commands MQTT turnouts. Rehearsal steps on a copy of the profile are in the header of `panelpro_session.sh`.

## Do not

- Run Discover or Store tables from CATS
- Move the END_BUMPER mast bindings
- Expect SML Enable lists to be the MQTT allow-list (that is field `track/signalmast/<packed>`)
