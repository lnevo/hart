# Schematic and panel builders

Rules for work under `tools/schematic/`, on top of the root [`AGENTS.md`](../../AGENTS.md). The `schematic-builder` agent carries the same rules.

- Geometry **1:1**; new track is **Mainline → Yes** (`mainline="yes"`). Hart has no `export_options.json`.
- Do not run `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry` or 2× draw scale unless asked.
- Check facts from the source files (the AnyRail plan, the data CSVs) before a geometry build.
- `make panels CHECK=1` before a commit; outputs stay byte-identical unless the task changes them. Approval fingerprints: [`panel-approval` skill](../../.claude/skills/panel-approval/SKILL.md).
- Code here gets `/code-review high` before merge.
