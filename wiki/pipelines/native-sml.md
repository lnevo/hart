# Pipeline 4 — Native SML + NX

Layout Editor Discover writes Signal Mast Logic (and NX pairs) into the tables bundle. JMRI re-paths SML on load when `useLayoutEditor=yes`.

**Status:** Live. Current tables hold 40 sources / 100 dests and 39 NX pairs. Two Princess dests are manual after every Discover.

NX is **SML mode** (`nxType="signalmastlogic"`). JMRI computes auto-turnouts at runtime (`useLayoutEditor=yes`); they are **not** stored in `tables.xml`. Digicon dests boot **Enabled=no**. Brick pairs without a stored dest use live connectivity.

`ISNX:*` systemNames are frozen CTC numbers (`ISNX:100L` = `NX Mast 2L`). Do not re-run `apply_nx_layer.py` against live tables unless you have pulled `nx_contract.py` — an old copy would mint `ISNX:Mast 2L`.

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
python3 jmri/layouts/hart/scripts/validate_le_signalling.py
```

The PanelPro wrappers share `tools/hosts/panelpro_session.sh`: the publishing Start Up scripts are off for the run, the PanelPro they started is stopped on a timeout, Ctrl-C or SIGTERM, and the profile comes back from `profile.xml.hart-run.bak`. After a `kill -9`, quit that PanelPro and run `python3 cats/scripts/patch_jmri_startup.py restore --profile <profile.xml>`. The NX smoke (`HART_NX_SMOKE=1`, default) paints sensor states in PanelPro only and publishes nothing; `HART_NX_THROW=1` sets a real route and commands MQTT turnouts. For a rehearsal profile set `JMRI_PROFILE_XML` (and `JMRI_USER_FILES` if the profile does not say).

After Discover, re-add manual Princess pairs (`Mast 36RA→Mast 40LA`, `Mast 36RB→Mast 38LA`): `restore_manual_sml_pairs.py --reference <tables before Discover>` (the Stage 1 wrapper does this itself). Digicon source dests must stay **Enabled=no** in stored tables until the MQTT publisher enables them.

## Do not

- Run Discover or Store tables from CATS
- Move the END_BUMPER mast bindings
- Expect SML Enable lists to be the MQTT allow-list (that is field `track/signalmast/<packed>`)
