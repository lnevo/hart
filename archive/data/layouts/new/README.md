# Layout: new (next AnyRail export)

Drop the new AnyRail export into **`anyrail/`**.

Suggested steps:

1. Export from AnyRail to `anyrail/<your_export>.xml`.
2. Open in JMRI once if needed; save an authoritative panel to `authoritative/` (turnouts, defaults, hidden tracks).
3. Run `python3 jmri/scripts/build_blocks_excel.py` with paths to your layout XML; move the generated workbook to `data/layout_blocks.xlsx`.
4. Edit `data/block_merges.txt` if needed.
5. Run `apply_blocks_to_panel.py` with `use-panel-layout` when refreshing geometry.

```bash
export JMRI_LAYOUT=new
# Or rename this folder and set JMRI_LAYOUT=<yourname>
```

Copy file naming from **mac** only as a template; filenames inside `authoritative/` and `output/` can match your project (pass explicit CLI paths until you standardize names in `layout_paths.py`).

## Track drawn in JMRI Layout Editor

AnyRail imports usually arrive with `mainline="yes"` on main tracks. **Track you draw in Layout Editor defaults to `mainline="no"`** (sidetrack width).

| Attribute | Effect |
|-----------|--------|
| `mainline="yes"` | `mainlinetrackwidth` (typically 4) — normal main-track appearance |
| `mainline="no"` | `sidetrackwidth` (typically 2) — thinner sidings/industrial |

If new segments or turnouts are not flagged mainline, blocks can appear unassigned or styled differently even when `blockname` is correct.

**After adding trackwork in JMRI:**

1. Assign a block to every segment and turnout (each switch → its own block).
2. Context menu → **Mainline → Yes** on new **track segments** and **turnouts** (match adjacent main track).
3. Add internal block sensors (`ISIS*` system names; userName `Block Sensor N` for track blocks, `BS <turnout ident>` for switch blocks) — see `apply_blocks_to_panel.py` / `process_linear5_new_panel.py` on linear5.
4. Save panel XML to `output/` and sync `reference/` backup if you keep one.

See [`docs/AI_CONTEXT.md`](../../../docs/AI_CONTEXT.md) principles and history (June 2026 linear5 yard lesson).
