# Pipeline 4 — Native SML + NX

Layout Editor Discover writes Signal Mast Logic (and NX pairs) into the tables bundle. JMRI re-paths SML on load when `useLayoutEditor=yes`.

**Status:** Live. Last full Discover 2026-08-27: 33 sources / 93 dests; 39 NX pairs. Two Princess dests are manual after every Discover.

NX is **SML mode** (`nxType="signalmastlogic"`). JMRI computes auto-turnouts at runtime (`useLayoutEditor=yes`); they are **not** stored in `tables.xml`. Digicon dests boot **Enabled=no**. Brick pairs without a stored dest use live connectivity.

`ISNX:*` systemNames are frozen CTC numbers (`ISNX:100L` = `NX Mast 2L`). Do not re-run `apply_nx_layer.py` against live tables unless you have pulled `nx_contract.py` — an old copy would mint `ISNX:Mast 2L`.

## Inputs

- LE mast bindings + [`jmri/layouts/hart/data/le_signal_boundaries.csv`](../../jmri/layouts/hart/data/le_signal_boundaries.csv)
- Frozen NX ids: [`jmri/layouts/hart/scripts/nx_contract.py`](../../jmri/layouts/hart/scripts/nx_contract.py)
- Facing: `python3 jmri/layouts/hart/scripts/apply_le_sml_facing.py`
- Stub `END_BUMPER` far-slot hack (keep): [`DISPATCHER_LAYOUT_HOOPS.md`](../DISPATCHER_LAYOUT_HOOPS.md)

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

After Discover, re-add manual Princess pairs (`Mast 36RA→Mast 40LA`, `Mast 36RB→Mast 38LA`). Digicon source dests must stay **Enabled=no** in stored tables until the MQTT publisher enables them.

## Do not

- Run Discover or Store tables from CATS
- Drop the END_BUMPER far-slot bindings
- Expect SML Enable lists to be the MQTT allow-list (that is field `track/signalmast/<packed>`)
