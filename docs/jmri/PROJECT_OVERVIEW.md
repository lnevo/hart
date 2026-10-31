# JMRI Panel / Block Workflow – Project Overview

> **Paths (May 2025):** Scripts live in `jmri/scripts/`. Layouts: **mac** (reference), **linear4** (active), **linear3** (legacy). Per-layout dispatcher: `jmri/layouts/<name>/dispatcher/`. **AI handoff / linear4 / Google Sheets:** [`docs/AI_CONTEXT.md`](../../docs/AI_CONTEXT.md). Mac-focused notes below. See repo root [`README.md`](../../README.md).

This document gives full context for the Panel workspace so a future session (or AI) can pick up where we left off. It covers scripts, the Excel block map, workflows, and what is still pending or disabled.

---

## 1. Project goal and context

- **Goal:** Build and maintain a JMRI panel that has (1) track geometry from AnyRail (e.g. `upper_both4.xml`), (2) block names on every segment and layout turnout from an Excel block map, (3) block occupancy sensors and NX (Entry/Exit) boundary sensors, (4) layout defaults, labels, and hidden tracks from the **authoritative panel** (`mac_jmri2.xml`), and (5) no AnyRail import error when refreshing geometry.
- **Authoritative panel:** `mac_jmri2.xml` – single source for preferences, comments, defaults, labels, hidden tracks, **and the turnouts table**. When refreshing track geometry, **upper_both4.xml** is the track plan (AnyRail export); all other data comes from mac_jmri2.xml. Do not use tables.xml or other legacy files for current data.
- **Output panel:** `mac_jmri_blocked.xml` – full panel with blocks, sensors, layoutblocks, turnouts table, and LayoutEditor (track + defaults/labels/hidden tracks).

---

## 2. Key files (quick reference)

| File | Role |
|------|------|
| **apply_blocks_to_panel.py** | Main script: reads Excel + merge file, applies blocks/sensors/entry-exit to a panel XML; writes `mac_jmri_blocked.xml`. |
| **generate_nx_pairs.py** | Reads `mac_jmri_blocked.xml`, writes **nx_pairs.txt** (Entry/Exit sensor pairs for manual add in JMRI if needed). |
| **build_blocks_excel.py** | Builds **layout_blocks.xlsx** from a layout XML (segment→block, turnout→block, suggested block names). Run once to seed the Excel; then maintain Excel and run apply script. |
| **layout_blocks.xlsx** | Source of truth for block names and segment/turnout→block mapping. |
| **block_merges.txt** | Merge list: `KEEP MERGE_AWAY` (one pair per line). Applied so merged-away blocks disappear and segments/turnouts get the “keep” block name. |
| **mac_jmri2.xml** | Authoritative panel: preferences, comments, defaults, labels, hidden tracks, **turnouts table**. Used as layout source (when not refreshing), as defaults file when refreshing from AnyRail, and as the source for the turnouts table in the output. |
| **upper_both4.xml** | AnyRail export (track plan). Use as panel input with **use-panel-layout** when refreshing track geometry; all other data from mac_jmri2.xml. |
| **mac_jmri_blocked.xml** | Output panel with blocks, sensors, layoutblocks, turnouts, and layout. |
| **tables.xml** | Legacy/example reference only; script does **not** use it for current data. |
| **SENSOR_NUMBERING.md** | Documents sensor systemName/userName schemes (block sensors ISIS1–N, NX sensors ISIS200+). |
| **BLOCK_101_114_NOTE.md**, **BLOCK_ASSIGNMENT_IN_TABLES.md**, **COMPARISON_AND_PLAN.md** | Older notes on block assignment and merging layout from AnyRail vs tables. |

---

## 3. Excel file: layout_blocks.xlsx

### Sheets and usage

| Sheet | Purpose | Used by |
|-------|---------|--------|
| **Segment_to_Block** | Columns: **Track Segment**, **Block #**, **Block Name**. One row per segment→block. | apply_blocks_to_panel.py (load_mappings) |
| **Turnout_to_Block** | Columns: **Turnout**, **Block #**, **Block Name**. One row per layout turnout→block. | apply_blocks_to_panel.py (load_mappings) |
| **Blocks** | Columns: Block #, Block Name, Block Name (suggested long), End 1/2 (turnout or endpoint), legs, Track Segments, Segment Count, **Comments**. Block list and suggested names; script **writes Comments** (turnouts + NX names, no labels). | apply_blocks_to_panel.py (load_block_names; update_blocks_sheet_comments writes Comments) |
| **Turnouts** | Turnout roster (ident, type, throat/normal/diverging). Reference; apply script copies the turnouts table from **mac_jmri2.xml**. | build_blocks_excel.py / reference |

### Block names and merges

- Block names are **Block_1**, **Block_2**, … **Block_N** (from Blocks sheet).
- **block_merges.txt** applies before writing the panel: e.g. `97 114` means merge Block_114 into Block_97. Segment/turnout mappings and the block list are updated so the output has fewer blocks and no references to merged-away blocks.
- After merges, the panel has 175 blocks (as of last run); exact count depends on merge list and Excel.

---

## 4. Scripts: what they do and how to run

### apply_blocks_to_panel.py

- **Purpose:** Apply block names from Excel (+ merges) to a panel; build sensors (block + NX), blocks, layoutblocks, turnouts (from mac_jmri2.xml); set boundary sensors on layout (eastboundsensor/westboundsensor, sensorA/B/C/D); add layout defaults, labels, hidden tracks from a “defaults” file; remove sensor icons from layout; write block/sensor comments to XML and Excel.
- **Inputs:** Panel XML (e.g. `mac_jmri2.xml` or `upper_both4.xml` for geometry refresh), optional output path, optional defaults file, optional `use-panel-layout`.
- **Outputs:** `mac_jmri_blocked.xml` (or second arg); updates **Comments** column in **layout_blocks.xlsx** (Blocks sheet).
- **Dependencies:** `layout_blocks.xlsx`, `block_merges.txt`. Turnouts table from **mac_jmri2.xml** (fallback: defaults file or panel file if mac_jmri2.xml missing).

**Typical runs:**

```bash
# Normal: use authoritative panel as source (mac_jmri2.xml)
python3 apply_blocks_to_panel.py mac_jmri2.xml mac_jmri_blocked.xml

# With defaults from same file (redundant but valid)
python3 apply_blocks_to_panel.py mac_jmri2.xml mac_jmri_blocked.xml mac_jmri2.xml

# Refresh track geometry from AnyRail: upper_both4 = track plan, mac_jmri2 = defaults/labels
python3 apply_blocks_to_panel.py upper_both4.xml mac_jmri_blocked.xml mac_jmri2.xml use-panel-layout
```
When **use-panel-layout** is used, the script uses the **panel file’s layout** (e.g. upper_both4.xml) for track geometry and **mac_jmri2.xml** for defaults, hidden tracks, and (when not stripping labels) labels. upper_both4 is the track geometry refresh source.

### generate_nx_pairs.py

- **Purpose:** Read a blocked panel XML, compute block connectivity and boundary sensors, write valid Entry/Exit (NX) pairs to **nx_pairs.txt** for manual “Add Pair” in JMRI if Auto Generate is insufficient.
- **Run:** `python3 generate_nx_pairs.py [mac_jmri_blocked.xml] [nx_pairs.txt]`
- **Output:** `nx_pairs.txt` – lines like `EntrySensor\tExitSensor`.

### build_blocks_excel.py

- **Purpose:** Parse a JMRI layout XML and build **layout_blocks.xlsx** (Blocks, Segment_to_Block, Turnout_to_Block, Turnouts). Used to seed or regenerate the block map from geometry.
- **Config:** Script has `LAYOUT_FILE` (e.g. `my_layout.xml`) and `EXCEL_FILE` (`layout_blocks.xlsx`). Run once or when layout topology changes; then maintain Excel and use apply_blocks_to_panel.py for daily use.

---

## 5. What the apply script does (detail)

- Reads **layout_blocks.xlsx**: Segment_to_Block, Turnout_to_Block, Blocks (block names list).
- Applies **block_merges.txt** (merge away blocks, update mappings and block list).
- Loads panel XML; if **use-panel-layout** is set, uses the panel file’s layout (e.g. upper_both4 track geometry); otherwise optionally uses **LAYOUT_OVERRIDE_PANEL** (mac_jmri2.xml) to avoid AnyRail import error.
- Sets **blockname** on every tracksegment and layoutturnout that has a mapping.
- Builds **sensors**: Block Sensor 1..N (ISIS1..N), then NX boundary sensors (ISIS200+). Adds **comments** to each sensor (block comment or “blocks using this NX”).
- Copies **turnouts** table from authoritative panel (mac_jmri2.xml); comments on turnouts are stripped so legacy text (e.g. from old tables.xml) does not reappear.
- Builds **blocks** and **layoutblocks** with occupancysensor = Block Sensor N; adds **comments** to blocks (turnouts + NX names, no “Turnouts:”/“Entry/Exit:” labels).
- **Layout copy:** blocknames, set turnoutname=ident, Block 14 link segment, apply **defaults** (from defaults file): layout attributes, layoutTrackDrawingOptions, **labels** (Washington, Bridgeville, etc.), **hidden tracks** (four segments set hidden="yes"), NX boundary sensors (eastboundsensor/westboundsensor, sensorA/B/C/D), remove sensoricons from layout.
- **Entry-exit pairs:** The script **copies** the `<entryexitpairs>` section (and `<signalmastlogics>` if present) from the authoritative panel (mac_jmri2.xml) or from the panel file when no defaults are given. Auto-generated Entry/Exit pairs in mac_jmri2.xml are therefore preserved in mac_jmri_blocked.xml.
- Writes **Comments** column in **Blocks** sheet (same text as block comments in XML).
- Writes output panel XML.

### AnyRail updates and PositionableLabel fix (do not regress)

When you refresh from a new AnyRail export (e.g. replace **upper_both4.xml** and run with **use-panel-layout**), the script keeps the following so JMRI opens the output without error:

- **With use-panel-layout:** The layout is from the panel file (e.g. upper_both4, schema layout-4-19-2). The script **removes all positionablelabel elements** from that layout (`remove_all_positionable_labels`) and **does not add labels from the defaults file**. Labels from the defaults file are layout-5-5-5 format and would cause a **PositionableLabel import error** when written into a 4-19-2 panel. So the output has no positionable labels; you can add labels again in JMRI Layout Editor after opening the panel.
- **Without use-panel-layout:** Only **icon-type** positionable labels are removed (`remove_icon_positionable_labels`); text labels (Washington, Bridgeville, etc.) are still added from the defaults file.

**Do not remove or bypass these steps** when updating the AnyRail file. The defaults file (mac_jmri2.xml) is parsed **once** per run and reused for layout defaults, hidden tracks, and (when not use-panel-layout) labels, so re-exporting AnyRail does not make the script slower.

---

## 6. Pending / disabled / left as-is

- **SIMPLIFY_TURNOUT_NAMES** (apply_blocks_to_panel.py): Set to **False**. If True, would rename turnouts to T1, T2, … and rewrite layout idents accordingly. Left disabled; roster uses full turnout names (e.g. TOL35287).
- **Turnout “on the right side”:** JMRI has a “Set Sensors at Turnout” option for drawing sensors on the right side. We never found an XML attribute for it; layout uses sensorA/B/C only. Sensor icons are not auto-placed; user places them in JMRI and keeps them in the input panel used for layout/defaults.
- **Block 101 / 114:** See **BLOCK_101_114_NOTE.md**. Two blocks at same spur (two bumpers same coords); merge or layout fix is manual if you want one block.
- **Entry/Exit pairs:** The script **copies** the `entryexitpairs` section from the authoritative/defaults panel (e.g. mac_jmri2.xml), so Auto Generate pairs are preserved in the output. **nx_pairs.txt** (from generate_nx_pairs.py) is for manual add if needed.
- **build_blocks_excel.py:** Uses a configurable `LAYOUT_FILE`; may need path update if you regenerate Excel from a different layout file.

---

## 7. Sensor numbering (reference)

See **SENSOR_NUMBERING.md**.

- **Block occupancy:** ISIS1–ISIS*N*, userName **Block Sensor 1** … **Block Sensor N** (N = number of blocks).
- **NX (Entry/Exit):** ISIS200+, userName **NX &lt;ident&gt;** (bumper), **NX &lt;ident&gt;-E/-W** (anchor), **NX &lt;turnout&gt;-A/-B/-C/-D** (turnout leg). Assigned in sorted order by userName.

---

## 8. Where key constants live (for code changes)

- **apply_blocks_to_panel.py:** `DEFAULT_PANEL` (mac_jmri2.xml), `DEFAULT_OUTPUT`, `LAYOUT_OVERRIDE_PANEL` (mac_jmri2.xml), `REFERENCE_FILE` (mac_jmri2.xml — turnouts table source; not tables.xml), `SIMPLIFY_TURNOUT_NAMES`, `EXCEL_FILE`, `MERGE_FILE`, `NX_SENSOR_BASE` (200), Block 14 link idents and segment ident.
- **generate_nx_pairs.py:** `DEFAULT_PANEL`, `DEFAULT_OUT`.
- **build_blocks_excel.py:** `LAYOUT_FILE`, `EXCEL_FILE`.

---

## 9. Handoff checklist for next session

- [ ] Confirm **layout_blocks.xlsx** has correct Segment_to_Block and Turnout_to_Block (and Blocks sheet if you added blocks).
- [ ] Confirm **block_merges.txt** reflects desired merges.
- [ ] After any AnyRail re-export: put new track plan in **upper_both4.xml**, then run with **use-panel-layout** and **mac_jmri2.xml** as defaults so the output has the latest track geometry. The script removes positionable labels when use-panel-layout to avoid import error; do not remove that step.
- [ ] If you enable **SIMPLIFY_TURNOUT_NAMES**, update reference turnouts and layout idents consistently.
- [ ] Block/sensor comments in XML and Excel are generated by the script; don’t rely on hand-edited comments in the input panel (they are replaced by generated text).
