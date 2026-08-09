# Live status — HART Digicon

Updated: 2026-08-09 — **West Yard sheet** `cats/panels/sheets/HART_sheet_West_Yard2.xml`: East Lead widened (+2), 26 NX panel lamps (restored CP approaches + SY/EE ladder singles), verify=0, CATS loads. Rebuild: `python3 cats/scripts/wire_hart_sheet_west_yard2.py`

## Repo / remote

- GitHub: https://github.com/lnevo/hart  
- Local workspace folder: `Panel` (same git root)  
- Agent branch pattern: `agent/<id>/<topic>` — see [`AGENTS_GIT.md`](AGENTS_GIT.md)  
- Cloud Agents: link `lnevo/hart` at [Cloud Agents dashboard](https://cursor.com/dashboard/cloud-agents)

## Product decision (stop the abstract chase)

| Deliverable | Role |
|-------------|------|
| **`cats/panels/HART_ctc.xml`** | **Operational Digicon** — CTC interlocking schematic (loadable) |
| `cats/panels/HART_le.xml` | Earlier LE-packed experiment (superseded for ops) |
| `cats/panels/HART.xml` | Designer Gate 1 experiment only |
| `render_ctc_panel.py` PNG | **Review art only** — same topology intent as `HART_ctc`, but **cannot** open in CATS |

See [`cats/docs/DIGICON_VS_CTC_PNG.md`](../cats/docs/DIGICON_VS_CTC_PNG.md).

## Collaboration (Mac ↔ Cloud)

| Role | Owns |
|------|------|
| **Mac / local** | Builder cell-role fixes, live CATS load, occupancy path accept, screenshots |
| **Cloud** | Help on builder/verify when asked; do not overwrite Mac ops branch with PNG-only commits |

Active tip for ops work: this working tree / branch with `build_hart_digicon_from_le.py` Gate‑1 spine fix.

## Now

| Panel | Role | Rebuild |
|-------|------|---------|
| `cats/panels/HART_ctc.xml` | **Ops Digicon** — CTC interlockings | `python3 cats/scripts/build_hart_digicon_ctc.py --mqtt` |
| `cats/panels/HART_le.xml` | LE-pack experiment | `python3 cats/scripts/build_hart_digicon_from_le.py --mqtt` |
| `cats/panels/HART.xml` | Designer Gate 1 | `python3 cats/scripts/wire_designer_ctc_rules.py --mqtt` |

### Gate 1 spine (ops board — required)

```
Main West ═══[ OS 100 ]═══ Block 100-102 (HORIZONTAL) ═══[ OS 102 ]═══ East Main Ext
                  ╲
                   OS 101 (yard)
```

- OS100 plant: continuing **RIGHT** into 100-102; diverge **BOTTOM** to OS101  
- Contiguous West Yard / South Yard / East End ladders (approach+plant pairs)

### Still open

- [ ] Live MQTT: `M2S405` → red only on Block 100-102; `M2S401` → OS 100 only  
- [ ] Wire turnout `ROUTECOMMAND` / `SELECTEDREPORT` from `turnout_bindings.csv`  
- [ ] Princess / East End visual polish after path-accept  
- [ ] Designer redraw or retire as dual-primary

## Manual launch (local Mac only)

```bash
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_le.xml
python3 cats/scripts/validate_cats_panel.py cats/panels/HART_le.xml
# optional schematic review PNG (not a substitute for CATS):
python3 cats/scripts/render_cats_panel.py cats/panels/HART_le.xml /tmp/le.png
```

Do **not** use `CATS_LAUNCH_VIA=app`. Keep-alive LaunchAgent stays disabled.
