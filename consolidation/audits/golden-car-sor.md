# Golden car — photo & roster SoR (2026-08-31)

**ADR:** [`wiki/decisions/ADR-car-roster-single-sor.md`](../wiki/decisions/ADR-car-roster-single-sor.md)  
**Inventory SoR:** [`sor/cars/README.md`](../sor/cars/README.md)

---

## Golden car: **NW32800**

Assert against **generated** `OperationsCarRoster.xml` after SoR build (not hand-edited in Operations Pro).

| Check | NW32800 |
|-------|---------|
| `image_metadata.csv` | `IMG_9106.png` — marks, weights, OCR |
| `HART_MergedCarRoster.xml` | Full fleet canonical export |
| `OperationsCarRoster.xml` | JMRI sync target (all cars) |
| Pipeline asset | `card_pipeline/assets/NW32800.png` |

---

## Single SoR (owner decision 2026-08-31)

| Layer | File | Role |
|-------|------|------|
| **Editable** | `image_metadata.csv` | All inventory fields + OCR + photos |
| **Canonical XML** | `HART_MergedCarRoster.xml` | Generated full fleet |
| **JMRI export** | `OperationsCarRoster.xml` | Generated — **all cars** sync to Operations Pro |

**Operations Pro is not the editor.** Generated exports stay in **hart-ops** until cutover; do not push to Pi or overwrite Desktop originals during consolidation (D12).

**STS** reads Merged + metadata but imports **freight STS inventory only** — excludes passenger/caboose/MOW types (existing `PASSENGER_TYPES` filter in `generate_hart_seed.py`).

---

## Photo tiers (unchanged)

| Tier | Path |
|------|------|
| Manifest | `data/image_metadata.csv` |
| Crop | `CarImagesCardFill/` |
| Final | `CarImagesFinal/` |

Orphans `IMG_9123`, `IMG_9180` — optional metadata hygiene.

---

## Not STS fleet (still in SoR + Operations Pro)

- 11 locomotive/streetcar rows → `OperationsEngineRoster.xml` / engine path
- 13 promo/not-on-roster freight rows in metadata notes
- Passenger, caboose, MOW on ops roster — sync to Operations Pro, **exclude from STS seed**

---

## Migration note

Invert `build_merged_car_roster.py`: build **from** metadata **to** Merged, then export Operations. See ADR.
