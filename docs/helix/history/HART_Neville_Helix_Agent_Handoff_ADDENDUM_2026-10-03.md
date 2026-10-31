# HART Railroad — Neville Island Helix Handoff ADDENDUM (2026-10-03)

> **2026-10-05:** a mid-piece bracket-pocket template (no lip, rides the 26 in edge, solid plate) was added. See `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-10-05.md`.

**Read after** `HART_Neville_Helix_Agent_Handoff_ADDENDUM_2026-10-01.md`. This file supersedes the "Half-lap template" and "Bracket pocket template" entries in its §6 and the template printing notes. Nothing here has been printed or tested yet; everything is verified in software only.

## 1. What changed (user request 2026-10-03)

The user asked for three changes to the router templates:
- the window the bit runs in reinforced at 100% infill
- screw holes so the template can be screwed to the blank
- less material, because the solid versions were big prints

The window geometry, lip face, fence face and A/B hand logic are **unchanged**. They were checked against the old STLs: the window boundary matches to 0.2 mm² of area, and the new lip and fence lie inside the old ones with the same faces.

The old solid versions and their scripts are in `superseded/router_templates_solid_2026-10-01/`.

## 2. Design

Shared code is in the new `router_template_lattice.py`. `make_lap_template.py` and `make_bracket_pocket_template.py` call it.

- **Multipart: template + 100% core modifier.**
  - The CORE is a 0.25 in (6.35 mm) band all around the bit window, at full plate thickness.
  - It is a *modifier* part (sparse infill 100%), not a separate physical piece. The bearing wall therefore prints solid and in one piece with the template, so no assembly error is added.
- **Lattice plate.** Outside the core:
  - 2.5 mm ribs at ±45° on a 1.75 in pitch (diamond holes about 1.6 in), plus a 0.12 in rim.
  - Ribs and rim are only 0.25 in tall, measured from the router face.
  - Full plate height, where the template bears on the wood: the core band, the screw bosses, the lip pads and the fence.
  - The end-side rail is over air anyway (past the end cut), and the screws clamp the shoulder-side rail.
- **Lip:** two pads instead of a full-length bar.
  - Lap: r 25.75–27.0 and 30.25–31.5.
  - Pocket: r 25.75–27.0 and 29.5–30.75.
  - Both pads land on every blank's end face and on the depth block's end face (x 26.13–32.5).
- **Screw holes.** Two per template, countersunk from the router face for #6 flat-head screws:
  - Shaft 0.156 in, head 0.340 in, 90° countersink, head sits 0.5 mm below the surface. Bosses are 0.6 in in diameter.
  - The first 10-03 build had the cone inverted (a plain hole at the face, widening inside). Fixed. Measured from the STL: 9.5 mm at the face → 7.6 at 1 mm → 5.6 at 2 mm → 3.96 shaft from 3 mm.
  - **Lap template:** r 26.75 and 31.0, 0.78 in past the lap shoulder. Use **#6 × 1 in** (1/2 in into the blank).
  - **Pocket template:** r 26.75 and 30.0, at 4.73° and 4.42°. Their heads clear the 3.75° lap shoulder by 0.29 in and 0.18 in, so they sit in full-thickness wood on the lower piece's underside. Use **#6 × 1-1/4 in** (1/2 in into the blank).
  - The holes land in the blank outside the joint: on the top of the lower piece (under the cork) or on the underside.
- **Label:** moved to the **underside** (wood side, the top as printed) at the user's request, so the first layer has no text. It is engraved 1 mm into a solid pad at rib height (0.25 in), not mirrored, and reads from the underside. It now includes the screw size.

## 3. Files (all mm, watertight single bodies, still watertight after STL reload)

| File | Use |
|---|---|
| `roadbed_halflap_template_A/B.3mf`, `bracket_pocket_template_A/B.3mf` | **Open these in Creality Print.** One object: the template part plus the `_CORE100` modifier part, already lined up and set to 100% sparse infill. Bambu-style project 3MF, centered at (130, 130) for the SPARKX i7 / K2 bed. |
| `*_template_A/B.stl` | Template body only |
| `*_template_A/B_CORE100.stl` | Core modifier only (same coordinates as the body) |

**If the 3MF doesn't come in with the modifier set:**
1. Import the body STL and its `_CORE100` STL **together** and answer **Yes** to "load as a single object with multiple parts". This keeps their relative position.
2. Right-click the CORE100 part, change its type to Modifier, and add Sparse infill density = 100%.

Cura was not used: the user's active slicer is Creality Print 7.3. The 3MF loader in Creality Print was **not** tested here, because its CLI only launches the GUI.

## 4. Material (estimated: 0.2 mm layers, 2 walls, 4 top/bottom layers, 15% infill, PLA)

| Template | Old solid | New (lattice + 100% core) |
|---|---|---|
| Half-lap | ~123 g | ~96 g |
| Bracket pocket | ~133 g | ~95 g |

These come from a simple layer-area estimate (`estimate.py` in that session's scratchpad), not a slicer. Use the slicer's number.

About 28 g of each new template is the 100% core. Narrowing `CORE_W` (0.25 in) or opening `PITCH` (1.75 in) trades stiffness for filament. No supports or raft are needed: the lip and fence point up and the holes are vertical. The user's Cura profile had raft + supports on; Creality Print needs neither for these parts.

## 5. Printing

- Print as positioned (router face on the bed).
- 2–3 walls, 10–15% infill on the template. The core gets 100% from the modifier.
- Use a brim if corners lift.
- Same-name STLs were overwritten. In the slicer, use **Reload from disk** or re-open the 3MF.

## 6. Open items added

1. Confirm in Creality Print that the 3MF opens as one object with the CORE100 modifier at 100%. If not, use the fallback in §3.
2. Confirm the router base bridges the 1.6 in lattice holes smoothly. It needs to be at least about 3 in across. If it catches, reduce `PITCH`.
3. First physical test as in 10-01 §9 #6, plus the screw holdown: check the template doesn't shift with the screws in, and that the screw holes land outside the lap.
