# LCOS Layout Inventory v85 (2026-08-22)

Source of truth: hart occupancy + Digicon CSVs (`occupancy_bindings.csv`, `signal_wiring.csv`, `signal_head_plan.csv`, `signal_mast_plan.csv`). Desktop snapshot of v84 is in `docs/wiring/imported/`.

## 2026-08-29 — Node ID = radio Address

Enclosure labels now match the Nodes **Address**: `C2` is radio 2 (East End signals), `C12` is radio 12 (East End turnouts 107–112). Old sequential C1–C13 / D1 IDs are in **Legacy Node ID** (v84 snapshot unchanged). Helix DCC is **D5**. Packed MQTT numbers are unchanged (Plane/Brick heads stay `4xx` on C3). Princess **C1**; overflow **C11**; Barn **C13**; Plane/Brick **C3**.

## 2026-08-28 — 3-pin remap (wiring only; tables.xml not updated)

One `STOP/APPROACH/CLEAR` head per mast (G/Y/R). Packed MQTT node = radio Address. **No D5 (was D1) signal ports** (DCC radio 5). Princess interlocking on **C1**; **36RB + 2035/2036** overflow **C11** (`IH1132`–`IH1134`). East End on **C2** (`IH232`–`IH237`); **OU1 as 5V** (no turnout motors). Barn on **C13**. Plane/Brick **C3** (packed 432/434/436/437/438). Review CSVs before JMRI tables.

## 2026-08-25 — EH-1 / EH-3 occupancy

C5-B3-1 (`Block 13-5` / M2S1304) is **EH-3** (track T11). C5-B4-1 (`Block 13-7` / M2S1306) is **EH-1** (track T9). MQTT ids in Notes are unchanged. Re-run `create_wiring_schematic_ppt.py` (python-pptx) to refresh the C5 slide.

## Changes vs v84
- **BlockSensors (lower deck):** Public names — Scale (was Yard T1), Barn (was Yard T6), S-1…S-5, W-1/W-2, EH-1…EH-3 (by MQTT `Block n-n`, which also unswapped v84’s T9/T11 labels on C5-B3/B4), OS 100… without the turnout-as-block names. Occupancy sensors remain `Block n-n` in Notes.
- **Signals (the v84 “pending revision”):** Overlay Digicon searchlight heads on the ports in `signal_wiring.csv` (C4 Plane/Brick, C1 Barn 117, C7 East End, D1 Princess including new 114LA/115LA). Previous RGB `Sx-y G/Y/R` labels kept in DNOU8 Notes.
- **D1:** Added OU2/OU3 Princess searchlight rows (12 heads).
- **TurnoutSummary:** Lower-deck 100–117 / 110–115 faces named Digicon (100L, 117LA, …). R/Y/G port columns now hold head 1/2/3 ports, not lamp colors.
- **DigiconSignals** sheet generated from the CSVs.
- Regenerated **Wiring_Schematic.pptx**.
- **signals_asbuilt_abs_v2.xlsx** rebuilt from the same CSVs (Digicon names, Scale/Barn, new Princess dwarfs). **Princess** / **all_logic** now include 114LA, 115LA, 114R, 115R (K-1/K-2 westbound + A48 balloon). **signals_split_v8.xlsx** kept as the frozen RGB plan (README sheet added).

## Still true from v84b
- Physical board silk / tape may still show sequential C1–C13; inventory **Legacy Node ID** is that label. MQTT occupancy (`Block n-n`, `M2T12xx`) already used Address.
- Confirm physical board IDs for C13 yard motors/FB (ASSUMED in v84 as C5).
- Upper-deck RGB (`S4-*`…`S6-*`) is still the planned matrix, not Digicon.
