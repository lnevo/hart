# Gate 1 — Brick → Brick-Plane → Plane

JMRI adjacency + Digicon cell-role checklist. SoR: `jmri/layouts/hart/output/hart_prod.xml`.

## JMRI truth (Switch 100 = LH)

| Leg | Connect | Block | Mainline |
|-----|---------|-------|----------|
| A (throat) | west | Main West | yes |
| B (diverge) | yard | OS 100 / toward OS 101 | no |
| C (continuing) | east | Brick-Plane | yes |

Then: Brick-Plane → TO102 A (Plane) → East Main Ext (B).

```
Main West ═══[ OS 100 LH ]═══ Brick-Plane ═══[ OS 102 ]═══ East Main Ext
                  ╲
                   OS 101 (West Yard)
```

**Critical:** Digicon must put Brick-Plane on the **continuing HORIZONTAL**, not on a diverge slash into the next plant throat.

## Digicon cell roles

| Order (W→E) | Digicon role | Block name | Occupancy sensor | Notes |
|-------------|--------------|------------|------------------|-------|
| 1 | HORIZONTAL | Main West | Block 2-1 (`M2S` from hart) | Approach to Brick |
| 2 | SWITCHPOINTS (LH) | OS 100 | Block 4-2 | Continuing = east straight |
| 3 | yard diverge | OS 101 | Block 4-1 | Off the main spine |
| 4 | HORIZONTAL (long) | Brick-Plane | Block 4-6 | Mid-spine; not plant approach |
| 5 | SWITCHPOINTS | OS 102 | Block 4-5 | Plane diverge |
| 6 | HORIZONTAL | East Main Ext | (hart layoutblock) | East of Plane |

## Designer steps (authoritative geometry)

**Beginner walkthrough (start here):** [`DESIGNER_GATE1_HOWTO.md`](DESIGNER_GATE1_HOWTO.md)

1. `./cats/scripts/launch_designer.sh`
2. File → New (do not keep full Armstrong TRACKPLAN).
3. Draw Gate 1 only per table above; complete every Digicon cell in Designer (no hand-built `SEC_EDGE`).
4. Bind occupancy / turnouts from [`BRICK_BINDINGS.md`](BRICK_BINDINGS.md) + `cats/data/occupancy_bindings.csv`.
5. Save as `cats/panels/HART.xml`.
6. Wire MQTT if needed: `python3 cats/scripts/jmri_to_cats_digicon.py --wire-only cats/panels/HART.xml`
7. `CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh`

## Acceptance

- [ ] Load paints Digicon (no ClassCast / blank board)
- [ ] `M2S405` ACTIVE → red on **HORIZONTAL** Brick-Plane only
- [ ] `M2S401` ACTIVE → red on OS 100 plant
- [ ] Visually: LH100 continuing L→R into 100–102; yard is the other route
- [ ] 100–102 does **not** read as diverge into Plane throat

## Agent interim (`build_gate1`)

Until Designer save exists, generator `--only gate1` clones the **contiguous** Armstrong Brick→Plane window (`X3–20`) and maps Intermediate1 → Brick-Plane (HORIZONTAL between plants). Do **not** abut separate bands (ClassCast VitalLogic). Interim is still not Neville LH100 geography — **Designer Gate 1 replaces it**.