# CATS source: why Digicon paints (or doesn’t)

Upstream: [Kb0oys/cats](https://bitbucket.org/Kb0oys/cats/src/master/) — local clone `tools/cats/src-repo/`.

## Paint gate

`TrackGroup.isVisible()` (`cats/layout/items/TrackGroup.java`): first track with a non-null `Block` returns `block.getVisible()`; if every track has `getBlock() == null`, returns **false** → `Section.showSec()` skips `GridTile` → **blank cell**.

So: no resolved VISIBLE block ⇒ no rails. Designer red track ≠ CATS paint.

That same method prints `Found a track in Section (x,y) that is not in a Block.`
to stdout for every unresolved cell, so the launch log is the oracle for
"did it paint" — grep it before trusting a screenshot.

## Edge types (`EdgeBuilder.addSelf`)

| SEC_EDGE child | Runtime class |
|----------------|---------------|
| `BLOCK` | `BlkEdge` (AbstractTrackEdge) |
| `SWITCHPOINTS` | `OSEdge` / `PtsEdge` (AbstractTrackEdge) |
| neither | plain `SecEdge` (**not** AbstractTrackEdge) |

`BLOCK` and `SWITCHPOINTS` must not share an edge.

## Blocks flow through turnouts

`PtsEdge.propagateBlock()` sets all of its tracks *and* forwards to its `Joint`,
so a turnout is **not** a block boundary. A "block region" is any set of cells
not separated by a `BLOCK` edge, and each region needs exactly one named visible
block (`Block.resolveBlocks()` anchors propagation at named blocks only; a bare
`<BLOCK />` starts as `Block.BlockHolder` and adopts whatever propagates in).

Consequence: a boundary can never sit at a plant throat, so the block holding an
OS always reaches back through its approach cell. `CTC-Tests/Chubb_CTC.xml`
`Block 14` = approach (12,3) + OS (13,3).

## ClassCast rules (load-time / first occupancy)

1. `BlkEdge.neighborOccupied()` does an unchecked `(BlkEdge) getNeighbor()`, so a
   `BLOCK` edge must be met by a neighbour edge that also carries a `BLOCK`.
   Pair named `BLOCK` with `<BLOCK />` (see `CTC-Tests/ctc_straights.xml`).
2. Never put a `BLOCK` opposite `SWITCHPOINTS` — leave that joint **plain**
   (`simpleSpur-ctc.xml`).
3. A `BLOCK` on an edge with **no neighbour cell** (panel rim, end of track) is
   fine — `XEdgeCTC.xml` (1,1) does exactly this.
4. `BLOCK` on a turnout cell's own non-points edges **is** legal: `Chubb_CTC.xml`
   (29,4) carries `<BLOCK />` on both frog legs, and (27,5)/(29,5) carry *named*
   blocks on a frog leg.

## Other load-time traps

- `DISCIPLINE` only accepts `UNDEFINED|ABS|APB|CTC|DTC` (`Discipline.java`).
  The `YARD` values in `cats/data/occupancy_bindings.csv` are **not** valid CATS
  disciplines and are written as `CTC`.
- `Compression` ("Compress Screen", `cats/gui/Compression.java`) defaults to
  **true** and shrinks every horizontal-only column to a sliver. `BooleanGui.
  newElement()` sets the flag to `!default` from the element merely being
  present, so a bare `<COMPRESSIONTAG />` turns it off.
- `Screen.FixSize` is hardcoded `true`, so CATS never scales cells to the
  window. `GridTile.Size` is a runtime-only 30×30 default that is *not* stored
  in the panel file — enlarge via CTC Panel menu **Appearance → Grid Size**.

## Track geometry → edges

| TRACK | Connects |
|-------|----------|
| `HORIZONTAL` | LEFT ↔ RIGHT |
| `VERTICAL` | TOP ↔ BOTTOM |
| `UPPERSLASH` | LEFT ↔ TOP |
| `LOWERSLASH` | RIGHT ↔ BOTTOM |
| `UPPERBACKSLASH` | RIGHT ↔ TOP |
| `LOWERBACKSLASH` | LEFT ↔ BOTTOM |

A two-track cell is a turnout: the edge shared by both tracks carries
`SWITCHPOINTS`, and `ROUTEINFO ROUTEID` uses the other two edge names.

## Golden patterns

- Straights: `CTC-Tests/ctc_straights.xml`
- Turnout: `CTC-Tests/simpleSpur-ctc.xml`, `CTCUpperPassing.xml` (H+UPPERSLASH)
- Tight plants / named blocks on frog legs: `CTC-Tests/Chubb_CTC.xml`
- Crossover: `CTC-Tests/SimpleXoverCTC.xml`

## HART tooling

```bash
python3 cats/scripts/wire_designer_ctc_rules.py --mqtt
# → cats/panels/HART_magnet.xml  (Designer XY + CTC-Tests edges)
# → cats/panels/HART.xml         (+ occupancy)
python3 cats/scripts/dump_cats_grid.py cats/panels/HART_magnet.xml   # inspect any panel
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_magnet.xml
```

The builder self-checks rules 1–4 above plus "every region has exactly one named
block" and refuses to write on failure. Cell map:
[`DESIGNER_DRAWING_REVIEW.md`](DESIGNER_DRAWING_REVIEW.md).
