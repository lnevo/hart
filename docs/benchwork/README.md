# docs/benchwork

Construction records for the layout benchwork: helix, main level, staging level and the 3D-printed station maps.

| Folder | What it holds | State |
|--------|---------------|-------|
| `helix/` | Neville Island helix: fabrication plan PDF, half-lap screw template, `stl/` fixtures, the design handoff and `HART_Neville_Helix_BUILD_STATUS.md` (the living status file, which wins on conflict) | Current; design handoff is rationale only |
| `main_level/` | Main level framing drawings, plywood cut plan, lumber cut list, marking sheets and `HART_main_level_BOM.md` (shopping list, prices of 2026-10-21) | Current build records |
| `roadbed/` | `cork_roadbed_plan_2025-08.pdf`, a supplier's cork roadbed plan worked out from the AnyRail plan: cork thickness per track type, where sheets, rolls and bevelled strips go on each level and the helix, and the material list (names, contact details and prices taken out) | Reference |
| `staging_level/` | `staging_level_framing.pdf`, the staging level framing drawing | Reference |
| `station_maps_3d/` | OpenSCAD sources and `build.sh` for the multi-colour fascia plates that hold Touch Toggles (Barn and SW13 so far); see its `README.md` for print settings | In progress, first prints under test |

The drawings are PDFs and HTML cut sheets; the Markdown files carry the decisions and the parts lists. Where the helix handoff and the status file disagree, the status file is right.

## 3D prints

- **One STL per colour**, not a generated 3MF. The printer is a Creality SPARKX i7 / K2 (260 mm bed) with a 4-colour AMS, sliced in Creality Print 7.3. A hand-written 3MF with per-part extruders failed there ("unable to resolve a mixed filament used by the current plate") and the owner prefers STLs. Exception: router templates use Bambu-style part plus modifier 3MFs with a 100% infill core; if the modifier does not import, load the body and the `_CORE100` STL as one object and set the core to Modifier.
- **Author in mm.** STL has no units, and a part under about 9 mm3 raises an inches-to-mm prompt; keep every part well over that in the model (`check_stl.py`, `build.sh`).
- **Check after generating:** `len(mesh.split(only_watertight=False)) == 1`, not just `is_watertight`, and reload the file (`lat.stl_roundtrip_ok`). For countersinks, check cone depth against thickness, model from the screw's entry face and verify with a section through the real hole centre.
- A regenerated file keeps its name; tell the owner to use Reload from disk in Creality Print.
- Template defaults: router face down, 2-3 walls, 10-15% infill, no supports; spiral vase parts need a slice gap closing radius of 0.01. PDF edits: keep redaction rects tight and verify with `get_text()`.
- Fixtures count as verified in software only until the owner reports a physical test. Helix facts live in `helix/HART_Neville_Helix_BUILD_STATUS.md`, which wins over the PDF and the handoff; update it in place, with no new addenda.
- **Python.** The root `.venv` is built from `requirements.txt`. trimesh needs earcut, scipy, rtree and networkx at run time though no script imports them, so an import scan misses them (stack: numpy, trimesh, manifold3d, shapely, mapbox_earcut, scipy, rtree, networkx, matplotlib, pymupdf, pypdf). The helix helpers (`router_template_lattice.py`, `stl_text.py`, `stl_out.py`, `check_stl.py`) are under `archive/code/benchwork-tools/`. Run with `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python <script> --out <folder>`. Station map parts build with OpenSCAD through `station_maps_3d/build.sh`; the app is installed but not on PATH.
