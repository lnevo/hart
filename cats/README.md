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

## Run (local)

1. Start JMRI with the HART profile; load `jmri/layouts/hart/output/hart_prod.xml` (hardware/monitor).
2. From `tools/cats/release3.2/`, run `./designer.csh` or `./cats.csh` (see package `ReadMe.pdf`).
3. Open sample `examples/ArmstrongMagnet.xml` first (magnet board), then follow [`docs/HART_DESIGNER_BUILD.md`](docs/HART_DESIGNER_BUILD.md).
4. Save Designer work under `cats/panels/HART.xml` (create via Designer — do not invent a full TRACKPLAN by hand).

## Authority rule

Only **one** UI may command turnouts/routes in a session: **CATS** (CTC) *or* NextTrain *or* Layout Editor click-to-throw. Others stay view-only.

Do **not** save CATS-created SignalHead/Mast objects into JMRI tables (load-crash risk).

## Guides

- Manuals (after fetch): `tools/cats/release3.2/{DesignerManual,catsManual,ReadMe}.pdf`
- Site: [User Guides](http://cats4ctc.wikidot.com/main:userguides)
