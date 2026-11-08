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

Sizes come from the caliper table below and the method proven on the SW13 test panel.

| Item | Value | Status |
|------|-------|--------|
| Plate outline | 202.7 × 126.5 mm, 3 mm corner radius | Placeholder until the frame is measured |
| Plate thickness | 7.0 mm | 1.0 skin + 5.8 third-light housing + 0.2 gap; placeholder until the frame depth is known |
| Toggle pocket | 18.0 mm square (toggle + 0.3), 6.0 mm deep | Measured; SW13 test fit |
| Crush ribs | Ø1.0, 0.35 proud, 1 mm lead-in | As the SW13 test |
| LED hole | 4.96 mm (3/16 in plus 0.2) | From the drawing |
| Skin over toggles | 1.0 mm (0.4 mm under inlaid ink) | As the SW13 test |
| Wire channels | 13 mm wide, full pocket depth, out through the plate edge | SW9, SW13 down; SW11 east; SW7 along the crossover |

Mounting is double-sided tape on the flat back. The ribbon position varies from toggle to toggle, hence the wide channels.

## Switch 7

The two-light toggle's 3/8 in hole pitch sets the crossover dot pitch, so its
pocket is turned to the crossover slope. The toggle takes the top and middle
dots and the third hole is the indicator; `indicator_dot` swaps it to the top.
The pocket is one 28.6 × 18.2 mm shape covering toggle and housing, with ribs on
both ends and one channel out the side for both wires. The 28.6 mm length is the
caliper figure for the joined assembly; the third LED sits 14.3 mm from the
toggle centre, so check how the housing sits on a real toggle before printing.
Main East sits 0.17 in higher than on the paper sheet as a result.

## SW13 test panel

`toggle_test_sw13.scad` is a 2 × 2 in panel with one one-light toggle. The face has
a horizontal main through the switch, a spur diverging north-west at 45° and
then running west, a ring round the LED, and SW13 in the upper right. It tests pocket fit, crush-rib retention and touch through a 1.0 mm skin
before the next station map. Barn's first print was cancelled (its first-layer
lettering did not stick), so none of that is proven yet.

- **One colour:** print `sw13_body.stl` alone. Track and SW13 are recessed 0.6 mm
  into the face; over the pocket that leaves 0.4 mm of skin under the track.
- **Two colour:** load `sw13_body.stl` and `sw13_ink.stl` as one object; the ink
  fills the recess. It is on the first layer, as Barn's lettering was, but with
  5 mm Arial Black and 1.3 mm lines rather than 3.6 mm text.
- Face down, no supports. Mount with double-sided tape: the back is flat and the
  toggle sits 0.4 mm below it. The ribbon leaves through a 13 mm slot in the
  bottom edge, wide because its position varies from toggle to toggle.

| Item | Value |
|------|-------|
| Plate | 50.8 × 50.8 × 6.5 mm, 3 mm corner radius |
| Skin over toggle | 1.0 mm, LED hole 4.96 mm |
| Pocket | 18.0 mm square (toggle + 0.3), 5.5 mm deep; LED at the plate centre |
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

Barn now uses these sizes (earlier 19.45 mm pockets came from the drawing).
