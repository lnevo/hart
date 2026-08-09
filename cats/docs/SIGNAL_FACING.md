# Digicon signal facing (West Yard2)

Panel lamps (`SECSIGNAL` / `PANELSIGNAL`) tip **into** the named BLOCK on that edge.

| Edge | `SIGORIENT` |
|------|-------------|
| LEFT | RIGHT |
| RIGHT | LEFT |
| TOP | BOTTOM |
| BOTTOM | TOP |

Place each CP lamp on the **OS-named** face of the plant cut (entry into the interlocking), not on the approach/yard side.

SoR: `cats/scripts/wire_hart_sheet_west_yard2.py` → `SIGNAL_DEFS`  
Plan CSV: `cats/data/signal_mast_plan.csv`  
Rewire: `python3 cats/scripts/wire_hart_sheet_west_yard2.py`
