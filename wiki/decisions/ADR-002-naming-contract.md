# ADR-002 — Public naming contract (CP / OS / tracks)

- **Status:** Accepted (amended 2026-08-20 by [ADR-005](ADR-005-public-equipment-names.md))
- **Date:** 2026-08-07
- **Deciders:** lnevo

## Context

The panel mixes `Switch 10x`, MQTT system names, geography, and station labels. Dispatcher feedback: one public language; equipment IDs stay secondary.

## Decision

### Label hierarchy (visible)

1. **Area** — Neville Island, West Yard, South Yard, Industries, directions  
2. **Control point** — Brick, Plane, Barn, East End, Princess
3. **Track** — Main West, Main East, S-1…S-5, Scale / Barn / East Lead
4. **Equipment** — DCC / switch numbers (100–119) as small labels only  

### Block user names (public)

| Role | Pattern | Example |
|------|---------|---------|
| Switch / plant OS | `OS <n> (<CP>)` | `OS 100 (Brick)` |
| Crossover leg | `OS <n><a\|b> (<CP>)` | `OS 111a (East End)` |
| Main track limit | `<Track> <CP west>–<CP east>` where helpful | `Main East Brick–East End` |
| Yard body | `<Yard> <track>` or plate | `West Yard 1`, `S-3` |
| Interchange | Geographic name | `McKees Rocks`, `McKeesport`, `PIR` deferred |

Switch / MQTT / DCC IDs remain in turnout table comments and mapping CSVs — not as the only block name.

### Control point → switches (phase 2)

| CP | Switches |
|----|----------|
| Brick | 100, 101 |
| Plane | 102 |
| **Barn** | 117, 117b |
| South Yard | 103, 104, 105, 106 |
| East End | 107, 108, 109, 110, 111a, 111b, 112 |
| Princess | 113a, 113b, 114, 115 |

Source of truth for this pass: [`jmri/layouts/hart/data/public_name_map.csv`](../../jmri/layouts/hart/data/public_name_map.csv) (ADR-005). `block_display_names.csv` is historical.

## Consequences

- Phase 2 renames layoutblock / block userNames via CSV + bootstrap/apply script.
- Signal work (later) names masts from CP + direction + track.
- NextTrain (later) must use the same public names.

## Alternatives considered

- Keep `Switch 100` as public block names — rejected for dispatcher readability.
- Aggregate one block per CP OS — deferred; keep per-switch OS for detection purity.
