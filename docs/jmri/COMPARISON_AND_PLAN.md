# JMRI Panel Comparison: upper_both3.xml vs tables.xml

## Overview

- **upper_both3.xml** – Layout exported from AnyRail. Minimal panel options; geometry is the “source of truth” for the track plan.
- **tables.xml** – Your main JMRI panel (layout name in file: **"Full Layout"**). Contains your sensors, turnouts, blocks, and all panel customizations.

Goal: Use **layout geometry from AnyRail** (upper_both3.xml) while keeping **panel options, colors, turnout settings, and your overlays** from tables.xml, so re-exporting from AnyRail doesn’t wipe your customizations.

---

## 1. File structure comparison

| Aspect | upper_both3.xml | tables.xml |
|--------|------------------|------------|
| **JMRI version** | 4.20 | 5.12 |
| **Schema** | layout-4-19-2.xsd | layout-5-5-5.xsd |
| **Layout name** | `upper_both3` | `Full Layout` |
| **Format** | Single long line (minified) | Pretty-printed |
| **Content before LayoutEditor** | Only `<jmriversion>` | Full panel: sensors, turnouts, blocks, signal mast logics, timebase, etc. |

So: **tables.xml** is the full JMRI panel; **upper_both3** is effectively “layout only” (version + one LayoutEditor with geometry).

---

## 2. Layout geometry (track + turnouts)

| Element | upper_both3.xml | tables.xml |
|---------|------------------|------------|
| **Track segments** | 381 | 422 (includes same topology; some segments may be split or formatted differently) |
| **Layout turnouts** | 65 | 65 |
| **Anchor idents** | Same set (e.g. A1, A10, … A218, A227, …) | Same set |

The two files describe the **same layout**: same anchor points and turnout idents (e.g. TOL35287, TOR35230, TO_CO34946). So we can treat upper_both3 as the “as-is” layout and tables as “same layout + your options and overlays.”

---

## 3. Panel options (what you want from tables.xml)

**LayoutEditor attributes** – tables.xml has many; upper_both3 has only a few.

**From tables.xml (keep these):**

- **Display:** `sliders`, `scrollable`, `drawgrid`, `snaponadd`, `snaponmove`, `antialiasing`, `showhelpbar`, `tooltipsnotedit`, `tooltipsinedit`
- **Track style:** `mainlinetrackwidth`, `sidetrackwidth`, `defaulttrackcolor`, `defaultoccupiedtrackcolor`, `defaultalternativetrackcolor`, `defaulttextcolor`
- **Turnout display:** `turnoutcircles`, `turnoutcirclecolor`, `turnoutcirclethrowncolor`, `turnoutfillcontrolcircles`, `turnoutcirclesize`, `turnoutdrawunselectedleg`, `turnoutbx`, `turnoutcx`, `turnoutwid`
- **Crossovers:** `xoverlong`, `xoverhwid`, `xovershort`
- **Panel behavior:** `autoblkgenerate`, `redBackground`, `greenBackground`, `blueBackground`, `gridSize`, `gridSize2nd`, `openDispatcher`, `useDirectTurnoutControl`
- **Window/position:** `x`, `y`, `windowheight`, `windowwidth`, `panelheight`, `panelwidth`

**layoutTrackDrawingOptions** (tables.xml lines 472–496):

- Full track-drawing options: main/side ballast, rail, tie colors and dimensions, block line dash/width, etc.
- This block exists only in tables.xml; upper_both3 has none.

So: **Panel options and track style** should come from tables.xml; **layout geometry** (track segments, turnouts, anchors, level crossings, etc.) from upper_both3.xml.

---

## 4. Your custom overlays (keep from tables.xml)

These exist only in tables.xml and should be preserved:

- **BlockContentsIcon** – Block 4-1 at (60, 440)
- **Positionable labels:** Washington, Scully Yard, Bridgeville, To Helix Outer, To Helix Inner, Neville's Island

When merging, we keep these after inserting the layout from upper_both3.

---

## 5. Schema / format differences

- **Turnout elements:** upper_both3 uses a single `LayoutTurnoutXml` style (with attributes like `xcen`, `yb`, `xc`, `yc`); tables.xml uses specific types (`LayoutLHTurnoutXml`, `LayoutRHTurnoutXml`, `LayoutDoubleXOverXml`) with extra coordinates (`xa`, `ya`, `xd`, `yd`). JMRI 5.x may expect the more specific form, so we may need to keep turnout *geometry* from upper_both3 but ensure the element names/attributes match what tables.xml (and the 5.5.5 schema) expect.
- **Version:** Merged file should remain JMRI 5.12 and layout-5-5-5.xsd (from tables.xml).
- **One small difference:** In tables.xml the first track segment `F35585-S-0` has `hidden="yes"`; in upper_both3 it has `hidden="no"`. So at some point you (or JMRI) hid that segment. We can either keep your choice (hidden) or follow AnyRail (visible); the plan below assumes we keep your overlays and options and can document this as the one “slight exception” if you want to keep that segment hidden.

---

## 6. What to do next (options)

### Option A – Merge script (recommended for “isolate” and reuse)

- **Inputs:**  
  - `upper_both3.xml` (or a future AnyRail export) → layout geometry only.  
  - `tables.xml` → panel options, layoutTrackDrawingOptions, your overlays (labels, BlockContentsIcon), and everything outside the LayoutEditor (sensors, turnouts, blocks, etc.).
- **Output:** One merged panel file (e.g. `tables.xml` or `merged_panel.xml`) where:
  - Root, jmriversion, and all content **before** the LayoutEditor come from tables.xml.
  - LayoutEditor opening tag uses **attributes from tables.xml** (all panel options).
  - First child of LayoutEditor: **layoutTrackDrawingOptions** from tables.xml.
  - Next: **Your overlays** (BlockContentsIcon, positionablelabels).
  - Next: **Layout geometry** from upper_both3: layoutturnouts, tracksegments, and any anchors/level crossings (and optionally preserve your `hidden="yes"` for `F35585-S-0` if we decide to).
  - All content **after** the LayoutEditor (and closing `</layout-config>`) from tables.xml.
- **Result:** Whenever you get a new AnyRail export, you run the script with the new file and your current tables.xml; your options and overlays stay, layout updates from AnyRail.

### Option B – Manual / documented merge

- Document exactly which blocks of tables.xml are “layout geometry” (turnouts + track segments) and which are “panel options + overlays.”
- When you receive a new AnyRail export, you manually replace only the geometry block in tables.xml and leave the rest untouched. No script, but more error-prone.

### Option C – Two-file workflow

- Keep a “layout only” file (e.g. from AnyRail) and a “panel preferences” file (options + overlays only), and a small script or instructions that combine them into the final panel. This is a variant of A with a more explicit split of files.

---

## 7. Recommendation and what I need from you

- **Recommendation:** Implement **Option A**: a small script (e.g. Python) that merges layout from upper_both3.xml with panel options and overlays from tables.xml, and writes the result to a target file (e.g. tables.xml or a new name). Then you can re-run it whenever you get a new AnyRail export.
- **To proceed I need you to confirm:**
  1. Use **tables.xml** as the source for panel options and overlays and **upper_both3.xml** as the source for layout geometry (as above)?
  2. Keep the merged panel as JMRI 5.12 / layout-5-5-5 (i.e. keep tables.xml as the “base” for everything except layout geometry)?
  3. For the first track segment (`F35585-S-0`): keep it **hidden** (as in current tables.xml) or use **visible** (as in upper_both3)?
  4. Layout name in the merged file: keep **"Full Layout"** or switch to **"My Layout"** (or something else)?
  5. Output: overwrite **tables.xml** or write to a **new file** (e.g. `merged_panel.xml`) so you can compare before replacing?

Once you confirm these, the next step is to implement the merge script and, if needed, handle the JMRI 4.x → 5.x turnout element format so the merged file loads correctly in JMRI 5.12.
