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
| (1,5) | OS Main West | (1,5) LEFT | added rim cell, extends drawn main west |
| (2,5) (3,5) | **OS 1** | (2,5) LEFT | SW100, points on (3,5) LEFT, **normal TOP** to Plane, diverge RIGHT |
| (4,5) (5,5) | **OS 3** | (4,5) LEFT | SW101, points on (5,5) LEFT, normal RIGHT, diverge TOP |
| (6,5) (7,5) | OS W-2 | (6,5) LEFT | east of OS 3 normal |
| (5,4) (6,4) (7,4) | OS W-1 | (5,4) BOTTOM | OS 3 diverging leg, heads toward South Yard |
| (3,4) (4,4) | OS Brick-Plane | (3,4) BOTTOM | the Brick→Plane diagonal |
| (4,3) (5,3) | **OS 5** | (4,3) BOTTOM | SW102, points on (5,3) LEFT, normal RIGHT, diverge TOP |
| (6,3) | OS East Main Ext | (6,3) LEFT | main east of Plane |
| (7,3) (8,3) | **OS 13** | (7,3) LEFT | points on (8,3) LEFT, normal RIGHT, diverge TOP to the crossover |
| (9,3) | OS Scale | (9,3) LEFT | east stub off OS 13 normal (South Yard / East End not drawn) |
| (5,2) (6,2) (7,2) | OS Barn | (5,2) BOTTOM | Plane diverging leg, row 2 lead to the crossover |
| (8,2) (9,2) (10,2) | **OS 7** | (8,2) LEFT | 117 points on (8,2) RIGHT; 117b points on (9,2) RIGHT |
| (9,1) (8,1) | OS EH-1 | (9,1) BOTTOM | westward stub off 117b top leg |
| (11,2) | OS Main East | (11,2) LEFT | added rim cell, extends drawn main east |

Earlier revisions of this doc put OS Brick-Plane at (6,4)(7,4). That was wrong:
OS Brick-Plane must join plant 100 to plant 102, which is the
(3,4)→(4,4)→(4,3) diagonal. (6,4)(7,4) hang off OS 3's diverging leg.

## Painted vs missing

**Designer primary (`HART.xml`):** Gate 1 only — 12×7 grid, 27 track cells, 14
named blocks. `EXTRA_CELLS` adds rim cells `(1,5)` OS Main West and `(11,2)` Main
East only. Rebuild refuses to write on any R2–R5 failure.

**LE WIP (`HART_le.xml`):** full occupancy name set (Gates 2–5 schematic) from
`build_hart_digicon_from_le.py` — see [`HART_DIGICON_MAP.md`](HART_DIGICON_MAP.md).
Do **not** invent South Yard / East End / Princess cells in
`wire_designer_ctc_rules.py`; draw those in Designer or use the LE board.

**Still coarse / merged on Designer Gate 1:**

| Block | Why |
|-------|-----|
| OS W-1 as its own main-line block | only one cell between SW100 and SW101 |
| OS 7b | throat adjacent to OS 7 (merged into OS 7 name) |
| OS 11, OS 9 | not in Designer draw yet (present on LE WIP) |
| South Yard / East End / Princess | Gates 3–5 — Designer draw or LE WIP |

Turnout `points_command` IO is deliberately not wired yet — the panel is a
magnet board plus occupancy. See `cats/data/turnout_bindings.csv`.

## Why the wiring looks the way it does

Derived from the CATS sources (`./tools/cats/fetch_cats_src.sh` → `tools/cats/src-repo`) and the golden
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
