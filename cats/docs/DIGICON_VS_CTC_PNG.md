# What you’re looking at (CATS Digicon vs PR #4 PNG)

Three different pictures got mixed together:

| Artifact | What it is | Loads in CATS? | Shows occupancy / points? |
|----------|------------|----------------|---------------------------|
| **PR #4 `hart_ctc_panel.png`** | Pillow drawing — Class I CTC *look* (one main, OS plates, ladders) | **No** | **No** (static art) |
| **PR #4 `hart_ctc_0x_*.png`** | Pillow drawing of JMRI LE *geography* | **No** | **No** |
| **`HART_le.xml` in CATS** | Real Digicon TRACKPLAN (slash/H cells) | **Yes** | Yes, once MQTT/points wired |

So: the remote screenshots that “looked right” were **not** what CATS opens. CATS can only show a Digicon built from `SECTION` / `SWITCHPOINTS` / named `BLOCK`s.

## What a dispatcher Digicon should be

Not a scale map of Neville Island. A **CTC interlocking schematic**:

1. **One main track** west → east (Brick … Princess)  
2. **Each interlocking** = a plant (OS / CP) on that main or on a ladder lead  
3. **Yards** = entry turnout off the main → lead → rungs (119→118→116, 103→104→105→106, etc.)  
4. **Block names** = JMRI userNames (for MQTT red)  
5. **Labels** = short CP numbers + station names (100, 101, Brick, South Yard)

That is the PR #4 PNG *intent*, implemented as loadable Digicon cells.

## Target mapping (interlockings)

| CP | Area | Digicon role |
|----|------|--------------|
| 100 | Brick | Main plant; continuing = Brick-Plane |
| 101 | Brick | Yard / Main West side of Brick |
| 102 | Plane | Main plant; east = East Main Ext |
| 117 / 117b | West Yard | Entry / crossover on main ↔ EME |
| 119, 118, 116 | West Yard / engine | Ladder rungs |
| 103–106 | South Yard | Ladder |
| 111 / 111b | East End | Crossover to West Main Ext |
| 107–110 | East End | Ladder |
| 112 | East End | Main → East Lead |
| 113–115 | Princess | Loops (McKees Rocks / McKeesport) |

Rebuild: `python3 cats/scripts/build_hart_digicon_ctc.py --mqtt` → `cats/panels/HART_ctc.xml`  
Launch: `CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_ctc.xml`
