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

Three Digicon “Master” panels for Neville Island ops, plus JMRI tables / scripts so Digicon, MQTT, and LCOS stay in sync.

| Launcher | Panel file | Role |
|----------|------------|------|
| **CATS CTC** | `cats/panels/HART_Master.xml` | Full CTC — Digicon owns routes **and** signal aspects |
| **CATS ABS** | `cats/panels/HART_Master_ABS.xml` | Open-house ABS — Digicon still drives aspects from plant/occupancy |
| **CATS ABS-RO** | `cats/panels/HART_Master_ABS_hold.xml` | Spectator / second screen — turnouts + occupancy on; signals `HOLD_ONLY` (paint from MQTT) |

Panels live at **`cats/panels/`** (not under `sheets/`). Sheet WIP and older experiments stay in `cats/panels/sheets/`. Checkpoints: `cats/panels/checkpoints/`.

Each Master carries a publication title row (Y=1):

- **HART RAILROAD** · **NEVILLE ISLAND OPERATIONS** · **P&CV DIVISION**
- Mode tag (`CTC DIGICON` / `ABS DIGICON` / `ABS-RO DIGICON`)
- Pub id (`DS-CTC` / `DS-ABS` / `DS-ABS-RO`) · Rev · Effective date

Rebuild ABS-RO after ABS edits:

```bash
python3 cats/scripts/build_hart_master_abs_hold.py   # HOLD_ONLY + re-stamps header
python3 cats/scripts/polish_hart_master_header.py --panel all
```

---

## 2. How the pieces interconnect

```text
┌─────────────────┐     Digicon aspect / route      ┌──────────────────┐
│  CATS Digicon   │ ───────────────────────────────►│  JMRI SignalMast │
│  CTC / ABS      │   bind by mast userName           │  (SHSM or MQTT)  │
└────────┬────────┘                                  └────────┬─────────┘
         │ turnout ROUTECOMMAND / SELECTEDREPORT              │
         │ occupancy paints from JMRI sensors                 │ Appearance
         ▼                                                    ▼
┌─────────────────┐                                  ┌──────────────────┐
│ JMRI Turnouts / │◄── MQTT retain paint (boot) ────│ MQTT broker       │
│ Sensors / Blocks│                                  │ minipc / Pi       │
└────────┬────────┘                                  └────────┬─────────┘
         │                                                    │
         │  track/turnout/#  track/sensor/#                   │
         │  track/signalhead/IH###  (virtual heads)           │
         │  track/signalmast/432    (Brick AAR mast)          │
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

Do **not** run PanelPro and CATS on the same profile at once. Only **one** Digicon should be signal authority (CTC or ABS). ABS-RO is for listening / turnout help.

---

## 3. Digicon geometry and ops features

### Geography (Neville Island)

Digicon schematic covers West Yard / Brick / Plane / Barn, South Yard ladder, East End, Princess, McKees Rocks / McKeesport leads — matching the Neville Island station maps and CSX/POV-era trackplan reference.

### Discipline

| Panel | Block `DISCIPLINE` | Dispatcher signal clicks |
|-------|--------------------|---------------------------|
| Master CTC | `CTC` | Left-click entrance signal = request route + code (release Hold) |
| Master ABS / ABS-RO | `ABS` | No CTC left-click routing; aspects follow plant |

CTC signals start **Held**. Left-click codes the route (`SIGNALINDICATIONLOCK`); when vital logic grants traffic, Digicon drops Hold and shows Approach/Clear. **Fleeting** is only for keeping a live route clear for following trains — it is disabled until a route is already ACTIVE (it is not “line first, clear later”). Closest “line then clear” workflow: throw turnouts manually (signal stays Held), then left-click when ready.

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

### Two families

| Family | JMRI object | Digicon `PHYSIGNAL` | MQTT | Field |
|--------|-------------|---------------------|------|-------|
| **AAR MQTT mast** (Brick East Main West only) | `IF$mqm:AAR-1946:…($432)` | `aar-single` (R-codes → Clear/Approach/Stop) | `track/signalmast/432` | Existing AAR mast path |
| **Virtual head + SHSM** (all other Digicon lamps) | Virtual `IH###` + `IF$shsm:cats-masts:cats-virtual[-2|-3](…)` | stock `single` / `double` / `triple` (native R-codes) | `track/signalhead/IH###` | LCOS searchlight ports |

Digicon binds by **mast userName** (exact string match). Panel lamps (`LAMP1|2|3`) are Digicon cosmetics; field head count comes from JMRI / LCOS wiring.

### Aspect language

- Digicon internals speak rule codes (`R281` Clear, `R285` Approach, `R292` Stop, `RES_*` Restricting, …).
- **cats-virtual** SHSM aspects stay in that vocabulary → Virtual heads get GREEN / YELLOW / RED / … appearances.
- **Brick 432** stays AAR vocabulary on the wire (`Clear; Lit; Unheld`). `aar-single` remaps Digicon R-codes → AAR names. Stub routes into W-Y often show Restricting → remapped to **Approach** on 432 (Restricting disabled on that mast).

### Authority

| Mode | Who drives Clear/Approach/Stop |
|------|--------------------------------|
| CTC / ABS | Digicon → JMRI mast/heads → MQTT (publisher for IH heads; native MQTT for 432) |
| ABS-RO (`HOLD_ONLY`) | Field / MQTT → JMRI; Digicon paints. CATS only Held/Unheld |

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
| Plane + W-1 / W-2 | **4** | C4 | `IH432`–`IH437` | C4-OU2-1 … OU2-6 |
| Barn / West Yard 117 | **13** (`013`) | C1 | `IH1332`–`IH1338` | C1-OU2-1 … OU3-1 |
| East End | **12** (`012`) | C7 | `IH1232`–`IH1241` | C7-OU2-1 … OU3-4 |
| Princess | **1** | D1 | `IH132`–`IH141` | D1-OU2-1 … OU3-2 |

Head roles on multi-head masts: **T** top, **M** middle, **B** bottom, **S** single.

Appearances for SHSM:

- 1 head → `cats-virtual`
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
| Brick East Main West | 2 (panel) | `IF$mqm:…($432)` | MQTT mast |
| Plane East East Main Ext | 2 | `…cats-virtual-2(IH432)(IH433)` | LCOS C4 |
| Plane East OS 102 | 2 | `…(IH434)(IH435)` | LCOS C4 |
| Brick West Yard 1 / 2 | 1 | `IH436` / `IH437` | LCOS C4 |
| West Yard West OS 117 | 2 | `IH1332`/`IH1333` | LCOS C1 |
| East End East Lead | 2 | `IH1237`/`IH1238` | LCOS C7 |
| Princess North McKees Rocks | 3 | `IH132`–`IH134` | LCOS D1 |
| Princess South McKeesport | 3 | `IH139`–`IH141` | LCOS D1 |

### JMRI ↔ MQTT for Virtual heads

`jmri/scripts/mqtt_signalhead_publisher.py` (Start Up; regenerated by `build_hart_signal_heads.py`):

1. **Boot:** `mosquitto_sub` retain on `track/signalhead/#` → `setAppearance` on listed `IH*` (no publish — does not stomp field SoR).
2. **Run:** PropertyChange on Appearance → `mqtt.publish("track/signalhead/"+sysName, appearanceName)` so Digicon-driven aspects reach LCOS.

**LCOS Nano bridge dual path** (`LCOS_ESP32_MQTT_Client`, see `docs/signal_dual_path.md`):

- **Send (Digicon → field):** subscribe `track/signalhead/IH###` → `EVENT_SIGNAL_CMD` (Red→Stop, Yellow→Approach, Green→Clear).
- **Receive (field → JMRI masts):** LCOS `EVENT_SIGNAL` → retained `track/signalmast/<packed>` (`Stop; Lit; Unheld`, …) so traditional MQTT Signal Masts still get aspect reports. Status is **not** published on `signalhead` (avoids looping Digicon).

Brick **432** does not use the IH list; JMRI’s MQTT Signal Mast adapter owns `track/signalmast/432`.

Rebuild heads + tables + publisher:

```bash
python3 cats/scripts/build_hart_signal_heads.py
```

Do **not** place cats-virtual LE `signalmasticon`s on Windows tables (NPE). Digicon does not need LE icons; it binds by userName.

---

## 5. Launch (all hosts)

| Host | How |
|------|-----|
| **Mac** | `/Applications/CATS CTC.app` (etc.) or `./cats/scripts/launch_cats.sh cats/panels/HART_Master.xml` |
| **Pi** | Desktop **CATS CTC** / **CATS ABS** / **CATS ABS-RO** → `/home/pi/hart/launch_cats.sh …` |
| **Windows** | Desktop shortcuts → `cats\scripts\windows\launch_hart_master*.bat` |

Default panel for `launch_cats.sh` is `cats/panels/HART_Master.xml`.

Profile tables (routes, YL internals, signal heads/masts) load from the host’s `preference:tables.xml` / Pi `JMRI_UserFiles/tables.xml` (repo mirror `jmri/layouts/hart/output/tables.xml`). Yard ladders need `IO:AUTO:0201–0210` and `IT:HART:YL:*` in that file.

### JMRI package (SSH deploy to hosts)

Same package carries Digicon Masters, `tables.xml`, yard-ladder button icons, and the JMRI **web home** override + Start Up scripts:

| Piece | Repo SoR | Installs to |
|-------|----------|-------------|
| CTC / ABS / ABS-RO panels | `cats/panels/HART_Master*.xml` | host `hart/cats/panels/` |
| Tables | `jmri/layouts/hart/output/tables.xml` | `preference:tables.xml` / `JMRI_UserFiles/tables.xml` |
| Ladder icons | `cats/resources/buttons/lamp_*.png` | `hart/cats/resources/buttons/` |
| Web home + STS | `cats/resources/jmri-web/` | profile / UserFiles `web/` (STS = Shipper-driven Traffic Simulator → `http://10.0.0.53:8980/sts/`) |
| JMRI Start Up scripts | `jmri/layouts/hart/scripts/apply_maintain_mqtt.py`, `sync_yard_ladder_buttons.py`; `jmri/scripts/mqtt_signalhead_publisher.py` | `hart/jmri/...` (Windows `home:hart/jmri/...`; Pi `/home/pi/hart/jmri/...`) |

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
| `cats/scripts/build_hart_master_abs_hold.py` | ABS → ABS-RO (`HOLD_ONLY`) + header |
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

1. One Digicon is signal authority; ABS-RO listens.
2. Never publish turnout “fix” commands at launch; retain paint is read-only.
3. Digicon Refresh Screen = safe (JMRI → Digicon). Refresh Layout pushes Digicon → JMRI — avoid for boot paint fixes.
4. Brick East Main West stays AAR MQTT mast `432`; everything else is packed `IH*` for LCOS.
5. After ABS panel edits, rebuild ABS-RO so `HOLD_ONLY` and the header stay in sync.

---

*Office of the Superintendent · Neville Island Operations · DS-DIGICON Rev A*
