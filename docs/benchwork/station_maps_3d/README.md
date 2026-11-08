# 3D-printed station maps

Multi-colour fascia plates that hold Touch Toggles. Barn is first; it follows
`ops/station_maps/scripts/render_barn_station_map.py`.

```bash
./docs/benchwork/station_maps_3d/build.sh   # writes stl/barn_*.stl and stl/sw13_*.stl
```

## Printing (Spark i7 + 4-colour AMS, Creality Print)

1. Add all four STLs in one go and choose to load them as one object with multiple parts. They share an origin, so do not move them apart.
2. Assign white, black, teal and gold to the parts.
3. Print as loaded, face down on a smooth plate, with no supports. Use 0.2 mm layers or finer so the 0.6 mm inlay gets at least three layers.

After a rebuild, use **Reload from disk**.

STL has no units, and the slicer treats a part under about 9 mm³ as inches. Keep every
colour above that; `build.sh` fails if one is not.

## Fit

Everything to confirm is at the top of `station_map_barn.scad`.

| Item | Current value | Status |
|------|---------------|--------|
| Plate outline | 202.7 × 126.5 mm (5 × 8 in less 0.5 mm) | Placeholder until the frame is measured |
| Plate thickness | 3.0 mm | Placeholder until the frame rabbet is measured |
| Toggle pocket | 19.45 mm square, 1.8 mm deep | Face from the drawing; depth is a guess |
| LED/sensor hole | 4.96 mm (3/16 in plus 0.2) | From the drawing plus clearance |
| Skin at pockets | 1.2 mm | Follows from thickness and pocket depth |

## Switch 7

The two-light toggle's 3/8 in hole pitch sets the crossover dot pitch, so its
pocket is turned to the crossover slope. The toggle takes the top and middle
dots and the third hole is the indicator; `indicator_dot` swaps it to the top.
Main East sits 0.17 in higher than on the paper sheet as a result.

## SW13 test panel

`toggle_test_sw13.scad` is a 2 × 2 in panel with one one-light toggle and SW13 on the
face. It tests pocket fit, crush-rib retention and touch through a 1.0 mm skin
before the next station map. Barn's first print was cancelled (its first-layer
lettering did not stick), so none of that is proven yet.

- **One colour:** print `sw13_body.stl` alone. SW13 is recessed 0.6 mm into the face.
- **Two colour:** load `sw13_body.stl` and `sw13_letters.stl` as one object; the
  letters fill the recess. They are on the first layer, as on Barn, but at 8 mm
  Arial Black rather than 3.6 mm.
- Face down, no supports. Mount with double-sided tape: the back is flat and the
  toggle sits 0.4 mm below it. The ribbon leaves through a 13 mm slot in the
  bottom edge, wide because its position varies from toggle to toggle.

| Item | Value |
|------|-------|
| Plate | 50.8 × 50.8 × 6.5 mm, 3 mm corner radius |
| Skin over toggle | 1.0 mm, LED hole 4.96 mm |
| Pocket | 18.0 mm square (toggle + 0.3), 5.5 mm deep |
| Crush ribs | 6 × Ø1.0, 0.35 proud (0.2 mm interference a side), 1 mm lead-in at the back |

## Touch Toggle measurements (calipers, 2026-11-07)

The spec drawing (`docs/ops/Toggle_Dimensions.png`) gives a 3/4 in (19.05 mm) square;
the real bodies are smaller. Use these sizes for pockets and the drawing for LED
size and pitch.

| Part | Measured | From the drawing |
|------|----------|------------------|
| One-light body | 17.7 × 17.7 × 5.1 mm, rounded edges, < 0.1 mm seam flash | LED Ø4.76 (3/16 in), centred |
| One-light wires | 3-wire ribbon 3.8 × 1.4 mm out of the bottom edge, 5.6 mm free left / 8.3 mm right (varies; hand-assembled) | |
| Two-light body | 17.7 × 17.7 × 5.1 mm | Two LEDs Ø4.76, 9.53 mm (3/8 in) pitch, centred |
| Third-light housing | 18.2 × 18.2 × 5.8 mm; wire out of the bottom, centred below its LED | LED Ø4.76, 9.53 mm on from the two-light's second LED |
| Two-light + third light | 28.6 × 18.2 mm joined; the toggle friction-fits a ~7.3 mm cutout in the housing. Faces flush, housing 0.7 mm deeper at the back; the exposed toggle steps in to 17.7 wide | |

Barn's 19.45 mm pockets came from the drawing, so they are about 1.75 mm too big
for these bodies.
