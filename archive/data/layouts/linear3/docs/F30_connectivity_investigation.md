# F30-S-0 / F51–F26 connectivity investigation

## Original AnyRail topology (`anyrail/linear3.xml`)

| Segment   | Connects |
|-----------|----------|
| **F51-S-0** | A51 ↔ A2 |
| **F30-S-0** | A51 ↔ A3 (9.5° arc, `hidden="no"`) |
| **F26-S-0** | A3 ↔ A23 |

Anchors **A51** and **A3** each join two segments: F51+F30 and F26+F30.  
**F30-S-0 is the link between F51-S-0 and F26-S-0.** Without it, those two segments only meet at separate anchors with no connecting track.

## Was F30 ever “hidden”?

**No.** In every linear3 file checked:

- `anyrail/linear3.xml` — `hidden="no"`
- `authoritative/linear3.xml` — `hidden="no"`
- No linear3 layout uses `hidden="yes"` on any segment.

F30 may *look* like extra/hidden construction (short arc parallel to F51/F26 near TOL42), but it is normal visible geometry from AnyRail, not copied from mac hidden tracks.

## Mac “hidden tracks” — separate issue

`apply_blocks_to_panel.py` can copy **mac** hidden segments (`F35585-S-0`, `F35586-S-0`, etc.) when `apply_hidden_tracks_from_defaults` runs with **mac** as the defaults file.

On an early linear3 run (before a code fix), one apply reported:

`Hidden tracks from defaults: 0 set hidden, 4 added`

Those four would be **mac-only** idents, not F30. They are **not** in the current `linear3_blocked.xml`.  
Since then, `use-panel-layout` skips mac labels **and** hidden-track import so mac geometry is not appended to linear3.

## What actually broke F51 ↔ F26

We added `exclude_segments.txt` with **F30-S-0** and ran `remove_track_segments.py`, which:

1. Deleted the F30 segment
2. Patched A51 and A3 to drop the F30 connection

That removed the only track between the F51 and F26 legs — **not** a hidden-track cleanup.

## Revert

- `data/exclude_segments.txt` cleared (F30 documented, not excluded)
- Pipeline re-run from `anyrail/linear3.xml` without `remove_track_segments.py`
- F30 restored; 98 segments in blocked panel and dispatcher Excel
