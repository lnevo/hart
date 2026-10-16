# HART Railroad — Neville Island Helix: Build Status

**Last updated 2026-10-15.** This is the single living status document. **Update it in place; don't start new addenda.** It replaces the six dated addenda (2026-09-30 through 2026-10-13), which are archived unchanged in `superseded/addenda_2026-09-30_to_10-13/` if the history is ever needed.

**Read in this order:**
1. `helix_construction_plan_FINAL_31p75_18p75_2026-09-23.pdf`: fabrication drawings. Its entry pages (2, 3, 8) are stale; see §8. **Page 13 is the half-lap screw template** (added 2026-10-15; same as `lap_screw_template.pdf`).
2. `HART_Neville_Helix_Agent_Handoff_FINAL_31p75_18p75_2026-09-23.md`: design rationale, alternatives, formulas.
3. **This file:** as-built facts, decisions that override the two above, every fixture and script, and open items. **Where this file conflicts with the PDF or the FINAL handoff, this file wins.**

Unless marked *tested*, the fixtures here are verified only in software (watertight, single body, sections checked).

---

## 1. As-built facts and datums (these override the PDF and the FINAL handoff)

### Heights — use these for all math
- **The height stack is definitive for the roadbed TOP.** `p1_height_template` = **1-1/32 in** (1.03125) above the -15 in deck at bracket 0, then **+1/2 in per 45°**. The user settled on 1-1/32 by test-fit on 2026-10-02 (1-1/16 was too high). The calculated value was 1.100.
- **Plywood is 0.72 in measured.** Underside = top − 0.72 (0.311 in at P1). **Don't use a nominal 3/4.**
- **The first-loop piers** were sized as top − 3/4, so they're 0.03 in under the 0.72-based underside. The user checked: the wood lines up, and they stay as built.
- **Layer spacers** (§4) are **3.345 in (84.96 mm)**, not 3.280: the 3.280 prints came out 1.65 mm short of the loop-to-loop gap (2026-10-15).
- **Grade and clearance:** a constant offset changes neither. Railhead-to-underside clearance in the helix = 4.000 − 0.72 − T = **3.12 in** with T = 0.160 (nominal Code 83; caliper the actual track).

### Half-lap joints (as built in 0.72 ply)
- **Upper piece keeps 0.26 in, lower piece keeps 0.46 in** (stack 0.72). This replaces the 1/4 + 1/2 split for 3/4 stock. The lap template labels still say LOWER 1/4 | UPPER 1/2.
- The lap is a 3.75° wedge: 1.701 in along the 26 in edge, 2.078 in along 31.75 (2.094 at 32). The shoulder is radial. The nominal joint line is in the middle, 1.875° from each end.
- Label cuts **by piece** (LOWER / UPPER), never "top lap / bottom lap".

### Bracket grid
- The grid is relative to the **entry butt joint** (the helix structure is rotated to suit). This supersedes "Post 1 at 6:00 + 21.75°".
- **Bracket n** is at **n × 45°** past the butt joint and **n × 0.500 in** above bracket 0. Even n is under a half-lap joint; odd n is mid-piece. The last regular bracket is n = 28 (1260°, +14.000). The final 30° needs separate support.
- Measure every bracket height **from bracket 0**, not bracket to bracket.
- Bracket 0 is under the butt joint. Keep its whole 0.600 strap on the helix side of the cork step.
- Brackets stay square and radial; **grade is tangential**. In the bracket's radial plane the roadbed is level, so grade only leans the bracket sideways (about 1.3°). See the plumb shim in §4.

### P1 (first roadbed piece)
- Butt start with no lap: **1.875° trimmed** off the entry end, 0.851 in (≈27/32) on the 26 in edge, 1.039 at 31.75 / 1.047 at 32. Radial cut. That leaves a 91.875° piece, inside chord **37.366 in**.
- The outer radius may be 32 in instead of 31.75 (6 in blank). Every inside-edge check is independent of the outer radius.

### Entry (approach to the helix)
- The cookie-cut tongue: **5-3/8 in straight** (inner and outer tracks the same) + a curve starting at **4:30** on the 26 in radius, with the existing track and 6 mm cork. The tongue is a **liftout**.
- At the butt joint the **railheads are continuous**: the tongue plywood is 0.236 in lower than P1, and the cork makes up the difference.
- The tongue is held by `entry_wedge_riser_inside/outside.stl` (§4). P1 sits on `cork_to_plywood_transition_shim.stl` (the user calls it the "offset bracket"), which sits in a pocket cut into the deck. `corner_spacer_P1.stl` goes under P1's two wing corners.
- **Clearance under loop 1 over the approach:** 3.12 in at the butt joint. If the tongue is a straight ramp, it drops to about **3.06 in** at the curve start (inner track 28 in: tongue ≈ 2.09% vs helix 2.27%; outer 30.5 in: ≈ 1.94% vs 2.09%). Cork doesn't reduce it because the railheads are continuous. Field check: **loop-1 underside above the deck = 4.311 − (degrees back from the butt joint ÷ 90) in**; subtract the measured railhead height at that spot.
- Old deck-height chain (-15 in baseline, GRADE 0.02176): rise to nominal 6:00 = 5.375 × 0.02176 + 0.500. This is history only; the height stack (above) is authoritative.

### Exit
- The cork may return about 6 in into the 20-15/16 in exit straight (the user's recollection). Helix railhead vs the downstream target there is about +0.26 in at full grade (+0.13 if the grade is flattened at the end of the curve). With 0.72 ply the railhead is 0.03 lower than earlier 3/4-based estimates, which helps slightly.
- Easing the exit early never reduces clearance (the loop below is fixed).

---

## 2. Frame alignment (advice, 2026-10-14)
The posts must line up with the pockets already routed. **Don't resize the frame first.**
- **Along the circle:** a 0.600 strap on a 1.5 in post face can slide ±0.45 in (about ±1°), so small errors need no frame change.
- **Radially:** this one is exact. The 2x4 face is **0.263 in inside the 26 in edge**. `bracket_edge_shim.stl` is a go/no-go gauge.
- Dry-fit the roadbed (clamped, not glued). At each post, measure A = the pocket centerline's offset along the circle, and B = the gap from the 26 in edge to the 2x4 face. Then fix in this order:
  1. A off by the same amount everywhere: **rotate** the frame.
  2. B tight on one side and loose opposite: **translate** the frame by half the difference.
  3. B off by the same amount everywhere: **scale**. Change each tie's 18.000 long edge by **0.828 × the radial change**.
  4. Leftovers: shim behind that bracket, or move that one post. **Don't** change one side's length to fix one post.

---

## 3. Shop process

### Blanks (31.75 / 32 outer)
| Check | 31.75 | 32 |
|---|---|---|
| Inside chord, 26 in corners (93.75°) | 37.953 (37-15/16) | same |
| Outside chord | 46.346 | 46.711 |
| Diagonals (both equal) | 42.333 | 42.530 |
| Nominal 90° mark in from the end | 0.851 in / 1.039 out | 0.851 / 1.047 |
| Inside chord between the 90° marks | 36.770 | same |
1/32 in on the inside chord ≈ 0.1°.

### Nesting (48 × 96, chord along 48, pivots 24 in from the long edge)
5.75 wide: 8.611 advance, 10 per sheet. 6.00: 8.918, 10 per sheet. 6.50: 9 per sheet. A fixed 9 in spacing fits 10 at any width up to 6.5 (gap 1.066 / 0.816 / 0.566 / 0.316). Not decided yet; not in the PDF.

### Cutting
- Arcs: Sigerio circle jig + AVID POWER MW104, **1/4 in straight or upcut spiral**, 3–4 passes over a spoil board. For the 26 in arc, measure the pivot to the **far** edge of the bit; for the outer arc, to the **near** edge.
- Radial ends: inside corner at 17.773 along the centerline and **18.976 (18-31/32)** perpendicular from the pivot. Strike the line through the pivot. Outside corner check 23.173 (31.75) / 23.356 (32). **No circular saw** (it runs into the nested neighbor). Use the router against a zero-offset straightedge, kerf to kerf, always with the same side of the base on the fence.

### Router bits
- User kit (`IMG_0718.jpeg`): straight bits, flush-trim, profile; no top-bearing bits. **Purchased:** UTRUSTTO 4-pc pattern set (ASIN B0CCFBBVPF), 1/2 in diameter, 1/4 shank, **bearing on top** despite the listing text. Shortest cutter is 1/2 or 25/64 (listings conflict; measure it).
- The bearing must ride the template at every depth: `0 ≤ L − depth < T − ~1/8`.
- Pockets and lower laps: shortest bit. Upper lap: shortest if L = 1/2; otherwise take it to about 3/8 and finish with the 3/4 bit. Never start a shallow lap with the 3/4 bit.

### Fasteners
| Where | Screw | Notes |
|---|---|---|
| Half-lap, from the top, with glue | **#6 × 5/8 flat-head wood screw** (Spax-type, not drywall) | 9/64 clearance through the upper piece, 7/64 pilot into the lower; countersink flush. Tip 0.095 above the underside. Keep off the pocket (0.366 left under it). Layout: `lap_screw_template.pdf`. |
| Bracket into the pocket, from below | **#8 × 5/8** (pan, or flat if the holes are countersunk) | Vix bit through the bracket holes, 1/8 pilot, **tape stop at 1/2 in** (only 0.626 of wood above the pocket). Stops 0.08 below the top. At laps it also clamps the joint. |
| Pocket/lap template hold-down | #6 × 1-1/4 (pocket), #6 × 1 (lap) | Holes land outside the joint |
| Piers to the deck | #6 × 1 in | 1-1/4 would come through |
| Entry risers | #6: 2 in high side, 1-1/4 low side | Driven from below |
| Corner spacer | #6 through the 1/4 in hole | |

**Dry fit, then glue:** drill and screw the laps and brackets snug, number every piece and its up face, take it apart, glue, and re-drive into the same holes. A stripped hole gets a glued toothpick or a #8 in that hole.

**Bracket placement during the dry fit:** put `bracket_edge_shim` against the 26 in edge, with the bracket back flush in its notch. Center the strap in the pocket (1/32 per side). Pilot through the bracket holes.

---

## 4. Fixtures and scripts (`~/Downloads/stl`, all STLs in mm, watertight single bodies)

Same filename = overwritten on regeneration. In Creality Print use **Reload from disk**.

### Router templates
| File(s) | Script | Notes |
|---|---|---|
| `roadbed_halflap_template_A/B.3mf` (+ `.stl`, `_CORE100.stl`) | `make_lap_template.py` + `router_template_lattice.py` | Lip hooks the end cut, fence hooks the 26 in edge. Window to a radial shoulder at 3.75°, r 25.5–32.75. 1/2 in plate, lattice with a 0.25 in **100% core modifier** around the window. 2 countersunk #6 holes. **Open the 3MF** (Bambu-style, part + modifier). |
| `bracket_pocket_template_A/B.3mf` (+ `.stl`, `_CORE100.stl`) | `make_bracket_pocket_template.py` | Slot 0.6625 wide, centered on the joint line, r 25.5 → 29.95, **3/4 in plate, 1/2 in bit**, 3/32 deep. Same letter pairs with the same lap letter. |
| `bracket_pocket_template_MID.3mf` (+ `.stl`, `_CORE100.stl`) | `make_mid_pocket_template.py` | Mid-piece brackets (odd n). Symmetric, rides the 26 in edge, no lip. Center on the pencil line (V-notch). Regular piece: chord **20.683** from each inside corner. P1: **19.900** from the butt-end corner. #6 × 1-1/4. |
| `router_depth_block.stl` | `make_router_depth_block.py` | Double-sided; wells 3/32·1/4·3/8 / 1/2·5/8·3/4 (the user's order; keep it). Face 1 = LAP B / PKT A. Print standing on its end with a brim. |
| `router_depth_gauge.stl` | `make_router_depth_gauge.py` | Checks POCKET 3/32, LOWER 1/4, UPPER 1/2 (3/4-stock values). |

A/B hand logic: templates print plate-down and are flipped for use. One lap hand does both ends by flipping the piece. If a template doesn't seat on both the lip and the fence, use the other letter.

### Heights
| File(s) | Script | Notes |
|---|---|---|
| `p1_height_template.stl` | `make_height_spacers.py` | **1-1/32 in** = P1 top at bracket 0. Sockets on top. |
| `height_spacer_1_4in/1_2in/3_4in/1in/1_1_2in.stl`, `height_base_1_4in.stl` | same | Lego-style stack (pegs + crush ribs), sum 4.000. Template + 1/2 per 45° marks the plywood **top**. |
| `first_loop_pier_post2…7.stl` | `make_first_loop_piers.py` | Sized as top − 3/4 (0.03 low; accepted). Top at grade, arrow uphill. Trellis webs, two screw tabs. Posts 1 and 8 skipped. |
| `layer_spacer_4in_pitch.stl` | `make_layer_spacer.py` | Loop-to-loop check, **3.345 in (84.96 mm)** = 4.000 − 0.72 + **1.65 mm field correction** (2026-10-15: the 3.280 in prints were 1.65 mm short; `FIELD_ADD`). 1 in OD, 2 mm wall + internal + ribs, 1.5 in 45° flared foot. ~22 g. Normal mode. |
| `layer_spacer_4in_pitch_vase.stl` | `make_layer_spacer_vase.py` | Same envelope, **spiral vase**. Solid with a 1-turn 0.1 mm spiral slit, so a 3-line (~1.95 mm) wall from one path, ~10 g. Vase on, bottom 3–4 layers, **slice gap closing radius 0.01**, outer line 0.45 (`LINE_W`). |
| `layer_spacer_4in_pitch_vase_1line.stl` | same | Plain single-line vase, ~4 g, weakest. |

### Entry
| File(s) | Script | Notes |
|---|---|---|
| `entry_wedge_riser_inside/outside.stl` | (none kept) | 1 × 2.25 in footprint, 1.261 tall. Step **0.864** (the chord-corrected calc says 0.859; not regenerated, and the P1 template already absorbs it). Engraved R / L. |
| `cork_to_plywood_transition_shim.stl` | (none kept) | 2 in along the track × 3.5 radial. Low foot 0.375 (tongue), high foot 0.611 (P1); step 0.236. 2 countersunk holes per foot. Sits in a deck pocket that should be ~0.300 deep. |
| `corner_spacer_P1.stl` | `make_corner_offset_spacer.py` | Barrel under each P1 wing corner (wings are 1.25 in on a 6 in roadbed). **0.311 tall**, 5/8 OD, 1/4 hole. Print 2 at 100% infill. Measure the gap first (`P1_GAP`). |

### Brackets (Wideskall 4x4, 0.080 steel, 0.600 strap, 0.185 holes)
| File(s) | Script | Notes |
|---|---|---|
| `bracket_edge_shim.stl` | `make_bracket_edge_shim.py` | Fills the gap between the 26 in edge and the 2x4 face above the bend. 0.62625 tall (0.72 − 3/32), 1.5 wide, 0.274 thick (r 26 curve vs the 2x4 face at r 25.7258), with a bracket notch. Also the radial gauge. 29 needed. Change `POST_FACE_R` if the posts are off. |
| `bracket_plumb_shim.stl` | `make_bracket_plumb_shim.py` | **Brackets lean sideways with the grade.** Strip tapered across its width, 0.20 → 0.56 mm (grade 2.29% × 0.62). **Notched (thick) edge uphill.** Fits the pocket's 0.35 mm slack. Prints flat, 0.2 first layer, 0.08–0.1 after. One per bracket. |
| `bracket_wedge_gap_{1,2,3,4}_64.stl` | `make_bracket_wedges.py` | For a **gap between the leg and the post** (a bend that isn't square, or a roadbed tilted across its width). Taper along the length; notches = gap in 64ths. Bottom of the leg off the post: thick end toward the tip. Top off: thick end toward the post. Set the height by the roadbed top. |

### Paper
- `lap_screw_template.pdf` (`make_lap_screw_template.py`): US Letter, **print at 100%** (print only that page; it is also page 13 of the construction plan PDF), check the 2 in / 50 mm bars. Arc on the 26 in edge, seam line on the visible top seam (symmetric, either hand). Six screws at r 26.75 / 29.25 / 30.85, ±0.56 / 0.62 / 0.60 off the joint line, ≥ 3/16 from the pocket and ≥ 0.31 from the seams.

### Shop tool
- `router_sigerio_test_plate*.stl`: MW104 to Sigerio adapter **test** plate. 6 in, 8.32 mm. Router holes 90° countersunk, 3.000 in across the diagonal. Sigerio holes plain on a 4.5 in circle. Hole sizes (0.22, 0.25) and center bore (1.75) are estimates.

### Obsolete (don't print)
`bracket_pocket_template.stl` (no suffix; inches, not watertight), `entry_transition_shim*.stl`, `entry_wedge_riser.stl` (no suffix). The old solid router templates are in `superseded/router_templates_solid_2026-10-01/`.

---

## 5. Printing (Creality Print 7.3, SPARKX i7 / K2, 260 mm bed)
- Multipart (modifier) parts ship as Bambu-style 3MF. If the modifier doesn't come in, import the body + `_CORE100` STL together as one object, set the core to Modifier, sparse infill 100%.
- Templates: router face down, 2–3 walls, 10–15% infill, no supports.
- Thin parts (wedges, plumb shims) print slower. Vase parts need the gap-closing setting above.

## 6. Regenerating
- Scripts run from `~/Downloads/stl` with `python <script>.py`. There's no global trimesh; make a venv with:
  `numpy trimesh manifold3d shapely mapbox_earcut scipy rtree networkx matplotlib pymupdf pypdf`
- Run with `PYTHONDONTWRITEBYTECODE=1` to keep `__pycache__` out of the folder.

## 7. Process lessons
- Author STLs **in mm** (STL has no units).
- Check `len(mesh.split(only_watertight=False)) == 1`, not just `is_watertight`.
- Countersinks: check cone depth against thickness, model them from the screw's entry face, and verify with a section through the actual hole center.
- PDF redactions: keep the rects tight and verify with `get_text()`.
- After overwriting an STL, remind the user to use **Reload from disk**.

## 8. Open items
1. **PDF entry pages (2, 3, 8)** still assume a 6 in straight and the old Post 1 reference. Regenerate them from §1 (5-3/8 straight, butt-joint grid, height stack), and redo the exit table.
2. **Exit straight plan-view direction** vs the lower loop: needs a field answer.
3. **Corner spacer:** measure deck-to-P1-underside at both corners (0.311 assumed). The user saw the outside reading higher. By design inside and outside are equal at the same angle, so check the table, the tongue risers and the shim seat. Make inside/outside versions if they really differ.
4. **Frame vs pockets:** dry-fit, take the 8 A/B readings (§2), and send them in for a rotate/translate/scale fit.
5. Measure the shortest UTRUSTTO cutter (1/2 vs 25/64).
6. Caliper the actual track height T (0.160 assumed) before clearance sign-off.
7. First physical tests not yet reported: lap/pocket templates in scrap, the MID template, the depth block wells, the 3MF modifier import, the vase coil (check it in the preview), wedges and plumb shims. The layer spacers were tested at 3.280 and came out 1.65 mm short; reprint all three at 3.345 and recheck.
8. Nesting spacing (9 in vs 8.611/8.918): decide, then add it to the PDF.
9. Delete the obsolete STLs listed in §4 once the user agrees.
10. Router adapter: verify the hole sizes against the real router and jig.
11. Add the diagonal bracing (PDF p. 12) to the FINAL handoff's locked list. It is in the PDF only: braced bays A-B, C-D, E-F, G-H, two half-diagonals each, 20-5/8 in, 27°.
