# Gates 2–5 — expand after Gate 1 accept

Do not promote these over Designer primary until [`GATE1_BRICK_PLANE.md`](GATE1_BRICK_PLANE.md) acceptance is checked on Mac.

**Cloud / script path:** LE schematic already includes Gate 2–5 names — rebuild with
`python3 cats/scripts/build_hart_digicon_from_le.py --mqtt` → `cats/panels/HART_le.xml`.
Still needs live CATS paint/path accept before replacing `HART.xml`.

**Designer path:** draw each gate in **CATS Designer**, merge into
`HART_designer_raw.xml`, extend anchors in `wire_designer_ctc_rules.py`, then:

```bash
python3 cats/scripts/wire_designer_ctc_rules.py --mqtt
# or: python3 cats/scripts/jmri_to_cats_digicon.py --wire-only cats/panels/HART.xml
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART.xml
```

## Gate 2 — West Yard + East Main Ext spine

| Digicon role | Block | Notes |
|--------------|-------|-------|
| Yard leads / ladder | OS 116, OS 118, OS 119 | West of / under Brick |
| Xover | OS 117 (top), OS 117b (bottom C/D) | Main East ↔ East Main Ext uses **117b** |
| Spine | East Main Ext → OS 117b → Main East | Contiguous main |

Accept: occupy East Main Ext and OS 117b; Digicon red matches JMRI path (not 117 top).

## Gate 3 — South Yard ladder

| Digicon role | Block |
|--------------|-------|
| West ladder | OS 103–106 |
| Body (optional) | S-1–5 |

Accept: diverge from Plane / main into 103 chain without lighting unrelated spine cells.

## Gate 4 — East End + East Lead

| Digicon role | Block |
|--------------|-------|
| East ladder / plant | OS 107–112 |
| Lead | East Lead |

Accept: Main East → OS 112 → East Lead contiguous on Digicon + JMRI.

## Gate 5 — Princess loops

| Digicon role | Block |
|--------------|-------|
| Plant | OS 113a/b, OS 114, OS 115 |
| Loops | McKees Rocks, McKeesport |

Accept: reverse-loop pair (not a wye); East Lead ↔ 113b adjacency.

## Checklist template (each gate)

- [ ] Designer cells complete (no hand `SEC_EDGE`)
- [ ] Block names = JMRI userNames
- [ ] `--wire-only` applied
- [ ] `validate_cats_panel.py` PASS
- [ ] Live MQTT occupancy on expected Digicon cells only
- [ ] Update [`HART_DIGICON_MAP.md`](HART_DIGICON_MAP.md) for new plants