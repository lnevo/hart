# JMRI panel pipeline

Turn an **AnyRail export** into a **blocked JMRI panel** with occupancy sensors, NX boundaries, and layout defaults from your authoritative panel.

## Per-layout folders

See [`layouts/README.md`](layouts/README.md). Active layout is **`mac`** unless you set:

```bash
export JMRI_LAYOUT=new
```

## Main scripts (`scripts/`)

| Script | Role |
|--------|------|
| `apply_blocks_to_panel.py` | Apply Excel block map + merges; write blocked panel |
| `build_blocks_excel.py` | Seed/regenerate `layout_blocks.xlsx` from layout XML |
| `generate_nx_pairs.py` | List Entry/Exit pairs for manual JMRI add |
| `sync_linear_panel.py` | Align `linear.xml` working file to authoritative panel |

Other scripts in `scripts/` are one-off layout edits (stubs, trim, hex arcs, schematic build).

## Typical workflow (existing Mac layout)

```bash
cd /Users/lnevo/Panel
export JMRI_LAYOUT=mac

# Normal run (authoritative panel as source)
python3 jmri/scripts/apply_blocks_to_panel.py

# Refresh track geometry from AnyRail
python3 jmri/scripts/apply_blocks_to_panel.py \
  jmri/layouts/mac/anyrail/upper_both4.xml \
  jmri/layouts/mac/output/mac_jmri_blocked.xml \
  jmri/layouts/mac/authoritative/mac_jmri2.xml \
  use-panel-layout
```

Defaults resolve via [`layout_paths.py`](layout_paths.py) when arguments are omitted.

## Documentation

- [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) — full handoff / script behavior
- [`docs/SENSOR_NUMBERING.md`](docs/SENSOR_NUMBERING.md) — ISIS block vs NX numbering
