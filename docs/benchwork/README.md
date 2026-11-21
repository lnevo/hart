# docs/benchwork

Construction records for the layout benchwork: helix, main level, staging level and the 3D-printed station maps.

| Folder | What it holds | State |
|--------|---------------|-------|
| `helix/` | Neville Island helix: fabrication plan PDF, half-lap screw template, `stl/` fixtures, the design handoff and `HART_Neville_Helix_BUILD_STATUS.md` (the living status file, which wins on conflict) | Current; design handoff is rationale only |
| `main_level/` | Main level framing drawings, plywood cut plan, lumber cut list, marking sheets and `HART_main_level_BOM.md` (shopping list, prices of 2026-10-21) | Current build records |
| `staging_level/` | `staging_level_framing.pdf`, the staging level framing drawing | Reference |
| `station_maps_3d/` | OpenSCAD sources and `build.sh` for the multi-colour fascia plates that hold Touch Toggles (Barn and SW13 so far); see its `README.md` for print settings | In progress, first prints under test |

The drawings are PDFs and HTML cut sheets; the Markdown files carry the decisions and the parts lists. Where the helix handoff and the status file disagree, the status file is right.
