# Live status — HART Digicon

Updated: 2026-08-08 — Gate 1 primary + LE Gate 2–5 WIP board

## Repo / remote

- GitHub: https://github.com/lnevo/hart  
- Local workspace folder: `Panel` (same git root)  
- Agent branch pattern: `agent/<id>/<topic>` — see [`AGENTS_GIT.md`](AGENTS_GIT.md)  
- Cloud Agents: link `lnevo/hart` at [Cloud Agents dashboard](https://cursor.com/dashboard/cloud-agents)

## Now

| Panel | Role | Rebuild |
|-------|------|---------|
| `cats/panels/HART.xml` | **Primary** — Designer Gate 1 + CTC rules + MQTT | `python3 cats/scripts/wire_designer_ctc_rules.py --mqtt` |
| `cats/panels/HART_le.xml` | **WIP** — LE-derived Gate 1–5 schematic (all occupancy names) | `python3 cats/scripts/build_hart_digicon_from_le.py --mqtt` |

- Authoritative Designer draw: `cats/panels/HART_designer_raw.xml`  
- Armstrong shell: `tools/cats/…/ArmstrongMagnet.xml` **or** checked-in `cats/panels/reference_ArmstrongMagnet.xml` (Cloud-safe via `cats/scripts/cats_paths.py`)  
- Static check: `python3 cats/scripts/validate_cats_panel.py`  
- How-to: [`cats/docs/DESIGNER_GATE1_HOWTO.md`](../cats/docs/DESIGNER_GATE1_HOWTO.md)  
- Map: [`cats/docs/HART_DIGICON_MAP.md`](../cats/docs/HART_DIGICON_MAP.md)

### Gate coverage (static)

- **Gate 1 (Designer primary):** Brick → Block 100-102 → Plane → East Main Ext; West Yard 116/117 present; MQTT on all 14 named blocks. Live paint/route-role accept still needs Mac CATS.  
- **Gate 2–5 (LE WIP):** 79 track cells, 22 plants, 43 named blocks (full `occupancy_bindings.csv`); Block 100-102 on HORIZONTAL spine; OS 117b on EME↔Main East; South Yard / East End / Princess present. Needs Mac CATS load + occupancy path check before promoting over Designer primary.

## Manual launch (local Mac only)

```bash
# Primary Gate 1
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART.xml

# LE full-railroad WIP (optional)
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_le.xml
```

Do **not** use `CATS_LAUNCH_VIA=app`. Keep-alive LaunchAgent stays disabled.
