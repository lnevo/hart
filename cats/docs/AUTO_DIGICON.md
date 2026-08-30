# Automated Digicon helpers

Topology truth is **Designer** ([`GATE1_BRICK_PLANE.md`](GATE1_BRICK_PLANE.md), ADR-004). The generator builds interim fragments and wires MQTT.

## Commands

```bash
# Primary Gate 1 from Designer draw
python3 cats/scripts/wire_designer_ctc_rules.py --mqtt

# LE Gate 1–5 WIP (does not overwrite HART.xml)
python3 cats/scripts/build_hart_digicon_from_le.py --mqtt

# Interim Gate 1 (contiguous Armstrong Brick→Plane window)
python3 cats/scripts/jmri_to_cats_digicon.py --only gate1

# After Designer save — wire only (TRACKPLAN unchanged)
python3 cats/scripts/jmri_to_cats_digicon.py --wire-only cats/panels/HART.xml

python3 cats/scripts/validate_cats_panel.py
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART.xml
```

| File | Purpose |
|------|---------|
| [`../panels/HART.xml`](../panels/HART.xml) | **Primary** Designer Gate 1 + MQTT |
| [`../panels/HART_magnet.xml`](../panels/HART_magnet.xml) | Gate 1 magnet |
| [`../panels/HART_le.xml`](../panels/HART_le.xml) | LE WIP full railroad + MQTT |
| [`../panels/HART_le_magnet.xml`](../panels/HART_le_magnet.xml) | LE WIP magnet |
| [`../panels/HART_armstrong_magnet.xml`](../panels/HART_armstrong_magnet.xml) | Full Armstrong demo |
| [`../panels/HART_chubb_magnet.xml`](../panels/HART_chubb_magnet.xml) | Chubb CTC look only |

Armstrong shell resolves via `cats_paths.py` (full CATS tree or
`reference_ArmstrongMagnet.xml`).

## Design intent

**Class 1 Digicon CTC** for HART. JMRI supplies connectivity and names. Digicon must keep **route roles** (straight vs diverge) honest — not foreign chassis stickers.

## Don’t

- Invent `SEC_EDGE` by hand  
- Treat Armstrong/Chubb rename as the finished Neville panel  
- Use `keep_cats` / PanelPro.app handoff as default launch