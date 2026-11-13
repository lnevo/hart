# Switch facts

Where the facts about each switch live, how to change one, and the check that holds the Layout Editor, the CATS desks and the USS CTC to them.

## The files

| File | One row per | Holds |
|------|-------------|-------|
| `jmri/layouts/hart/data/switches.csv` | switch | `level`, `switch` number, Layout Editor turnout (`le_ident`), `cats_inverted` (CATS Normal is the thrown leg: Switch 1 only), USS lever sensors (`ctc_is`), whether the USS column has signal levers (`ctc_signals`) |
| `jmri/layouts/hart/data/switch_legs.csv` | OS block at the points | `closed_leg` and `thrown_leg`: the block each leg leads to. A crossover has two rows; the first is its main OS block |
| `public_name_map.csv` (turnout rows where current = proposed) | turnout | hardware ID, DCC address (in `comment`), control point |
| `control_points.csv` | control point | the switches it holds |

Track names are the CATS occupancy names (`Track S-R`). A Layout Editor throat block such as `Track S-R West`, on the same occupancy sensor, counts as `Track S-R`. `jmri/layouts/hart/scripts/layout_facts.py` reads the files. `wire_digicon.py` takes each CATS Normal leg and inversion from them, and `gen_ctc_track_plan.py` takes the USS lever columns, points dots and station plates. CATS grid cells stay in `wire_digicon.py` (`PLANT_CELLS`).

## Changing a switch

Example: after a rewiring, Switch 9 normal leads to EH-2 and thrown to EH-3.

1. Edit its row in `switch_legs.csv` (and `switches.csv` if its inversion or lever changes).
2. In PanelPro, set the turnout's continuing sense and fix the OS block paths, then Store and run `make tables-pull` (ADR-008). Nothing edits `tables.xml` by script for this.
3. If the CATS drawing needs other track names, change `ANCHORS` in `wire_digicon.py` or the Designer save, then run `python3 cats/scripts/wire_digicon.py`. It stops if a desk leg cannot reach the block the data names.
4. Rebuild the USS panel: `python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py`.
5. Run `python3 tools/audit/check_layout_facts.py` (also in `tools/check.sh`). Each failure names the switch or track and the two sources that disagree.

A new level adds rows with a new `level` value. Its plant cells go in `PLANT_CELLS`, and its USS columns follow from the plate numbers.

## What the check covers

- **Layout Editor:** turnout hardware and DCC address, layout turnout name and OS block, the leg the continuing sense closes to, and the stored block paths for both legs.
- **CATS desks** (`HART_CTC.xml`, `HART_ABS.xml`) and `cats/data/turnout_bindings.csv`: the turnout on each plant, where the close and throw legs lead, which leg is Normal, and that every desk block is a Layout Editor block.
- **USS CTC:** each code button's turnout, OS sensors, lever and signal levers. In both copies of the panel, each column's lever and points dot, and the track jewels and labels matching a fresh build from the CATS desk.

`KNOWN` in the check lists differences already reported to the owner. They print without failing. An entry that stops happening fails until someone removes it.
