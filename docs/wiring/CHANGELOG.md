# LCOS Layout Inventory v85 (2026-08-22)

Source of truth: hart occupancy + Digicon CSVs (`occupancy_bindings.csv`, `signal_wiring.csv`, `signal_head_plan.csv`, `signal_mast_plan.csv`). Desktop snapshot of v84 is in `docs/wiring/imported/`.

## Changes vs v84
- **BlockSensors (lower deck):** Public names — Scale (was Yard T1), Barn (was Yard T6), S-1…S-5, W-1/W-2, EH-1…EH-3 (by MQTT `Block n-n`, which also unswapped v84’s T9/T11 labels on C5-B3/B4), OS 100… without the turnout-as-block names. Occupancy sensors remain `Block n-n` in Notes.
- **Signals (the v84 “pending revision”):** Overlay Digicon searchlight heads on the ports in `signal_wiring.csv` (C4 Plane/Brick, C1 Barn 117, C7 East End, D1 Princess including new 114LA/115LA). Previous RGB `Sx-y G/Y/R` labels kept in DNOU8 Notes.
- **D1:** Added OU2/OU3 Princess searchlight rows (12 heads).
- **TurnoutSummary:** Lower-deck 100–117 / 110–115 faces named Digicon (100L, 117LA, …). R/Y/G port columns now hold head 1/2/3 ports, not lamp colors.
- **DigiconSignals** sheet generated from the CSVs.
- Regenerated **Wiring_Schematic.pptx**.
- **signals_asbuilt_abs_v2.xlsx** rebuilt from the same CSVs (Digicon names, Scale/Barn, new Princess dwarfs). **Princess** / **all_logic** now include 114LA, 115LA, 114R, 115R (K-1/K-2 westbound + A48 balloon). **signals_split_v8.xlsx** kept as the frozen RGB plan (README sheet added).

## Still true from v84b
- **C# ≠ radio address.** Client IDs are enclosure/board groups; MQTT packed IDs use the Nodes **Address**.
- Confirm physical board IDs for C5 yard motors/FB (ASSUMED in v84).
- Upper-deck RGB (`S4-*`…`S6-*`) is still the planned matrix, not Digicon.
