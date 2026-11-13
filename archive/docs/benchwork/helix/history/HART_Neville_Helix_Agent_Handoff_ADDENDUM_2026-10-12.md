# HART Railroad — Neville Island Helix Handoff ADDENDUM (2026-10-12)

**Read after** `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-10-05.md`. Adds a bracket edge shim. Not printed yet; verified in software only.

> **2026-10-13:** a corner offset spacer for the bracket-0 seam wings was added. See `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-10-13.md`.

## 1. Request (user, 2026-10-12)
The user wants to screw the brackets into the roadbed underside **before** the roadbed goes on the posts, because the underside may be hard to reach afterward. They asked for a shim that sits flat against the bracket and is curved to meet the 26 in inside edge, **0.72 in − 3/32 in tall**. 0.72 in is the measured plywood thickness.

## 2. Design — `make_bracket_edge_shim.py` → `bracket_edge_shim.stl`
- **Corrected 2026-10-13.** The first version sat against an upright leg rising past the edge. That's wrong: the upright leg hangs **down** and screws directly to the 2x4 face.
- The shim fills the gap above the bracket's bend, between the plywood's 26 in inside edge and the 2x4 face. The curved r 26 face goes against the plywood. The flat face is **coplanar with the back of the bracket's upright leg**. The bottom rests on the flat leg.
- Use: hold the bracket back flush with the shim's flat face, then screw the flat leg into the pocket. Later, the bracket back and the shim both bear flat on the 2x4 face.
- **Height 0.62625 in** (15.91 mm) = 0.72 − 3/32. That spans pocket floor to roadbed top.
- **Width 1.5 in** on the flat face (user, 2026-10-13; first built at the 0.600 in strap width).
- **Thickness 0.2742 in** on the centerline, 0.2634 in at the ends (the r 26 curve sags only 0.011 in over 1.5 in) = 26 − 25.7258 (design 2x4 face, PDF §9).
- No chamfer: the bracket's outer bend rounds away from the shim.
- **Bracket notch (2026-10-13):** the bracket's upright leg rides the 2x4 face up through the shim zone, so the flat face has a full-height notch: **0.6625 in wide** (0.600 strap + 1/32 per side, like the pocket) × **0.085 in deep** (0.080 steel + 0.005). The shim straddles the leg and bears on the 2x4 on both sides. A 0.10 in × 45° chamfer at the notch's bottom back edge clears the bracket's inside bend. Wall behind the notch is 0.187–0.189 in.
- **Labels:** none. The user removed them on 2026-10-13 (briefly had engraved IN / OUTSIDE).
- Printed **standing on its bottom edge** (38.1 × 7.0 mm footprint, 15.9 mm tall), so the notch runs straight up. No supports. Watertight single body. One shim per bracket (29 for n = 0…28).

## 3. Open items
1. If a 2x4 face isn't at r 25.7258 as built, the bracket and shim will stand off it or hit it. Change `POST_FACE_R` and re-run.
