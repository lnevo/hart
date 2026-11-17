# Staged for the staging device-map cut-over

The files here take effect only when the staging panel switches to the device-map path
(`tools/schematic/build_staging_candidate.py`, owner approval pending). Nothing live reads them before that, so the live
checks keep reading the files they read today.

| File | Replaces at the cut-over | Written by |
|------|--------------------------|------------|
| `le_signal_boundaries.csv` | `jmri/layouts/hart/data/le_signal_boundaries.csv` | `build_staging_candidate.py`; `--check` says when it is stale |

## le_signal_boundaries.csv

The device-map panel keeps every turnout ident (switches.csv `le_ident`) and leg letter. Its anchors and end bumpers
take generated idents (owner, 2026-11-17), so the six anchor rows name the anchor each mast stands on in that panel
(A45 becomes AG33, A56 AG21, A1 AG6, A48 AG40). Every other column is unchanged. `staged_boundaries()` stops when a
mast is missing, in another kind of slot or on another leg, so only anchor idents can change.

The readers already take the file as an argument, so no reader changes before the cut-over:

```bash
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --tables <candidate> \
    --boundaries jmri/layouts/hart/data/schematic/staged/le_signal_boundaries.csv --generated
python3 jmri/layouts/hart/scripts/apply_le_sml_facing.py --panel <candidate copy> \
    --csv jmri/layouts/hart/data/schematic/staged/le_signal_boundaries.csv --no-sync
```

On the trial with the parked features split out (as the cut-over candidate is), the audit passes with no boundary error.
The facing script changes nothing. `build_layout_le.check_swapped_slots` reads only the turnout rows, which do not
change. The CATS desks and their bindings name no Layout Editor anchor.

At the cut-over, in the same commit as the new tables.xml:

1. Move this file over `jmri/layouts/hart/data/le_signal_boundaries.csv`.
2. Recapture the baselines (`jmri/layouts/hart/scripts/capture_public_name_baseline.py`):
   `baselines/le_mast_bindings.csv` names the anchors by ident.
3. Record the approved panel again (`approved_staging.sha256` holds the anchor idents).
4. Update the docs that name the old anchors (`wiki/pipelines/native-sml.md`, `docs/ctc/SIGNAL_FACING.md` and the
   name map notes for Mast 36L and Track East Lead East).
