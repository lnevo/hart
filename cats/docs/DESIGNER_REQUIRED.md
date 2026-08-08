# Designer vs automated Digicon

Hand-authored incomplete `TRACKPLAN` XML crashes CATS (`MyBlock` null, SecEdge mismatches, VitalLogic NPE).

## Authoritative path (ADR-004)

**Redraw Neville in CATS Designer** plant-by-plant. Layout Editor `hart_prod.xml` stays the MQTT hardware panel.

1. Gate 1: [`GATE1_BRICK_PLANE.md`](GATE1_BRICK_PLANE.md) — Brick → Block 100-102 → Plane  
2. Gates 2–5: [`GATE2_PLUS.md`](GATE2_PLUS.md)  
3. After Designer save: wire I/O without touching geometry:

```bash
python3 cats/scripts/jmri_to_cats_digicon.py --wire-only cats/panels/HART.xml
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh
```

Launch Designer: `./cats/scripts/launch_designer.sh`

## Interim generator (not Neville geography)

```bash
python3 cats/scripts/jmri_to_cats_digicon.py --only gate1
```

Abuts Armstrong **fragments** so Gate 1 has a long HORIZONTAL Block 100-102 between Brick and Plane. Use for MQTT smoke tests only. **Designer Gate 1 replaces it** for a representative panel.

Armstrong/Chubb full-chassis renames (`--only armstrong|chubb`) are demos/alts — not the HART primary.

## When to edit XML by hand

Never invent `SEC_EDGE` / `SWITCHPOINTS`. Only safe automated edits: occupancy IOSPEC, MQTT `JMRINAME`, train store (`--wire-only`).

## Smoke / reference

| File | Role |
|------|------|
| `HART.xml` | **Primary** — Gate 1 (interim or Designer) + MQTT |
| `HART_magnet.xml` | Gate 1 magnet (no occ) |
| `HART_armstrong_magnet.xml` | Full Armstrong rename demo |
| `HART_chubb_magnet.xml` | Chubb 3-row CTC look only |
| `HART_smoke_Armstrong.xml` | Proves CATS install paints track |