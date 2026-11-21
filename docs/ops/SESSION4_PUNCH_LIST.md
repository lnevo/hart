# Session #4 punch list (2026-11-08)

Feedback from operating session #4: the dispatcher's notes on DS-01 Rev D, the owner's punch list sheet, and the yardmaster notes. Consolidated 2026-11-14.

## Done

| Item | Where |
|------|-------|
| SW9 fixed by a wiring change | Layout |
| Lineup for the dispatcher: starting tracks, routes (origin → points → destination), three extras | DS-01 Rev E |
| CK1 starts at the Engine House and terminates on S-4 | DS-01 Rev E |
| Extras: Extra CK coal (McKeesport → South Yard), X9602 scale tank, X1993 coal extra (drop and pick up at the loop, terminate at South Yard) | DS-01 Rev E |
| NVL may start before Route 23 AM, cleared to East End, so it is out of the helix and clear of the Princess crossover before Route 23 arrives. Lineup order unchanged | DS-01 Rev E |
| The dispatcher throws the Switch 7 crossover at Barn only with the yardmaster's permission | DS-01 Rev E, YM-01 Rev E |
| Yard blocking list: NVL local (yellow, green, purple, red, pink), CSX (blue), P&OV (orange), CK1 (black), yard storage (no color) | YM-01 Rev E |
| Work train parks on EH-1, the engine terminal back track, not in the yard | YM-01 Rev E |
| S-R labelled as the run-around (long siding) | Owner, already done |

## Open: agent work

| # | Item | Notes |
|---|------|-------|
| 4 | Control point signs for every interlocking rail gap, sized for a stick in the benchwork | Printable |
| 5 | Big crew board listing the jobs in sign-up order | Printable |
| 6 | Mock signal design for the interlocking gaps, if wanted | Printable or STL |

## Open: owner

| # | Item | Notes |
|---|------|-------|
| 7 | Resistor wheels | Needed before standing cars between Princess and East End show, and before the train label "bounce" is looked at |
| 8 | Put up mock signals at every interlocking rail gap so crews know where to stop | With the CP signs (item 4) beside them |
| 9 | Print and mount the crew board (item 5) | |
| 3 | Mark the rail gap between East End and Princess | On the layout |
| 10 | Wire the drill signal on the Barn lead | The signal is already installed, not yet wired. See below |

### Drill signal

A drill track is a yard lead that crews use for switching ("drilling") cars. A drill signal is a dwarf at the lead's end. It tells the yard crew whether they may pull out past the lead onto the Switch 7 crossover at Barn. It goes with the crossover rule: the yardmaster asks for the move, and the dispatcher lines it and clears the signal.

The signal is already on the layout; it needs wiring. The wiring plan has one dwarf at Barn: Mast 8LB on Switch 7 reverse. It is head IH1334, LCOS Signal 2 on C13, at ports C13-OU3-7, C13-OU3-8 and C13-OU4-7 (the old `docs/wiring/signals/signal_wiring.csv`; the wiring source is now `jmri/layouts/hart/data/wiring.csv`, which lists the heads only once they are wired). If the drill signal is a different one, it needs its own entry in the plan.

## Deferred

- More labels on the dispatcher panel, for example Shenango (item 1): on hold, since the panels are mostly temporary.
- Train labels "bounce" or are left behind on the panel: mostly cars without resistor wheels. Look again after item 7.
- No indication of standing cars between Princess and East End: the same cause.
