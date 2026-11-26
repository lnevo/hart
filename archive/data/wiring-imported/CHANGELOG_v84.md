# LCOS Layout Inventory v84 (2026-08-07)

Source of truth: linear6 panel (`linear6.xml` + `block_display_names.csv` + `yard_turnout_hardware.json`).

## Changes
- **BlockSensors:** Renamed all lower-deck sections to panel names (Switch 100+, Main East/West, McKees*, Yard Track*, etc.). MQTT `Block N-M` / `M2S*` recorded in Notes.
- **BlockSensors C5:** Added 8 channels (Yard T6/T9/T10/T11, Switch 117–119) for west yard.
- **Unused channels:** Marked Unused where linear6 has no block (e.g. Block 2-2, 3-4, 3-6, 3-8, 12-2).
- **East Main Ext:** Added on C6-B4-1 (Block 4-7 / M2S406).
- **Turnouts:** Renamed SW1–SW18 / SCXA / SCXB → Switch 100–115 on DNOU8 / DNIN8 / TurnoutSummary.
- **Switch 116 (TO1):** Added on C6 OU1-7/8 + FB IN1-7/8 + BTN IN2-4 (`M2T411`).
- **Switch 117–119:** Added on C5 (ASSUMED new OU3 12V + IN1/IN2) from `yard_turnout_hardware.json`.
- **Signals:** Left LED assignments untouched (pending separate revision).
- Regenerated **Wiring_Schematic.pptx** from v84.

## Confirm with physical wiring
1. C5-OU3 / C5-IN1 / C5-IN2 board IDs for yard motors/FB/buttons.
2. C3 hosts Switch 107–110 motors physically while MQTT is node 12 (`M2T12xx`) — confirm board vs address.
3. Switch 100/101/102 port order on C6 (SW1→100, SW2→101, SW3→102).

## v84b clarification (same file)
- **C# ≠ radio address.** Client IDs (C1–C13) are enclosure/board groups; MQTT prefixes (`Block 12-*`, `M2T12xx`, `Switch 12-n`) use the Nodes **Address** (radio address): C1=1, C2=12, C3=2, C4=3, C5=13, C6=4.
- Moved Switch **107–110** motors/FB/buttons from C3 → **C2** (radio addr 12). C3 (addr 2) is block-detection only for the linear6 turnout set.
- C2: OU1 = 107–110; OU4 (assumed) = 111–112; IN1/IN3 FB; IN2 buttons.
