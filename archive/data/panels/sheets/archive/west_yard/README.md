# Archived West Yard sheets

These CATS sheet panels and builders are historical. Live Digicon is Master 4
(`HART_Master4.xml` → `cats/scripts/wire_hart_master4.py`). Do not launch these
as the desk.

Turnout IO (`load_turnouts` / `wire_turnouts`) lives in
`cats/scripts/cats_turnout_io.py`. The old sheet wire is
`wire_hart_sheet_west_yard2.py` in this folder; it no longer writes live
`HART_Master.xml`.

## Duplicates removed (2026-11-26)

These files were byte-identical to another archived file and were deleted. Use the copy named on the right.

| Removed | Same bytes as |
|---|---|
| `HART_sheet_West_Yard2.xml` | `HART_sheet_West_Yard.xml` |
| `checkpoints/HART_sheet_West_Yard2_good_row1.xml` | `checkpoints/HART_sheet_West_Yard_good_row1.xml` |
| `checkpoints/HART_sheet_West_Yard_SOR_pre_signal_declutter.xml` | `checkpoints/HART_sheet_West_Yard_SOR2.xml` |
| `checkpoints/wire_hart_sheet_west_yard2_pre_signal_declutter.py` | `checkpoints/wire_hart_sheet_west_yard2_pre_column_insert.py` |
