# Why Designer is required for HART CTC

Hand-authored `TRACKPLAN` XML for Brick caused:

- `multiple Block definitions` / SecEdge boundary mismatches  
- `VitalLogic is null` NPEs when MQTT feedback fired early  
- `ClassCastException` during vital-logic wiring  

CATS expects panels created (or heavily edited) in **Designer**, which emits correct edge/block/switch topology.

## Working approach

1. Open **Designer**: `./cats/scripts/launch_designer.sh`
2. File → Open `cats/panels/HART_smoke_Armstrong.xml` (or New)
3. Redraw Neville Island west→east; save as `cats/panels/HART.xml`
4. Bind occupancy / turnouts using `cats/docs/BRICK_BINDINGS.md` and the CSVs
5. Open that file in CATS (`./cats/scripts/launch_cats.sh`)

## Smoke test (should paint track)

`cats/panels/HART_smoke_Armstrong.xml` — Armstrong magnet board with HART section labels and Operations connect off. If this is blank/crashes, the problem is the CATS install, not our Brick geometry.
