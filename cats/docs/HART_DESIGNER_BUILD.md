# Build HART CTC panel in CATS Designer

## Goal (phase 1)

Magnet-board / dark CTC schematic of Neville Island west→east. **Gate 1 first:** Brick + OS Brick-Plane + Plane ([`GATE1_BRICK_PLANE.md`](GATE1_BRICK_PLANE.md)), then Gates 2–5 ([`GATE2_PLUS.md`](GATE2_PLUS.md)).

Layout Editor `hart_prod.xml` stays the MQTT hardware panel. Designer XML is a **second** definition that references the same JMRI user names.

After save: `python3 cats/scripts/jmri_to_cats_digicon.py --wire-only cats/panels/HART.xml`

## Prerequisites

- JMRI ≤ 5.16 with HART profile + `hart_prod.xml` loaded  
- CATS 3.2 fetched (`./tools/cats/fetch_cats_3.2.sh`)  
- Binding CSVs generated (`python3 jmri/scripts/export_hart_devices_for_cats.py`)

## Designer steps (Brick first)

1. Launch `tools/cats/release3.2/designer.csh` (or `.bat` on Windows).
2. File → Open `examples/ArmstrongMagnet.xml` to learn grid sections; File → New for HART (or Save As `cats/panels/HART.xml`).
3. Enable MQTT device prefixes in Designer connection tables if prompted (sensors `M2S*`, turnouts `M2T*` — see `jmri_devices.csv`).
4. Draw left→right:
   - West Yard (dark / no signals initially)
   - **Brick** (OS 1, OS 3) + approach `OS Main West` / `OS West Main Ext`
   - **Plane** (OS 5)
   - South Yard ladder (OS 15–106) — optional phase 1b
   - **East End** (OS 25–112, crossover 111)
   - **Princess** (OS 113–115) → OS McKees Rocks / OS McKeesport
5. For each OS block, set **Occupied Report** user name from `occupancy_bindings.csv` (e.g. OS 1 → `Block 4-2`).
6. For each set of points, bind **Command** to turnout user name (`Switch 1`, …) from `turnout_bindings.csv`.
7. Add station/section labels: Brick, Plane, East End, Princess, Neville Island.
8. Signals: leave as panel lamps / no physical JMRI mast until ADR confirms ownership; use `signal_mast_plan.csv` for placement intent.
9. Save as `cats/panels/HART.xml`.
10. Run `cats.csh`, open `HART.xml`, Test Layout: throw Brick switches; confirm LE panel / MQTT follow.

## Acceptance (Brick)

- [ ] Designer block `OS 1` occupancy follows live `Block 4-2`
- [ ] Designer block `OS 3` occupancy follows live sensor
- [ ] Throwing Switch 1/101 from CATS moves MQTT motors
- [ ] Layout Editor still shows alignment; no double-command from NextTrain

## Do not

- Import or overwrite `hart_prod.xml` with CATS XML  
- Run LE Signal Mast Logic on the same aspects CATS drives  
- Commit `tools/cats/release3.2/*.jar` (fetch script only)
