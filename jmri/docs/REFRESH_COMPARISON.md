# Refresh vs normal output comparison

**Purpose:** Isolate why the refresh output (from upper_both4.xml) used to trigger an import error in JMRI, and what was fixed.

## Files

| File | Source | Use |
|------|--------|-----|
| **mac_jmri_blocked.xml** | mac_jmri2.xml as panel | Normal run; imports cleanly. |
| **mac_jmri_blocked_refresh.xml** | upper_both4.xml as panel + mac_jmri2.xml as defaults, `use-panel-layout` | Refresh run (AnyRail geometry); now also imports cleanly after fix. |

## Root cause of the import error

When using **use-panel-layout**, the script took the **layout** (track geometry) from the panel file (upper_both4.xml). It also took the **root element** and **jmriversion** from that same file. upper_both4 is an AnyRail export and uses:

- **Schema:** `layout-4-19-2.xsd`
- **jmriversion:** 4.20

The rest of the content (sensors, turnouts, entryexitpairs, etc.) is 5.x-style from the script and from mac_jmri2. Writing a file that declares 4-19-2 but contains 5.x content led JMRI to report an error (e.g. PositionableLabel or schema mismatch).

## Fix applied

1. **Parse defaults (mac_jmri2.xml) early** when building the output, so we have `defaults_root` before constructing the root.
2. **When `use_panel_layout` and defaults_root is not None:** use the defaults file for the output root (schema + jmriversion) instead of the panel file:
   - `out_root = defaults_root` so `new_root` gets 5-5-5 attributes and jmriversion 5.14 from mac_jmri2.
   - Explicitly set `noNamespaceSchemaLocation` to `layout-5-5-5.xsd` so the written file always declares 5-5-5 when refresh is used with defaults.
3. **Layout geometry** still comes from upper_both4 (layout_copy); only the root/schema and jmriversion come from mac_jmri2.

Result: refresh output is now **layout-5-5-5** with **jmriversion 5.14**, so it imports cleanly while still using upper_both4 track geometry.

## Summary of differences (before fix)

| Aspect | mac_jmri_blocked.xml (normal) | mac_jmri_blocked_refresh.xml (before fix) |
|--------|-------------------------------|-------------------------------------------|
| Schema | layout-5-5-5.xsd | layout-4-19-2.xsd |
| jmriversion | 5.14 | 4.20 |
| Layout source | mac_jmri2 | upper_both4 (AnyRail) |
| positionablelabel | 6 text labels from defaults | 0 (all removed to avoid error) |

After the fix, both files use schema **5-5-5** and jmriversion **5.14**; only the LayoutEditor content (track segments, positions) differs because the refresh uses upper_both4 geometry.
