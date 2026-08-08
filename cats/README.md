# CATS integration (HART)

[CATS](http://cats4ctc.wikidot.com/) is a Digicon-style CTC suite that runs **on JMRI** for hardware I/O and owns interlocking via a **Designer** panel XML (not a Layout Editor import).

| Piece | Role |
|-------|------|
| **Designer** | Draw CTC schematic; bind JMRI sensors/turnouts/signals |
| **CATS** | Runtime dispatcher panel (routes, N/X, occupancy colors, train labels) |
| **TrainStat** | Optional yard/trainmaster client ([download](http://cats4ctc.wikidot.com/main:downloadts)) |

**SoR:** [`wiki/decisions/ADR-004-cats-ctc.md`](../wiki/decisions/ADR-004-cats-ctc.md)

## JMRI pin

Use **CATS 3.2** with **JMRI 4.24–5.16** ([downloads](http://cats4ctc.wikidot.com/main:downloads)).  
HART’s recent panels target JMRI **5.15.5** — compatible with 3.2.

```bash
./tools/cats/fetch_cats_3.2.sh   # → tools/cats/release3.2/ (gitignored binaries)
```

## Bindings from hart panel

```bash
export JMRI_LAYOUT=hart
python3 jmri/scripts/export_hart_devices_for_cats.py
```

| File | Use in Designer |
|------|-----------------|
| [`data/jmri_devices.csv`](data/jmri_devices.csv) | Full sensor/turnout catalog |
| [`data/occupancy_bindings.csv`](data/occupancy_bindings.csv) | Block → occupancy sensor userName |
| [`data/turnout_bindings.csv`](data/turnout_bindings.csv) | Layout OS → Switch / M2T* |
| [`data/plants_from_hart.csv`](data/plants_from_hart.csv) | CP → switch list |
| [`data/signal_mast_plan.csv`](data/signal_mast_plan.csv) | Planned mast slots |

## Decisions (Accepted)

- JMRI: **current** host (panel reports **5.15.4plus** — OK for CATS 3.2)
- CTC throws: **CATS**
- First plant: **Brick** — must be drawn in **Designer** ([why](docs/DESIGNER_REQUIRED.md))
  - Smoke test: [`panels/HART_smoke_Armstrong.xml`](panels/HART_smoke_Armstrong.xml) (Armstrong topology; should paint track)
  - Bindings cheat-sheet: [`docs/BRICK_BINDINGS.md`](docs/BRICK_BINDINGS.md)
- Validate: `python3 cats/scripts/validate_cats_panel.py`

## Install + run (macOS)

CATS **must** be copied into your JMRI folder (`cats.jar` next to `jmri.jar`). Running it from this repo alone fails with `Could not find or load main class cats.apps.Crandic`.

```bash
# once:
./tools/cats/fetch_cats_3.2.sh          # if needed
./tools/cats/install_into_jmri.sh       # → /Applications/JMRI

# each session (no sudo; quit PanelPro on the same profile first):
./cats/scripts/launch_cats.sh
# then File → Open → cats/panels/HART_Brick.xml

./cats/scripts/launch_designer.sh       # Digicon editor
```

`readelf` warnings on macOS from `cats.csh` are harmless ARM probes; prefer `StartJMRI -m cats.apps.Crandic` (what `launch_cats.sh` uses).

Also: sample `panels/reference_ArmstrongMagnet.xml`, guide [`docs/HART_DESIGNER_BUILD.md`](docs/HART_DESIGNER_BUILD.md).

## Authority rule

**CATS** commands turnouts/routes in CTC sessions. NextTrain and Layout Editor stay view / local (no dual-command).

Do **not** save CATS-created SignalHead/Mast objects into JMRI tables (load-crash risk).

## Guides

- Manuals (after fetch): `tools/cats/release3.2/{DesignerManual,catsManual,ReadMe}.pdf`
- Site: [User Guides](http://cats4ctc.wikidot.com/main:userguides)
