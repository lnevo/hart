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

- **Upper band after the helix-top move.** The helix-top switches (T285, T251, T175, T199) are drawn on the
  upper band with H1/H2 there and connector A at T199 (`levels.assign`). With the moved T300 right-hand it
  draws with no faults or warnings and the peninsula loop runs round the outside of its spurs at the east,
  as the owner prefers. H1, H2 and A sit below the band's middle, pointing east (`helix_side`), not at an end;
  the run from T262 up to T237 is one long slope. The moved T300's hand was found by trial.
- **Rows are stricter than they need to be.** Two tracks are kept on separate rows whenever the working
  order had them open together, even if they end up nowhere near each other along the band. On the upper
  band this stops the helix tracks sitting directly under T300: the peninsula's lower spurs claim those rows
  although they lie further east. The fix is to take the above/below rules only from tracks that really
  overlap along the band. Hints `keep_close`, `level_leg` and `band_cell` (stretch) exist meanwhile.
- A band has no rule for which end is which except `left_end` (staging) and `side` on helix ends (upper).
- Main weight on the upper band follows `main_route`, as the owner gave it (2026-11-13): H2 McKeesport up
  the rise to T262, diverging there onto the outer track round the west balloon loop (T275, T273, T256, T233)
  back to T274 and T237, then T300, the double crossover, round the peninsula loop past T241 and back; and
  H1 McKees Rocks through T175 and T199 to connector A. The T237 to T262 crossover is not main. Routes are
  spelled hop by hop, because the shortest way between two points can cut across a crossover.
- `shorten` draws a named run short (T237 to T300).
- AnyRail's section names (Mainline, Branchline) are layer placeholders (owner, 2026-11-13); band titles are
  the spike's own.
- Labels are not checked for collisions (the connector text can overlap a track); switch numbers collide in
  places; a crossover's number is printed on both halves; no page folding; no capacity.
- Switch labels on the main and upper bands are plan part numbers, three junctions unmatched; no names there.
