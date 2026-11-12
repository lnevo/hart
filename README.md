# HART

The Neville Island model railroad: JMRI tables and panels, a CATS CTC overlay, wiring and operations material, and the public website.

**Start here:** [`wiki/home.md`](wiki/home.md) · [`AGENTS.md`](AGENTS.md)

## Layout of this repo

| Folder | Purpose |
|--------|---------|
| `jmri/` | JMRI layout, tables, resources, and the AnyRail tools |
| `cats/` | The CTC overlay only |
| `docs/` | Wiring, CTC, benchwork and ops documents |
| `www/` | The public website |
| `ops/` | Station maps, car cards, operating packages |
| `external/` | Submodules and STS data |
| `media/` | Photos, video and archive material (gitignored) |
| `tools/` | Checks, MQTT and host helpers |
| `wiki/` | Decisions, status and pipelines |
| `archive/` | Retired material; nothing here runs |

See [ADR-007](wiki/decisions/ADR-007-repository-layout.md).

## Quick commands

```bash
# Pipeline 1 — build a blocked panel from AnyRail
export JMRI_LAYOUT=hart
python3 jmri/scripts/apply_blocks_to_panel.py \
  jmri/layouts/hart/anyrail/hart.xml \
  jmri/layouts/hart/output/hart_blocked.xml \
  jmri/templates/panel_style.xml \
  use-panel-layout
```


## License

The code and the documents written for this repository are under the [MIT License](LICENSE).

Some material here belongs to others and keeps its own terms:

- **Railroad and industry logos** (`ops/hart-ops/operator_logos/`, and their copies on the website) are trademarks of their owners, used for reference. Sources: [`SOURCES.md`](ops/hart-ops/operator_logos/SOURCES.md).
- **Historical photos and archive items** belong to the sources credited beside them.
- **Submodules** under `external/` carry their own licenses.
- **Files from JMRI and CATS** keep their projects' licenses.
