# 3D-printed station maps

Multi-colour fascia plates that hold Touch Toggles. Barn is first; it follows
`cats/scripts/render_barn_station_map.py`.

```bash
./cats/station_maps_3d/build.sh   # writes stl/barn.3mf and one STL per colour
```

## Printing (Spark i7 + 4-colour AMS, Creality Print)

Open `stl/barn.3mf`, not the STLs. STL has no units, so the slicer guesses from size
and offers to convert the small gold part from inches. The 3MF declares millimetres
and already holds the four colours as parts of one object, in place.

1. Map filaments 1-4 to white, black, teal and gold.
2. Print as loaded, face down on a smooth plate, with no supports. Use 0.2 mm layers or finer so the 0.6 mm inlay gets at least three layers.

After a rebuild, use **Reload from disk**.

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
