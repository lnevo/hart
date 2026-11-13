# Schematic spike (stage 0)

Proof of the construction in [`wiki/projects/schematic-maps.md`](../../../wiki/projects/schematic-maps.md).
Not tested, not wired into `check.sh`; the tested version goes in `model-railroad-skills`.

    python3 le_reader.py ../../../jmri/layouts/hart/output/tables.xml \
        ../../../jmri/layouts/hart/data/switches.csv ../../../jmri/layouts/hart/data/block_lengths.csv built.json
    python3 schem.py built.json built.svg built_opts.json

`built_sample.svg` is that output for the built staging level, with no hand placement.
`any_reader.py` builds the same logical graph from the AnyRail prototype reader's `parts.json` and `graph.json`.

How `schem.py` works:

1. **Orient.** Each switch faces left or right. Runs that must double back are turnbacks; the choice with the fewest, most U-shaped turnbacks wins.
2. **Sweep.** Walk left to right keeping the tracks in top-to-bottom order, using each switch's hand.
3. **Rows.** Each switch keeps one leg level. Rows are chosen to make the sloped legs as short as possible.
4. **Columns.** Every track gets room for its name; long tracks take up the slack.
5. **Draw.** SVG on a Letter landscape sheet.

`export_reader.py` reads AnyRail's "export to JMRI" XML, which is the better input: it holds the double
crossover and every turnout, and only track. It has no heights; those still come from the `.any` reader.

Known gaps (2026-11-13):

- The main levels (50 turnouts and a double crossover from the 5.3b export) draw, but the west end is a
  tangle. Tracks pass over each other there (the 2.1% rise from the height-0 main to the 4.25 in branch
  line), and the spike draws everything as one flat band. The fix is the plan's level bands: cut the
  graph at the graded runs and draw each level as its own band with lettered connectors.
- Where the layout is not flat the row step drops ordering rules (35 on the main levels), so tracks can
  overlap. That fallback should go once level bands exist.
- Switch numbers collide on yard ladders; a crossover's number is printed on both halves.
- No page folding, no capacity, no as-built overrides file yet.
