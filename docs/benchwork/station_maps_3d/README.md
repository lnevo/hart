# 3D-printed station maps

Multi-colour fascia plates that hold Touch Toggles. Barn is first; it follows
`ops/station_maps/scripts/render_barn_station_map.py`.

```bash
./docs/benchwork/station_maps_3d/build.sh   # writes stl/barn_{white,black,teal,gold}.stl
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
