# Data masters

`entities.csv` lists each kind of record on the layout and says which one file in this repo is the master.

## Columns of `entities.csv`

- `kind`: the kind of record, such as loco, industry or block.
- `key`: the column whose value names one record. It is assigned once and never reused, and it does not depend on row order or on a public name.
- `master`: the one repo file that owns the records. A change to a record is made here first.
- `copies`: other repo files that hold the same records, such as a column in another file or a file built from the master. Each copy is built from the master or checked against it.
- `outside_tools`: programs that keep their own copy of the records, such as STS, Operations Pro, JMRI, DecoderPro, CATS and the website.
- `wins_in_session`: which side is right while the layout is operating. Identity and design data come from the repo. State that the layout creates, such as where a car is, comes from the tool that records it.

Items inside a cell are separated by `;`, so the file needs no quoting.

## Master and copy

A master is the file a person edits. A copy is never edited by hand. A copy in the repo is written from the master by a script, or a check fails when it disagrees. A copy in an outside tool is brought into line by a reconcile step (phase 2 of ADR-039).

A spreadsheet, a slide deck or a JSON file for the site is never a master. It is written from the masters.

## Masters the owner chose (2026-11-25)

- **Locos:** `ops/hart-ops/data/locos.csv`, extended to every loco that runs. The engine rosters and the `engine` column of the train list are copies.
- **Industries:** a new `ops/hart-ops/data/industries.csv` (`industry_id`, name, public name, slug). `spot_assignments.csv` stays the master for spots and refers to `industry_id`.
- **Trains:** a new `ops/hart-ops/data/trains.csv`, keyed on `train_symbol`. `cats/data/hart_trains.csv` is built from it for CATS, and the site reads it.
- **Stations and control points:** two files with new ids. `schematic/stations.csv` owns stations (`station_id`) and `schematic/interlockings.csv` owns control points (`cp_id`). Every `cp` cell then holds ids.

Which script writes or reads a given file is in `docs/pipeline-map/pipeline_map.json`. The rule is in [ADR-039](../../wiki/decisions/ADR-039-data-masters-in-git.md).
