# linear4 panel assets

## Background image

`linear4_panel_bg.png` — 1280×320 light blue panel with a river-style band along the bottom edge (waves, gold horizon rule, tie ticks).

Regenerate:

```bash
python3 jmri/scripts/generate_linear4_panel_background.py
python3 jmri/scripts/build_linear4_device_mapping.py --write-panel --write-prod-panel --dcc-label-placement split
```

Production panel (linear4 + LogixNG from live `tables.xml`): **`output/linear4_prod.xml`**

### Install into JMRI (optional)

Generated panel XML uses **RGB background only** so it loads without this file. To add the river graphic, copy the PNG into JMRI **preferences** and add the image in the Layout Editor (or reference `preference:/linear4_panel_bg.png`):

**macOS (typical):**

```bash
cp jmri/layouts/linear4/assets/linear4_panel_bg.png \
   ~/Library/Preferences/JMRI/linear4_panel_bg.png
```

If that folder does not exist, open JMRI → **Edit** → **Preferences** → note the **User Files Location**, then copy the PNG there.

Generated panel XML uses the light blue **RGB** background on `LayoutEditor` only (no embedded `preference:` image label), so the file loads cleanly before you copy the PNG. After installing the PNG, you can add the image in the Layout Editor if you want the river graphic on top of the RGB fill.
