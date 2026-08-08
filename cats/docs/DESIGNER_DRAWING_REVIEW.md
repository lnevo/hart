# Designer board map (built, loaded, painting)

`cats/panels/HART.xml` and `cats/panels/HART_magnet.xml` are now built from
**your Designer draw** (`cats/panels/HART_designer_raw.xml`). The Armstrong
chassis is gone from both — only the Armstrong *header* (fonts, colours, signal
template, train/job/crew stores) is reused as a shell.

27 track cells, 14 named visible blocks, window 560×380.

## Rebuild (one command)

```bash
python3 cats/scripts/wire_designer_ctc_rules.py --mqtt
# -> cats/panels/HART_magnet.xml          magnet board, no JMRI IO
# -> cats/panels/HART_designer_wired.xml  identical copy for diffing
# -> cats/panels/HART.xml                 + MQTT occupancy on all named blocks

CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_magnet.xml
```

The script refuses to write if its own structural check fails, so a bad edit
cannot reach a launch. Inspect any panel with:

```bash
python3 cats/scripts/dump_cats_grid.py cats/panels/HART_magnet.xml
```

Cells are 30×30 px and that size is runtime-only in CATS (never stored in the
panel file). To enlarge the board use the CTC Panel menu **Appearance → Grid
Size**.

## Cell map

Row/col are Designer `X`,`Y`. "Region" is the set of cells sharing one CATS
block; the **named** column is where the `BLOCK NAME=` anchor lives.

| Cells | Block | Anchor edge | Notes |
|-------|-------|-------------|-------|
| (1,5) | Main West | (1,5) LEFT | added rim cell, extends drawn main west |
| (2,5) (3,5) | **OS 100 (Brick)** | (2,5) LEFT | SW100, points on (3,5) LEFT, **normal TOP** to Plane, diverge RIGHT |
| (4,5) (5,5) | **OS 101 (Brick)** | (4,5) LEFT | SW101, points on (5,5) LEFT, normal RIGHT, diverge TOP |
| (6,5) (7,5) | West Yard 2 | (6,5) LEFT | east of OS 101 normal |
| (5,4) (6,4) (7,4) | West Yard 1 | (5,4) BOTTOM | OS 101 diverging leg, heads toward South Yard |
| (3,4) (4,4) | Block 100-102 | (3,4) BOTTOM | the Brick→Plane diagonal |
| (4,3) (5,3) | **OS 102 (Plane)** | (4,3) BOTTOM | SW102, points on (5,3) LEFT, normal RIGHT, diverge TOP |
| (6,3) | East Main Ext | (6,3) LEFT | main east of Plane |
| (7,3) (8,3) | **OS 116 (West Yard)** | (7,3) LEFT | points on (8,3) LEFT, normal RIGHT, diverge TOP to the crossover |
| (9,3) | Yard T1 | (9,3) LEFT | east stub off OS 116 normal (South Yard / East End not drawn) |
| (5,2) (6,2) (7,2) | Yard T6 | (5,2) BOTTOM | Plane diverging leg, row 2 lead to the crossover |
| (8,2) (9,2) (10,2) | **OS 117 (West Yard)** | (8,2) LEFT | 117 points on (8,2) RIGHT; 117b points on (9,2) RIGHT |
| (9,1) (8,1) | Yard T9 | (9,1) BOTTOM | westward stub off 117b top leg |
| (11,2) | Main East | (11,2) LEFT | added rim cell, extends drawn main east |

Earlier revisions of this doc put Block 100-102 at (6,4)(7,4). That was wrong:
Block 100-102 must join plant 100 to plant 102, which is the
(3,4)→(4,4)→(4,3) diagonal. (6,4)(7,4) hang off OS 101's diverging leg.

## Painted vs missing

**Painted:** Designer Gate 1 plus scripted Digicon expansion (22×7 grid, 59
track cells, 31 named blocks). Rebuild refuses to write on any R2–R5 failure.

**Now on the board** (EXTRA_CELLS in `wire_designer_ctc_rules.py`):

| Area | Named blocks |
|------|----------------|
| South Yard | OS 103–106, Yard Track 1/3/4/5 |
| East End | OS 107, 109, 111a, 112, East Lead |
| Princess / loops | OS 113b, OS 115, McKees Rocks, McKeesport |

**Still coarse / merged** (throat geometry — fix by drawing extra approach cells):

| Block | Why |
|-------|-----|
| West Yard 1 as its own main-line block | only one cell between SW100 and SW101 |
| OS 117b | throat adjacent to OS 117 |
| OS 108 / OS 110 | owned by 111a / 109 through plant throats |
| OS 114 | merged into OS 113b |
| Yard Track 2 | OS 106 owns (18,3) through its throat |
| OS 118, OS 119 | not drawn yet |

Turnout `points_command` IO is deliberately not wired yet — the panel is a
magnet board plus occupancy. See `cats/data/turnout_bindings.csv`.

## Why the wiring looks the way it does

Derived from the CATS sources in `tools/cats/src-repo` and the golden
`CTC-Tests` panels; `Chubb_CTC.xml` is the reference for tight plants. Full rule
list is the module docstring of `cats/scripts/wire_designer_ctc_rules.py`. The
two that drive every layout decision:

- `PtsEdge.propagateBlock()` forwards the block to its joint, so **blocks flow
  through turnouts**. A block region is any set of cells not separated by a
  `BLOCK` edge, and each region needs exactly one named visible block.
- `BlkEdge.neighborOccupied()` does an unchecked `(BlkEdge) getNeighbor()`, so a
  `BLOCK` edge must be met by another `BLOCK` edge and must never face
  `SWITCHPOINTS`. This is what makes a boundary at a plant throat impossible,
  and why an OS block always reaches back through its approach cell — exactly
  what Chubb does (`Block 14` = approach (12,3) + OS (13,3)).

`BLOCK` on a turnout cell's non-points edges **is** legal — Chubb (29,4) carries
an anonymous `BLOCK` on both frog legs and (27,5)/(29,5) carry named blocks on a
frog leg. Earlier notes claiming otherwise were wrong and cost the west end its
block granularity.

Paint rules: [`CATS_SOURCE_PAINT.md`](CATS_SOURCE_PAINT.md).
