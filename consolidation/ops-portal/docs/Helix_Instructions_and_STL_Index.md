# Neville Island Helix — Instructions and STL Index

*Updated 15 October 2026. Web version: [helix/index.html](../helix/index.html).*

## Instructions

- [Construction plan PDF](../helix/files/helix_construction_plan_FINAL_31p75_18p75_2026-09-23.pdf): 13 pages. **Page 13 is the half-lap screw template.**
- [Half-lap screw template PDF](../helix/files/lap_screw_template.pdf): US Letter, print at 100%, check the 2 in / 50 mm bars.
- [Build status](../helix/files/HART_Neville_Helix_BUILD_STATUS.md): as-built facts; overrides the PDF where they differ.
- [Design handoff](../helix/files/HART_Neville_Helix_Agent_Handoff_FINAL_31p75_18p75_2026-09-23.md): rationale and formulas.

## STL index

46 files, all in millimetres. Extents are the exported bounding box, X × Y × Z.

### Router templates

| File | Size | Extents mm (in) | Script | Notes |
|---|---|---|---|---|
| [`roadbed_halflap_template_A.3mf`](../helix/stl/roadbed_halflap_template_A.3mf) | 124 KB | 3MF project | [`make_lap_template.py`](../helix/scripts/make_lap_template.py) | Half-lap router template, hands A and B. Hooks the end cut and the 26 in edge; window to a radial shoulder at 3.75°. Open the 3MF (body + 100% core modifier). |
| [`roadbed_halflap_template_A.stl`](../helix/stl/roadbed_halflap_template_A.stl) | 619 KB | 203.8 × 184.4 × 25.4 (8.03 × 7.26 × 1.00) | ″ | ″ |
| [`roadbed_halflap_template_A_CORE100.stl`](../helix/stl/roadbed_halflap_template_A_CORE100.stl) | 13 KB | 198.6 × 67.5 × 12.7 (7.82 × 2.66 × 0.50) | ″ | ″ |
| [`roadbed_halflap_template_B.3mf`](../helix/stl/roadbed_halflap_template_B.3mf) | 127 KB | 3MF project | ″ | ″ |
| [`roadbed_halflap_template_B.stl`](../helix/stl/roadbed_halflap_template_B.stl) | 632 KB | 203.8 × 184.4 × 25.4 (8.03 × 7.26 × 1.00) | ″ | ″ |
| [`roadbed_halflap_template_B_CORE100.stl`](../helix/stl/roadbed_halflap_template_B_CORE100.stl) | 13 KB | 198.6 × 67.5 × 12.7 (7.82 × 2.66 × 0.50) | ″ | ″ |
| [`bracket_pocket_template_A.3mf`](../helix/stl/bracket_pocket_template_A.3mf) | 138 KB | 3MF project | [`make_bracket_pocket_template.py`](../helix/scripts/make_bracket_pocket_template.py) | Bracket pocket at a lap joint: slot 0.6625 wide on the joint line, 3/32 deep, 1/2 in bit. Pair with the same lap letter. |
| [`bracket_pocket_template_A.stl`](../helix/stl/bracket_pocket_template_A.stl) | 715 KB | 150.4 × 168.1 × 31.8 (5.92 × 6.62 × 1.25) | ″ | ″ |
| [`bracket_pocket_template_A_CORE100.stl`](../helix/stl/bracket_pocket_template_A_CORE100.stl) | 2 KB | 126.5 × 33.6 × 19.0 (4.98 × 1.32 × 0.75) | ″ | ″ |
| [`bracket_pocket_template_B.3mf`](../helix/stl/bracket_pocket_template_B.3mf) | 140 KB | 3MF project | ″ | ″ |
| [`bracket_pocket_template_B.stl`](../helix/stl/bracket_pocket_template_B.stl) | 726 KB | 150.4 × 168.1 × 31.8 (5.92 × 6.62 × 1.25) | ″ | ″ |
| [`bracket_pocket_template_B_CORE100.stl`](../helix/stl/bracket_pocket_template_B_CORE100.stl) | 2 KB | 126.5 × 33.6 × 19.0 (4.98 × 1.32 × 0.75) | ″ | ″ |
| [`bracket_pocket_template_MID.3mf`](../helix/stl/bracket_pocket_template_MID.3mf) | 63 KB | 3MF project | [`make_mid_pocket_template.py`](../helix/scripts/make_mid_pocket_template.py) | Mid-piece bracket pocket (odd n). Rides the 26 in edge; center the V-notch on the pencil line (chord 20.683, P1 19.900). |
| [`bracket_pocket_template_MID.stl`](../helix/stl/bracket_pocket_template_MID.stl) | 327 KB | 147.9 × 158.1 × 31.8 (5.82 × 6.23 × 1.25) | ″ | ″ |
| [`bracket_pocket_template_MID_CORE100.stl`](../helix/stl/bracket_pocket_template_MID_CORE100.stl) | 2 KB | 125.6 × 29.5 × 19.0 (4.95 × 1.16 × 0.75) | ″ | ″ |
| [`router_depth_block.stl`](../helix/stl/router_depth_block.stl) | 1.4 MB | 172.3 × 25.4 × 104.1 (6.78 × 1.00 × 4.10) | [`make_router_depth_block.py`](../helix/scripts/make_router_depth_block.py) | Two-sided depth block, wells 3/32 · 1/4 · 3/8 / 1/2 · 5/8 · 3/4. Print on its end with a brim. |
| [`router_depth_gauge.stl`](../helix/stl/router_depth_gauge.stl) | 231 KB | 76.2 × 31.8 × 12.7 (3.00 × 1.25 × 0.50) | [`make_router_depth_gauge.py`](../helix/scripts/make_router_depth_gauge.py) | Checks POCKET 3/32, LOWER 1/4, UPPER 1/2 (3/4-stock values). |

### Heights

| File | Size | Extents mm (in) | Script | Notes |
|---|---|---|---|---|
| [`p1_height_template.stl`](../helix/stl/p1_height_template.stl) | 149 KB | 38.1 × 50.8 × 26.2 (1.50 × 2.00 × 1.03) | [`make_height_spacers.py`](../helix/scripts/make_height_spacers.py) | P1 roadbed top at bracket 0: 1-1/32 in above the deck. |
| [`height_base_1_4in.stl`](../helix/stl/height_base_1_4in.stl) | 122 KB | 38.1 × 50.8 × 6.3 (1.50 × 2.00 × 0.25) | [`make_height_spacers.py`](../helix/scripts/make_height_spacers.py) | Stacking height blocks (pegs + crush ribs). Template + 1/2 in per 45° marks the plywood top. |
| [`height_spacer_1_4in.stl`](../helix/stl/height_spacer_1_4in.stl) | 105 KB | 38.1 × 50.8 × 9.4 (1.50 × 2.00 × 0.37) | ″ | ″ |
| [`height_spacer_1_2in.stl`](../helix/stl/height_spacer_1_2in.stl) | 112 KB | 38.1 × 50.8 × 15.7 (1.50 × 2.00 × 0.62) | ″ | ″ |
| [`height_spacer_3_4in.stl`](../helix/stl/height_spacer_3_4in.stl) | 122 KB | 38.1 × 50.8 × 22.0 (1.50 × 2.00 × 0.87) | ″ | ″ |
| [`height_spacer_1in.stl`](../helix/stl/height_spacer_1in.stl) | 98 KB | 38.1 × 50.8 × 28.4 (1.50 × 2.00 × 1.12) | ″ | ″ |
| [`height_spacer_1_1_2in.stl`](../helix/stl/height_spacer_1_1_2in.stl) | 118 KB | 38.1 × 50.8 × 41.1 (1.50 × 2.00 × 1.62) | ″ | ″ |
| [`first_loop_pier_post2.stl`](../helix/stl/first_loop_pier_post2.stl) | 77 KB | 101.6 × 38.1 × 20.3 (4.00 × 1.50 × 0.80) | [`make_first_loop_piers.py`](../helix/scripts/make_first_loop_piers.py) | First-loop piers, posts 2–7. Top at grade, arrow uphill; two screw tabs. |
| [`first_loop_pier_post3.stl`](../helix/stl/first_loop_pier_post3.stl) | 91 KB | 101.6 × 38.1 × 33.0 (4.00 × 1.50 × 1.30) | ″ | ″ |
| [`first_loop_pier_post4.stl`](../helix/stl/first_loop_pier_post4.stl) | 82 KB | 101.6 × 38.1 × 45.7 (4.00 × 1.50 × 1.80) | ″ | ″ |
| [`first_loop_pier_post5.stl`](../helix/stl/first_loop_pier_post5.stl) | 97 KB | 101.6 × 38.1 × 58.4 (4.00 × 1.50 × 2.30) | ″ | ″ |
| [`first_loop_pier_post6.stl`](../helix/stl/first_loop_pier_post6.stl) | 107 KB | 101.6 × 38.1 × 71.1 (4.00 × 1.50 × 2.80) | ″ | ″ |
| [`first_loop_pier_post7.stl`](../helix/stl/first_loop_pier_post7.stl) | 97 KB | 101.6 × 38.1 × 83.8 (4.00 × 1.50 × 3.30) | ″ | ″ |
| [`layer_spacer_4in_pitch.stl`](../helix/stl/layer_spacer_4in_pitch.stl) | 63 KB | 38.1 × 38.1 × 83.3 (1.50 × 1.50 × 3.28) | [`make_layer_spacer.py`](../helix/scripts/make_layer_spacer.py) | Loop-to-loop check, 3.280 in (4.000 − 0.72). Normal mode, ~22 g. |
| [`layer_spacer_4in_pitch_vase.stl`](../helix/stl/layer_spacer_4in_pitch_vase.stl) | 100 KB | 38.1 × 38.1 × 83.3 (1.50 × 1.50 × 3.28) | [`make_layer_spacer_vase.py`](../helix/scripts/make_layer_spacer_vase.py) | Same spacer in spiral vase mode (~10 g, or ~4 g single line). Slice gap closing radius 0.01. |
| [`layer_spacer_4in_pitch_vase_1line.stl`](../helix/stl/layer_spacer_4in_pitch_vase_1line.stl) | 28 KB | 38.1 × 38.1 × 83.3 (1.50 × 1.50 × 3.28) | ″ | ″ |

### Entry

| File | Size | Extents mm (in) | Script | Notes |
|---|---|---|---|---|
| [`entry_wedge_riser_inside.stl`](../helix/stl/entry_wedge_riser_inside.stl) | 28 KB | 25.4 × 57.2 × 32.0 (1.00 × 2.25 × 1.26) | none kept | Tongue risers, 1 × 2.25 in, 1.261 tall, step 0.864. Engraved R / L. |
| [`entry_wedge_riser_outside.stl`](../helix/stl/entry_wedge_riser_outside.stl) | 24 KB | 25.4 × 57.2 × 32.0 (1.00 × 2.25 × 1.26) | ″ | ″ |
| [`cork_to_plywood_transition_shim.stl`](../helix/stl/cork_to_plywood_transition_shim.stl) | 68 KB | 50.8 × 88.9 × 15.5 (2.00 × 3.50 × 0.61) | none kept | The “offset bracket” under P1: low foot 0.375 (tongue), high foot 0.611 (P1). Sits in a ~0.300 deep deck pocket. |
| [`corner_spacer_P1.stl`](../helix/stl/corner_spacer_P1.stl) | 28 KB | 15.9 × 15.9 × 9.6 (0.62 × 0.62 × 0.38) | [`make_corner_offset_spacer.py`](../helix/scripts/make_corner_offset_spacer.py) | Barrel under each P1 wing corner, 0.376 tall (0.311 + 1.65 mm field correction), 5/8 OD. Print 2 at 100% infill. |

### Brackets

| File | Size | Extents mm (in) | Script | Notes |
|---|---|---|---|---|
| [`bracket_edge_shim.stl`](../helix/stl/bracket_edge_shim.stl) | 13 KB | 7.0 × 38.1 × 15.9 (0.27 × 1.50 × 0.63) | [`make_bracket_edge_shim.py`](../helix/scripts/make_bracket_edge_shim.py) | Fills the 26 in edge to 2x4 face gap above the bend; also the radial go/no-go gauge. 29 needed. |
| [`bracket_plumb_shim.stl`](../helix/stl/bracket_plumb_shim.stl) | 2 KB | 88.9 × 15.7 × 0.6 (3.50 × 0.62 × 0.02) | [`make_bracket_plumb_shim.py`](../helix/scripts/make_bracket_plumb_shim.py) | Tapered strip (0.20 → 0.56 mm) for the sideways lean from grade. Notched edge uphill. One per bracket. |
| [`bracket_wedge_gap_1_64.stl`](../helix/stl/bracket_wedge_gap_1_64.stl) | 2 KB | 88.9 × 0.8 × 15.7 (3.50 × 0.03 × 0.62) | [`make_bracket_wedges.py`](../helix/scripts/make_bracket_wedges.py) | Wedges for a gap between the bracket leg and the post; notches = gap in 64ths. |
| [`bracket_wedge_gap_2_64.stl`](../helix/stl/bracket_wedge_gap_2_64.stl) | 3 KB | 88.9 × 1.2 × 15.7 (3.50 × 0.05 × 0.62) | ″ | ″ |
| [`bracket_wedge_gap_3_64.stl`](../helix/stl/bracket_wedge_gap_3_64.stl) | 4 KB | 88.9 × 1.5 × 15.7 (3.50 × 0.06 × 0.62) | ″ | ″ |
| [`bracket_wedge_gap_4_64.stl`](../helix/stl/bracket_wedge_gap_4_64.stl) | 5 KB | 88.9 × 1.9 × 15.7 (3.50 × 0.07 × 0.62) | ″ | ″ |

### Shop tool

| File | Size | Extents mm (in) | Script | Notes |
|---|---|---|---|---|
| [`router_sigerio_test_plate.stl`](../helix/stl/router_sigerio_test_plate.stl) | 502 KB | 152.4 × 152.4 × 4.8 (6.00 × 6.00 × 0.19) | none kept | MW104 router to Sigerio circle-jig adapter, test plate. Hole sizes and center bore are estimates. |
| [`router_sigerio_test_plate_body.stl`](../helix/stl/router_sigerio_test_plate_body.stl) | 440 KB | 152.4 × 152.4 × 4.8 (6.00 × 6.00 × 0.19) | ″ | ″ |
| [`router_sigerio_test_plate_screw_rings.stl`](../helix/stl/router_sigerio_test_plate_screw_rings.stl) | 563 KB | 98.9 × 98.9 × 4.8 (3.89 × 3.89 × 0.19) | ″ | ″ |

Obsolete, not published: `bracket_pocket_template.stl`, `entry_transition_shim.stl`, `entry_transition_shim_inside.stl`, `entry_transition_shim_outside.stl`, `entry_wedge_riser.stl`.
