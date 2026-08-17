# Live status — HART Digicon

Updated: 2026-08-11 — **Ops Digicon Masters** at `cats/panels/HART_Master*.xml` (CTC / ABS / ABS-RO). System overview: [`cats/docs/HART_DIGICON_SYSTEM.md`](../cats/docs/HART_DIGICON_SYSTEM.md).

## Repo / remote

- GitHub: https://github.com/lnevo/hart  
- Local workspace folder: `Panel` (same git root)  
- Agent branch pattern: `agent/<id>/<topic>` — see [`AGENTS_GIT.md`](AGENTS_GIT.md)  
- Cloud Agents: link `lnevo/hart` at [Cloud Agents dashboard](https://cursor.com/dashboard/cloud-agents)

## Product decision (stop the abstract chase)

| Deliverable | Role |
|-------------|------|
| **`cats/panels/HART_Master.xml`** | **Ops Digicon CTC** — Neville Island Master (**source of record**; checkpoint this family) |
| **`cats/panels/HART_Master_ABS.xml`** | **Ops Digicon ABS** — open house |
| **`cats/panels/HART_Master_ABS_hold.xml`** | **ABS-RO** — signals HOLD_ONLY; turnouts on |
| `cats/panels/sheets/HART_sheet_West_Yard2.xml` | Legacy sheet WIP — **do not checkpoint**; Masters are the live copy |
| `cats/panels/HART_ctc.xml` | Earlier CTC schematic experiment |
| `render_ctc_panel.py` PNG | **Review art only** — cannot open in CATS |

See [`cats/docs/HART_DIGICON_SYSTEM.md`](../cats/docs/HART_DIGICON_SYSTEM.md) and [`cats/docs/DIGICON_VS_CTC_PNG.md`](../cats/docs/DIGICON_VS_CTC_PNG.md).

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
