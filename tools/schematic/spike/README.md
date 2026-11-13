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

Staging is now drawn from the AnyRail export too, not from the Layout Editor panel (owner's choice,
2026-11-13): `export_reader.py plan.xml staging.json +Staging parts.json`, then the as-built edits in
`staging_opts.json` (relabel plan parts to switch numbers, drop the unbuilt crossover T41/T43, add the
Switch 7 crossover, Switch 13 and the engine terminal, name the tracks). Sample: `staging_sample.svg`.
`le_reader.py` and `built_opts.json` remain as a cross-check against the panel.

`system.py` puts staging, the main level and the upper level on one sheet in route order from the bottom up
(sample in `system_sample.svg`). Each band's helix tracks end in a HELIX box and carry the same track names on
both levels: the main level's helix track from T175 is McKees Rocks and the one from T251 is McKeesport
(owner confirmed, 2026-11-13).

The spike checks its own drawing: every pair of drawn lines is tested for crossing or lying on top of
each other, and each fault is printed with the switches either side.

Main levels (2026-11-13), from the 5.3b export with the owner's as-built change (`main_asbuilt_opts.json`,
sample in `main_asbuilt_sample.svg`):

| Drawing | Faults |
|---------|--------|
| One flat band | 52 crossings or overlaps, 2 switches whose leg must cross other track, 36 ordering rules dropped |
| Two bands, cut at the rise | 3 crossings on the upper level |
| Two bands, coincident track ends joined, loops ordered by their bend | 0 on both bands |

What fixed it: level bands with lettered connectors; choosing each switch's level leg so no above/below rule
is broken; keeping other track clear of the columns a sloped leg passes through; a double crossover's two
tracks on neighbouring rows; joining track ends the export leaves on the same spot (two pairs in 5.3b, one
of them the main level's balloon loop at T196); stacking a loop's two tracks by which way the loop bends on
the layout; trying the cheapest few fold-back choices and keeping the one that draws with the fewest faults. Two
tracks that never run side by side are kept apart along the row, not stacked on separate rows (this is what
had pushed T155 to the bottom). A long track always gets a level run, so the three parallel tracks west of
T162 and T160 show as three.

Known gaps (end of the 2026-11-13 session):

- **Upper band after the helix-top move.** The owner asked for the helix-top switches (T285, T251, T175, T199)
  to be drawn on the upper band, with H1/H2 there and connector A at T199 (`levels.assign` in
  `main_asbuilt_opts.json`). It draws without crossings, but H1 and H2 sit mid-band instead of at the west
  end, the double crossover spans three rows and is reported with its two tracks in swapped order (not
  verified to connect the right tracks), and the moved T300 is set left-hand by trial. This band needs its
  rows and ends worked out next.
- A band has no rule for which end is which except `left_end` (staging) and `side` on helix ends (upper).
- Main weight on the upper band follows `main_route`, chosen by the agent, not the owner.
- AnyRail's section names (Mainline, Branchline) are layer placeholders (owner, 2026-11-13); band titles are
  the spike's own.
- Labels are not checked for collisions (the connector text can overlap a track); switch numbers collide in
  places; a crossover's number is printed on both halves; no page folding; no capacity.
- Switch labels on the main and upper bands are plan part numbers, three junctions unmatched; no names there.
