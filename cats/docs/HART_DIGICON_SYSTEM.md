# HART Digicon (CATS) — System Overview

**Publication:** DS-DIGICON · Rev A · Eff 2026-08-11  
**Railroad:** HART Railroad · Pittsburgh & Chartiers Valley Division · Neville Island Operations  
**Scope:** Digicon CTC / ABS panels, JMRI MQTT bridge, LCOS signal heads

This is the end-to-end picture of what we built: Digicon panels on Mac / Pi / Windows, how they talk to JMRI and MQTT, and how field signal heads are addressed for LCOS hardware.

Related detail docs (do not duplicate here):

| Topic | Doc |
|-------|-----|
| Signal facing / mast bind | [`SIGNAL_FACING.md`](SIGNAL_FACING.md) |
| Turnout SoR / retain paint | [`TURNOUT_STATE_SOURCES.md`](TURNOUT_STATE_SOURCES.md) |
| Sensor status-only MQTT | [`MQTT_SENSOR_STATUS_ONLY.md`](MQTT_SENSOR_STATUS_ONLY.md) |
| Pi install notes | [`../scripts/pi/README_CATS.txt`](../scripts/pi/README_CATS.txt) |
| Neville trackplan (reference) | [`station_maps/Neville_Island_Trackplan_Clean.png`](station_maps/Neville_Island_Trackplan_Clean.png) |

---

## 1. What we built

Two Digicon “Master” launchers for Neville Island ops, plus JMRI tables / scripts so Digicon, MQTT, SML, and LCOS stay in sync.

| Launcher | Panel file | Role |
|----------|------------|------|
| **CATS CTC** | `cats/panels/HART_Master_CTC_hold.xml` | **Live CTC** — Digicon codes routes / throws; signals `HOLD_ONLY`; **JMRI SML** owns aspects |
| **CATS ABS** | `cats/panels/HART_Master_ABS_hold.xml` | **Live ABS** — `HOLD_ONLY`; SECSIGNALs bound to JMRI masts so Digicon **paints SML**. Geometry source `HART_Master_ABS.xml` stays unbound. |

Geometry sources (no desktop icons): `HART_Master.xml` (CTC rebuild) and `HART_Master_ABS.xml` (ABS rebuild), wired from Designer `HART_Master4.xml` (`python3 cats/scripts/wire_hart_master4.py --live`). Checkpoint **Masters only** (`cats/panels/checkpoints/`). Sheet WIP (`cats/panels/sheets/`, including West Yard2) is legacy — do not snapshot it.

Each Master carries a publication title row (Y=1):

- **HART RAILROAD** · **NEVILLE ISLAND OPERATIONS** · **P&CV DIVISION**
- Mode tag (`CTC DIGICON` / `ABS DIGICON`)
- Pub id (`DS-CTC` / `DS-ABS`) · Rev · Effective date

Rebuild hold panels after a Designer save:

```bash
python3 cats/scripts/wire_hart_master4.py --live   # CTC + ABS geometry + HOLD copies
```

---

## 2. How the pieces interconnect

```text
┌─────────────────┐     route / Hold only              ┌──────────────────┐
│  CATS CTC       │ ── setHeld + ROUTECOMMAND ────────►│  JMRI SignalMast │
│  HOLD_ONLY      │   bind by mast userName            │  AAR-1946 SHSM   │
└────────┬────────┘                                    └────────┬─────────┘
         │ turnout throws                                      │ SML aspects
         │ occupancy paints from JMRI sensors                  │ Appearance
         ▼                                                     ▼
┌─────────────────┐                                  ┌──────────────────┐
│ JMRI Turnouts / │◄── MQTT retain paint (boot) ────│ MQTT broker       │
│ Sensors / Blocks│                                  │ minipc / Pi       │
└────────┬────────┘                                  └────────┬─────────┘
         │                                                    │
         │  track/turnout/#  track/sensor/#                   │
         │  track/signalhead/IH###  (virtual heads)           │
         ▼                                                    ▼
┌─────────────────┐                                  ┌──────────────────┐
│ LCOS / field    │◄─────────────────────────────────│ LED searchlights │
│ radio nodes     │   packed IH address → DNOU8 port │ on the layout    │
└─────────────────┘                                  └──────────────────┘
```

**Boot sequence (profile Start Up, after `tables.xml`):**

1. `jmri/layouts/hart/scripts/apply_maintain_mqtt.py` — read MQTT **retain** for sensors/turnouts; JMRI-only paint (`setOwnState` / KnownState); never publishes commands. Then Digicon `IOSpec.refreshScreen()`.
2. `jmri/layouts/hart/scripts/sync_yard_ladder_buttons.py` — yard-ladder lamp buttons ↔ internal turnouts.
3. `jmri/scripts/mqtt_signalhead_publisher.py` — paint Virtual heads from `track/signalhead/#` retain, then **listen** and **publish** Appearance changes JMRI → MQTT for LCOS.

(`unhold_signal_masts.py` is retired: masts boot Unheld, so SML runs ABS by default; **Held is CATS CTC's channel** — it holds homes at panel load and unholds when the dispatcher lines a route. A blanket unhold watchdog fought that.)

SML dests are **native**: Layout Editor Discover generates them (`cats/scripts/run_sml_discover.sh` one-shot) and they are stored in `tables.xml` with `useLayoutEditor=yes`, so JMRI re-paths them on every load. Re-running Discover is safe. `apply_sml_cats_pairs.py` is retired — its `PAIRS` list survives only as the regression oracle for `cats/scripts/validate_le_signalling.py` (static boundary/routing checks + mini-discovery, run it before deploying panel edits). Facing is in `cats/data/le_signal_boundaries.csv` (`python3 cats/scripts/apply_le_sml_facing.py`). Advanced routing is `blockrouting="yes"` on `<layoutblocks>`. Two-head masts use the custom `hart-aar` signal system (`SL-2-digicon`) so aspects chain as 3-aspect ABS + diverging; see `cats/docs/SIGNAL_FACING.md`.

**PanelPro vs CATS (same profile, sequential — never simultaneous):**

- **PanelPro** — edit/store JMRI tables, connections, Start Up. Then quit. Never Store tables while a CATS layout is open (Rodney Black, cats-users #2534).
- **CATS** — separate JMRI app (`cats.apps.Crandic`). Profile Start Up loads `preference:tables.xml` first (HART equivalent of Designer “Include”), then the Digicon XML. Refers to JMRI beans by user name; does not redefine them. LogixNG hides **USS CTC** on every host (IQC:AUTO:0002) and, under CATS only, **HART Railroad** (IQC:AUTO:0004 / `hide_cats_desk_windows.py`) so the Digicon stays up.
- Do **not** run both at once (MQTT client-id + profile lock). Only **one** Digicon should be signal authority (**CATS CTC** or **CATS ABS**).

---

## 3. Digicon geometry and ops features

### Geography (Neville Island)

Digicon schematic covers West Yard / Brick / Plane / Barn, South Yard ladder, East End, Princess, McKees Rocks / McKeesport leads — matching the Neville Island station maps and CSX/POV-era trackplan reference.

### Discipline

| Panel | Block `DISCIPLINE` | Dispatcher signal clicks |
|-------|--------------------|---------------------------|
| Master CTC | `CTC` | Left-click entrance = request route + Unhold; **SML** sets the aspect |
| Master ABS | `ABS` | No CTC left-click routing; SML follows occupancy / points |

CTC homes start **Held** (CATS holds them at panel load). Left-click codes the route; Digicon drops Hold and SML shows Approach/Clear. Without CATS, masts simply boot Unheld so SML runs ABS — no script needed. **Fleeting** is only for keeping a live route clear for following trains — it is disabled until a route is already ACTIVE.

### Yard ladder buttons

Lamp buttons beside S-1…S-5 (left = west ladder + 116; right = east ladder + 112 / 111 for S-1):

- Digicon and Layout Editor share the same triggers: internal turnouts `IT:HART:YL:L1…R5`
- JMRI routes `IO:AUTO:0201–0210` fire on throw and line M2T peels
- Digicon icons: `cats/resources/buttons/lamp_{left,right}_{idle,active}.png` (paths rewritten per OS)
- Layout Editor / JMRI web: USS lamp `turnouticon`s on the same ITs inside **`tables.xml`** Layout Editor (script: `jmri/layouts/hart/scripts/add_yard_ladder_le_icons.py` → `tables/new_tables.xml`, synced to `jmri/layouts/hart/output/tables.xml`). Lamps align with the **Track 1…5** text labels (above each rail), not the BlockContentsIcon “Yard Track N” rows. Click THROWN = line that track; CLOSED/idle = red. Prefer this panel over `hart_prod.xml` (CP labels on hart_prod are oversized).

### Turnout SoR (summary)

Live Digicon follows field feedback for most plants; Digicon `SELECTEDREPORT` and `ROUTECOMMAND` share polarity. Tip SoR for 112 / 114 / 115 is documented in [`TURNOUT_STATE_SOURCES.md`](TURNOUT_STATE_SOURCES.md). Agents must not throw field points to “fix” paint.

### Load safety

Installed Digicon jar includes the `cats-pts-nullguard` overlay so early `SELECTEDREPORT` cannot kill `RREventManager` (occupancy freeze).

---

## 4. Signals — nature and LCOS heads

### One family

| Family | JMRI object | Digicon `PHYSIGNAL` | MQTT | Field |
|--------|-------------|---------------------|------|-------|
| **Virtual head + SHSM** (all Digicon lamps) | Virtual `IH###` + `IF$shsm:hart-aar:SL-2-digicon` two-head / `IF$shsm:AAR-1946:SL-1-low` dwarf | stock `single` / `double` (native R-codes remapped to AAR names) | `track/signalhead/IH###` | LCOS searchlight ports |

Digicon binds by **mast userName** (exact string match). Panel lamps (`LAMP1|2|3`) are Digicon cosmetics; field head count comes from JMRI / LCOS wiring.

### Aspect language

- Digicon internals speak rule codes (`R281` Clear, `R285` Approach, `R292` Stop, `RES_*` Restricting, …).
- **AAR-1946** SHSM aspects are Clear / Approach / Stop (2-head) or Slow Clear / Restricting / Stop (dwarf). `aar_aspect_bridge.py` remaps Digicon R-codes → those names.
- Virtual heads get GREEN / YELLOW / RED appearances; `mqtt_signalhead_publisher.py` publishes those names on `track/signalhead/IH###`.

### Authority

| Mode | Who drives Clear/Approach/Stop |
|------|--------------------------------|
| **CATS CTC** | Occupancy + points via MQTT → JMRI; **SML** sets aspects; Digicon paints (`HOLD_ONLY`). CTC also Held/Unhold. |
| **CATS ABS** | Occupancy + points via MQTT → JMRI; **SML** sets aspects; Digicon paints (`HOLD_ONLY`). SECSIGNALs bind real JMRI mast names. CATS ABS vital logic still Hold/Unhold. |

### LCOS packing (signal heads)

LCOS addresses searchlights as **packed IDs** on the radio node:

```text
packed = displayNode * 100 + UID
UID    = 32 + signal_index     # Signal 0..15 → UID 32..47 (mqtt_serial.h)
JMRI   = IH<packed>            # e.g. node 4, signal 0 → IH432
MQTT   = track/signalhead/IH<packed>
Payload = appearance name      # Red / Yellow / Green / Dark / …
```

| Area | MQTT node (radio) | Parent board | Packed heads | Example ports |
|------|-------------------|--------------|--------------|---------------|
| Plane + W-1 / W-2 + Brick east | **4** | C4 | `IH432`–`IH439` | C4-OU2-1 … OU2-6, C4-OU3-1/2 |
| Barn / W-117 | **13** (`013`) | C1 | `IH1332`–`IH1338` | C1-OU2-1 … OU3-1 |
| East End | **12** (`012`) | C7 | `IH1232`–`IH1241` | C7-OU2-1 … OU3-4 |
| Princess | **1** | D1 | `IH132`–`IH143` | D1-OU2-1 … OU3-4 |

Head roles on multi-head masts: **T** top, **M** middle, **B** bottom, **S** single.

Appearances for SHSM:

- 1 head → `cats-virtual-dwarf` (SL-1-low LE icons)
- 2 heads → `cats-virtual-2`
- 3 heads → `cats-virtual-3`

XML: `cats/resources/signals/cats-masts/`.

### Mast index (Digicon name → JMRI)

Full table: [`cats/data/signal_mast_plan.csv`](../data/signal_mast_plan.csv)  
Port / topic / LCOS inventory: [`cats/data/signal_wiring.csv`](../data/signal_wiring.csv)  
Head plan: [`cats/data/signal_head_plan.csv`](../data/signal_head_plan.csv)

Examples:

| Digicon mast userName | Heads | System name (abbrev) | Binding |
|-----------------------|-------|----------------------|---------|
| 100L | 2 | `…(IH438)(IH439)` | LCOS C4-OU3 |
| 102LB | 2 | `…cats-virtual-2(IH432)(IH433)` | LCOS C4 |
| 102LA | 2 | `…(IH434)(IH435)` | LCOS C4 |
| 101RA / 2 | 1 | `IH436` / `IH437` | LCOS C4 |
| 117RA | 2 | `IH1332`/`IH1333` | LCOS C1 |
| 112L | 2 | `IH1237`/`IH1238` | LCOS C7 |
| 115LB | 2 | `…cats-virtual-2(IH132)(IH133)` | LCOS D1 |
| 114R | 1 | `IH134` | LCOS D1 (was North middle) |
| 113RA / 113a | 2 | `IH135`–`IH138` | LCOS D1 |
| 114LB | 2 | `IH139`/`IH140` | LCOS D1 |
| 115R | 1 | `IH141` | LCOS D1 (was South bottom) |
| 115LA / K-2 | 1 | `IH142` / `IH143` | LCOS D1 dwarfs |

### JMRI ↔ MQTT for Virtual heads

`jmri/scripts/mqtt_signalhead_publisher.py` (Start Up; regenerated by `build_hart_signal_heads.py`):

1. **Boot:** `mosquitto_sub` retain on `track/signalhead/#` → `setAppearance` on listed `IH*` (no publish — does not stomp field SoR).
2. **Run:** PropertyChange on Appearance → `mqtt.publish("track/signalhead/"+sysName, appearanceName)` so Digicon-driven aspects reach LCOS.

**LCOS Nano bridge dual path** (`LCOS_ESP32_MQTT_Client`, see `docs/signal_dual_path.md`):

- **Send (Digicon → field):** subscribe `track/signalhead/IH###` → `EVENT_SIGNAL_CMD` (Red→Stop, Yellow→Approach, Green→Clear).
- **Receive (field → JMRI masts):** LCOS `EVENT_SIGNAL` → retained `track/signalmast/<packed>` (`Stop; Lit; Unheld`, …) so traditional MQTT Signal Masts still get aspect reports. Status is **not** published on `signalhead` (avoids looping Digicon).

100L is the same packed-head path (`IH438`/`IH439` on C4-OU3). JMRI no longer publishes `track/signalmast/432`.

Rebuild heads + tables + publisher:

```bash
python3 cats/scripts/build_hart_signal_heads.py
```

LE `signalmasticon`s use stock AAR-1946 schematic GIFs (no custom cats-masts imagelinks required). Digicon binds by userName either way.

---

## 5. Launch (all hosts)

| Host | How |
|------|-----|
| **Mac** | `/Applications/CATS CTC.app` / `CATS ABS.app` or `./cats/scripts/launch_hart_master.sh` |
| **Pi** | Desktop **CATS CTC** / **CATS ABS** |
| **Windows** | Desktop **CATS CTC** / **CATS ABS** |

Default panel for `launch_cats.sh` is `cats/panels/HART_Master_CTC_hold.xml`.

Profile tables (routes, YL internals, signal heads/masts) load from the host’s `preference:tables.xml` / Pi `JMRI_UserFiles/tables.xml` (repo mirror `jmri/layouts/hart/output/tables.xml`). Yard ladders need `IO:AUTO:0201–0210` and `IT:HART:YL:*` in that file.

### JMRI package (SSH deploy to hosts)

Same package carries Digicon Masters, `tables.xml`, yard-ladder button icons, and the JMRI **web home** override + Start Up scripts:

| Piece | Repo SoR | Installs to |
|-------|----------|-------------|
| CTC / ABS hold panels | `cats/panels/HART_Master_*hold.xml` | host `hart/cats/panels/` |
| Tables | `jmri/layouts/hart/output/tables.xml` | `preference:tables.xml` / `JMRI_UserFiles/tables.xml` |
| Ladder icons | `cats/resources/buttons/lamp_*.png` | `hart/cats/resources/buttons/` |
| Web home + STS | `cats/resources/jmri-web/servlet/home/Home.html` | profile / UserFiles `web/servlet/home/` (STS link in Home.html → `http://10.0.0.53:8980/sts/`) |
| JMRI Start Up scripts | `sync_yard_ladder_buttons.py`, `mqtt_signalhead_publisher.py` | All hosts `preference:jython/` (Pi `JMRI_UserFiles/jython/`; Mac/Windows `<profile>.jmri/jython/` because user-files=`profile:`). `hide_cats_desk_windows.py` is LogixNG, same folder. |

Deploy via SSH (agent does this — no manual batch/Dropbox step):

```bash
./cats/scripts/sync_hart_package.sh --pi    # Pi
./cats/scripts/sync_hart_package.sh --win   # Windows (SSH :2222)
./cats/scripts/sync_hart_package.sh --all   # Mac web + Pi + Windows
```

---

## 6. Source-of-truth scripts

| Script | Purpose |
|--------|---------|
| `cats/scripts/wire_hart_sheet_west_yard2.py` | Geometry / plants / signal defs → sheets + Masters |
| `cats/scripts/build_hart_master_ctc_hold.py` | CTC geometry → CATS CTC (`HOLD_ONLY` + AAR bridge) + header |
| `cats/scripts/build_hart_master_abs_hold.py` | ABS geometry → CATS ABS (`HOLD_ONLY` + AAR bridge) + header |
| `cats/scripts/aar_aspect_bridge.py` | Digicon R-codes ↔ AAR Clear/Approach/Stop |
| `cats/scripts/apply_le_sml_facing.py` | AAR SHSM + Layout Editor `signalAMast` / block-boundary facing |
| `jmri/layouts/hart/scripts/discover_sml.py` | PanelPro one-shot SML Discover (background; do not leave on Start Up) |
| `cats/scripts/run_sml_discover.sh` | Launch PanelPro, Discover, store `tables.xml`, quit |
| `cats/scripts/polish_hart_master_header.py` | Publication title row |
| `cats/scripts/build_hart_signal_heads.py` | Virtual heads, SHSM masts, wiring CSV, publisher, LCOS inventory ports |
| `cats/scripts/add_yard_ladder_buttons.py` | Ladder lamp buttons on Masters |
| `cats/scripts/sync_hart_package.sh` | SSH deploy package to Pi / Windows |
| `cats/scripts/install_jmri_web_override.sh` | STS link into JMRI `web/` (Mac/Pi) |
| `cats/scripts/windows/install_hart_tables.ps1` | Windows local install helper (tables + jars + web); prefer `sync_hart_package.sh --win` |
| `jmri/layouts/hart/scripts/apply_maintain_mqtt.py` | Boot retain paint (sensors/turnouts) |
| `jmri/scripts/mqtt_signalhead_publisher.py` | Retain paint + publish IH appearances |

---

## 7. Operating rules (short)

1. **CATS CTC** and **CATS ABS** both `HOLD_ONLY`: SML sets aspects; Digicon paints JMRI appearances. CTC also Held/Unhold on coded routes. ABS Hold/Unhold follows Digicon ABS vital logic. Layout Editor is always SML.
2. Never publish turnout “fix” commands at launch; retain paint is read-only.
3. Digicon Refresh Screen = safe (JMRI → Digicon). Refresh Layout pushes Digicon → JMRI — avoid for boot paint fixes.
4. All Digicon lamps are packed `IH*` SHSM — two-head homes on custom **hart-aar** (`SL-2-digicon`), dwarfs on stock **AAR-1946** (`SL-1-low`). 100L is `IH438`/`IH439`.
5. After Master / ABS geometry edits, rebuild both hold copies (`build_hart_master_ctc_hold.py`, `build_hart_master_abs_hold.py`) so `HOLD_ONLY` and mast bindings stay in sync. ABS live panel is `HART_Master_ABS_hold.xml`.
6. Without CATS: Unhold + SML = ABS. Do not launch CTC geometry-source `HART_Master.xml` against live SML.

---

*Office of the Superintendent · Neville Island Operations · DS-DIGICON Rev A*
