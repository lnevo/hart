# HART Operator Portal (consolidation)

Light, operator-facing static site **inside** the consolidation workspace:

`consolidation/ops-portal/`

It does **not** replace the dark engineering desk at [`../index.html`](../index.html). All content is drawn from consolidation SoR and mirrors (`sor/`, `external/hart-runtime/`, `external/hart-ops/`, `html/`, `wiki/`, `packages/`).

## Open

Open in a browser:

```
consolidation/ops-portal/index.html
```

## Rebuild layout data

```bash
python3 consolidation/ops-portal/scripts/build_layout_index.py
```

**Inputs (consolidation only):**

- `external/hart-runtime/jmri/layouts/hart/output/hart_prod.xml`
- `sor/names/public_name_map.csv`
- `sor/names/hart_devices_review.json`
- `external/hart-runtime/jmri/layouts/hart/data/control_points.csv`
- `external/hart-ops/publications/assets/station_map_*.png`

**Outputs:**

- `data/layout-index.json`
- `assets/layout/HART_le_schematic.png`
- `assets/maps/*.png`

(The schematic render helper lives at `cats/scripts/render_le_layout.py` but is only fed the consolidation panel XML.)

## Sections

| Path | Role |
|------|------|
| `layout/` | Annotated LE schematic + hotspot detail |
| `roster/` | Filterable device table |
| `guides/` | USS / CATS Digicon / Auto Dispatcher / Digicon overview |
| `tools/` | STS, Mimic, JMRI deep links (`data/site.json`) |
| `reference/` | Pointers into consolidation SoR / pubs / wiring |
| `gallery/` | Station maps + schematic |

## Hosting

`file://` / static for now. Pi static copy beside STS is deferred (consolidation portal-hosting ADR).
