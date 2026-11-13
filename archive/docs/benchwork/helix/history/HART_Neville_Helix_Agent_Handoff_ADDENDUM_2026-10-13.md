# HART Railroad — Neville Island Helix Handoff ADDENDUM (2026-10-13)

**Read after** `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-10-12.md`. Adds a corner offset spacer. Not printed yet; verified in software only.

## 1. Request (user, 2026-10-13)
At bracket 0, where P1 butts the corked liftout tongue, the user cut a pocket in the deck plywood for the cork-to-plywood transition shim (`cork_to_plywood_transition_shim.stl`, which the user calls the "offset bracket"). They'll screw through that shim into the deck. The roadbed is wider than the 3.5 in shim, so they also want to secure the **wings** that overhang it on the inside and outside. They asked for an offset spacer at the subroadbed corners, with a screw going through it into the table.

## 2. Design — `make_corner_offset_spacer.py` → `corner_spacer_P1.stl`
- **Revised twice on 2026-10-13.** The first version was a stepped 2 × 1 in block, the second a stepped half barrel straddling the joint. The user wants **plain full barrels**: one under each wing corner, with a screw through the roadbed and the barrel into the deck. The barrel carries the height, so the screw clamps against it instead of pulling the wood down.
- Bracket (transition shim) = 2 in along the track × 3.5 in radial. The subroadbed is 6 in wide, so each **wing is 1.25 in**.
- **P1 corners only.** The tongue is already held by `entry_wedge_riser_inside/outside.stl` (each 1 in radial × 2.25 in along the track × 1.261 in tall). The tongue barrel was dropped.
- **5/8 in OD, 1/4 in hole** (user: narrower so it fits wherever there is room, wider hole for play with a #6 screw). Print at **100% infill**.
- **P1 barrel 0.311 in (7.9 mm, ~5/16)** = P1 top 1-1/32 (`p1_height_template`, definitive) − 0.72 measured plywood. Cross-check: the transition shim high foot is 0.611 in, so the shim pocket should be 0.300 in deep.
- **These heights are derived, not measured.** Measure the gap from the deck to each underside and set `P1_GAP`.
- Print 2, flat, no supports. Watertight single bodies.

## 3. Height datum (user, 2026-10-13) — applies to all future math
- **The height stack is definitive for the roadbed TOP:** `p1_height_template` (1-1/32 in at bracket 0) + 1/2 in per 45° post. The user settled the template at 1-1/32 after measuring; that's 1/32 (0.03) in under the first 1-1/16 estimate.
- The plywood is **0.72 in measured**, so the **underside = top − 0.72**. At P1 that's 0.311 in above the -15 in deck. Don't use a nominal 3/4.
- The first-loop piers (10-01 §11) were computed as top − 3/4, so they're 0.03 in under the 0.72-based underside.

## 4. Layer spacer — `make_layer_spacer.py` → `layer_spacer_4in_pitch.stl`
- For checking loop-to-loop height past the first loop. It stands on the lower roadbed's top and carries the upper roadbed's underside: **3.280 in** = 4.000 pitch − 0.72 plywood.
- Open tube (no top, bottom or infill): **1 in OD, 2.0 mm wall**, plus an **internal + of 1.6 mm ribs** running full height. The bottom 1/4 in is flared at 45° to 1.5 in OD for stability. Fits between the 26 in edge and the track ties. 18.1 cm³ (~22 g). Section 213 mm² (the first 1.2 mm plain tube was 91). No supports; **not** vase mode.
- Watertight single body, 38.1 × 38.1 × 83.3 mm.
- **Vase version** (`make_layer_spacer_vase.py` → `layer_spacer_4in_pitch_vase.stl`): same envelope, modeled solid with **one spiral slit** (0.1 mm wide, **1 turn** (user: 4 was too many; 2 took ~1 h / 15 g, wanted the middle), 1.0 mm pitch = 2 × 0.45 line + slit) winding in from the outside, with a radial lead out through the flare. In spiral vase mode the single outline runs in and out of the coil, so each band gets two lines: about a **1.95 mm wall** (3 lines), ~144 mm² section, ~223 mm path per layer, ~10 g, from one continuous path. Every slice is one outline with no holes. (It replaced a 4-straight-slit version the same day; the user asked for "more walls"; full-diameter slits rotated 90° per layer were rejected because they split each layer in two and leave the ribs bridging.) Slicer: vase on, bottom shell 3–4, slice gap closing radius 0.01. If the outer-wall line width changes, set `LINE_W` and re-run. The script also writes **`layer_spacer_4in_pitch_vase_1line.stl`**: the plain solid with no slit, which prints as a single 0.45 mm line (~80 mm path, ~4 g). Cheapest and fastest, but the weakest.

## 4a. Half-lap as built and lap screws (user, 2026-10-14)
- In the 0.72 in plywood, the lap halves are **upper piece 0.26 in, lower piece 0.46 in** (stack 0.72). This replaces the 1/2 / 1/4 split for 3/4 stock (10-01 §3).
- Lap screws, with glue: **#6 × 5/8 in flat-head wood screws**, countersunk flush from the top. The tip is 0.095 in above the underside, with 0.365 in of thread in the lower piece. Drill a 9/64 in clearance hole through the upper piece and a 7/64 in pilot into the lower piece.
- **Keep them off the bracket pocket.** The lower piece is 0.366 in thick under the 3/32 pocket, so a 5/8 in screw would just reach the pocket floor.
- **Paper template** `lap_screw_template.pdf` (`make_lap_screw_template.py`), US Letter at 100%, with 2 in / 50 mm scale bars. Six screws, symmetric about the joint line, so it fits either hand: at r 26.75 (±0.56 in), r 29.25 (±0.62 in) and r 30.85 (±0.60 in). They stay ≥ 3/16 in from the pocket edge and ≥ 0.31 in from both seams. Register the arc on the 26 in edge and the seam line on the visible top seam.

## 4b. Bracket pocket wedges (user, 2026-10-14) — `make_bracket_wedges.py` → `bracket_wedge_gap_{1,2,3,4}_64.stl`
- Purpose: the brackets don't sit square on the posts. A tapered shim between the flat leg and the pocket floor tilts the bracket so the upright leg sits flat on the 2x4.
- Named by the **gap at the bottom of the 4 in upright leg** that it corrects (1/64–1/16). Taper = gap × 3.5/4 over the 3.5 in length. Thin end 0.5 mm; thick end 0.033 / 0.047 / 0.061 / 0.074 in.
- **Which way:** if the leg's bottom stands off the post, put the thick end toward the bracket tip. If the bottom hits the post and the top stands off, put the thick end toward the post. Flip end for end to reverse.
- 0.62 in wide (pocket 0.6625), 0.2 in center slot for the bracket screws. Notches at the thick end = gap in 64ths.
- Printed standing on the long edge, so the taper is smooth. No supports.
- With the thick end at the post, the roadbed sits up to 0.074 in higher on that bracket. Set the bracket height by the roadbed **top**, with the wedge installed.

## 4c. Bracket plumb shim (user, 2026-10-14) — `make_bracket_plumb_shim.py` → `bracket_plumb_shim.stl`
- What the user meant by "out of whack": the brackets **lean sideways** with the grade. The flat leg runs radially, so the 2.29% grade tilts it across its width, and the upright leg leans about 1.3° along the post face. It still bears flat on the post. The user wants the brackets plumb.
- A strip that tapers **across its width**: 0.62 wide × 3.5 long, **0.20 mm on the thin edge** (one first layer, the user's idea) to **0.56 mm on the thick edge** (taper 0.0142 in = grade at r 27.85 × width). It fits in the pocket's 0.35 mm of slack, so the bracket sits about 0.03 mm proud on average.
- **Thick (notched) edge goes uphill.** Same part for every bracket. 0.2 in center slot for the screws. Prints flat; 0.08–0.1 mm layers give 3–4 steps.
- The §4b along-the-length wedges are for a different problem: a gap between the leg and the post (a bend that isn't square, or a roadbed that tilts across its width).

## 5. Open items
1. Measure the two gaps before printing.
