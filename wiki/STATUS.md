# Live status — HART Digicon

Updated: 2026-08-08 — Mac↔Cloud sync; LE board loads; CTC renderers iterating

## Repo / remote

- GitHub: https://github.com/lnevo/hart  
- Local workspace folder: `Panel` (same git root)  
- Agent branch pattern: `agent/<id>/<topic>` — see [`AGENTS_GIT.md`](AGENTS_GIT.md)  
- Cloud Agents: link `lnevo/hart` at [Cloud Agents dashboard](https://cursor.com/dashboard/cloud-agents)

## Collaboration (Mac host ↔ Cloud)

| Role | Owns | Do not |
|------|------|--------|
| **Cloud** | `HART_le` builder, PNG renderers (`render_ctc_panel.py`, `render_le_layout.py`, `render_cats_panel.py`), static validate, PR iteration | Assume CATS GUI paint; overwrite Designer primary without Mac accept |
| **Mac / local** | Live CATS load, screenshots, MQTT path accept, Gate 1 Designer accept | Re-invent cloud renderer geometry; fight over the same unpushed branch |

**Active tip:** `cursor/digicon-le-render-4da6` → [PR #4](https://github.com/lnevo/hart/pull/4) (renderers + ladder geometry). Base includes merged [PR #3](https://github.com/lnevo/hart/pull/3) (1-based X fix). Draft [PR #2](https://github.com/lnevo/hart/pull/2) is the LE WIP board SoR.

**Mac verified 2026-08-08:** After #3, `HART_le.xml` loads in CATS (Dispatcher 1400×520, no col≤0 NPE). Live shot: `cats/screenshots/cats_HART_le_live_*.png`. Local regenerates of cloud PNGs: `cats/screenshots/remote_renders/`.

**Next joint goals**

1. Keep Designer `HART.xml` as primary until Gate 1 live accept (LH100 continuing / Block 100-102 HORIZONTAL).  
2. Evolve LE Digicon toward the Class I CTC look in `render_ctc_panel.py` (real ladders, CP plates) — either improve `build_hart_digicon_from_le.py` cell roles or hand-Designer Gates 2–5.  
3. Keep Princess loop names as McKees Rocks / McKeesport in both Digicon XML and CTC PNGs.  
4. Wire turnout `points_command` + MQTT path checks on Mac before promoting LE over primary.

## Now

| Panel | Role | Rebuild |
|-------|------|---------|
| `cats/panels/HART.xml` | **Primary** — Designer Gate 1 + CTC rules + MQTT | `python3 cats/scripts/wire_designer_ctc_rules.py --mqtt` |
| `cats/panels/HART_le.xml` | **WIP** — LE-derived Gate 1–5 schematic (all occupancy names) | `python3 cats/scripts/build_hart_digicon_from_le.py --mqtt` |

- Authoritative Designer draw: `cats/panels/HART_designer_raw.xml`  
- Armstrong shell: `tools/cats/…/ArmstrongMagnet.xml` **or** checked-in `cats/panels/reference_ArmstrongMagnet.xml` (Cloud-safe via `cats/scripts/cats_paths.py`)  
- Static check: `python3 cats/scripts/validate_cats_panel.py`  
- Cloud review PNGs: `python3 cats/scripts/render_ctc_panel.py …` / `render_le_layout.py … --all-views` / `render_cats_panel.py`  
- How-to: [`cats/docs/DESIGNER_GATE1_HOWTO.md`](../cats/docs/DESIGNER_GATE1_HOWTO.md)  
- Map: [`cats/docs/HART_DIGICON_MAP.md`](../cats/docs/HART_DIGICON_MAP.md)

### Gate coverage (static)

- **Gate 1 (Designer primary):** Brick → Block 100-102 → Plane → East Main Ext; West Yard 116/117 present; MQTT on all 14 named blocks. Live paint/route-role accept still needs Mac CATS.  
- **Gate 2–5 (LE WIP):** 79 track cells, 22 plants, 43 named blocks (full `occupancy_bindings.csv`); Block 100-102 on HORIZONTAL spine; OS 117b on EME↔Main East; South Yard / East End / Princess present. **Mac load OK** after 1-based X; occupancy path check still pending before promoting over Designer primary.

## Manual launch (local Mac only)

```bash
# Primary Gate 1
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART.xml

# LE full-railroad WIP (optional)
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_le.xml
```

Do **not** use `CATS_LAUNCH_VIA=app`. Keep-alive LaunchAgent stays disabled.
