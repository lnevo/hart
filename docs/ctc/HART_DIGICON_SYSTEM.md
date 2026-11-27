# HART Digicon (CATS) — System Overview

End-to-end overview of the Digicon CATS panels, how they talk to JMRI and MQTT, and how LCOS signal heads are addressed.

**Publication:** DS-DIGICON · Rev B · Eff 2026-11-09 (Rev A 2026-08-11)  
**Railroad:** HART Railroad · Pittsburgh & Chartiers Valley Division · Neville Island Operations  
**Scope:** Digicon CTC / ABS panels, JMRI MQTT bridge, LCOS signal heads

**Parked:** the USS CTC lever machine, its panel and sensors, the Dispatcher System and Entry/Exit are parked since the helix-join release (November 2026): not in the active tables; data kept in `jmri/layouts/hart/parked/`. The CATS desks are the only dispatcher desks.

This is the end-to-end picture of what we built: Digicon panels on Mac / Pi / Windows, how they talk to JMRI and MQTT, and how field signal heads are addressed for LCOS hardware.

Related detail docs (do not duplicate here):

| Topic | Doc |
|-------|-----|
| Signal facing / mast bind | [`SIGNAL_FACING.md`](SIGNAL_FACING.md) |
| Turnout SoR | [`TURNOUT_STATE_SOURCES.md`](TURNOUT_STATE_SOURCES.md) |
| Sensor status-only MQTT | [`MQTT_SENSOR_STATUS_ONLY.md`](MQTT_SENSOR_STATUS_ONLY.md) |
| Pi install notes | [`tools/hosts/pi/README_CATS.txt`](../../tools/hosts/pi/README_CATS.txt) |
| Neville trackplan (reference) | [`station_maps/Neville_Island_Trackplan_Clean.png`](../../ops/station_maps/maps/Neville_Island_Trackplan_Clean.png) |

---

## 1. What we built

Two Digicon desks for Neville Island ops, CATS CTC and CATS ABS, built from one Designer drawing, plus JMRI tables and scripts so Digicon, MQTT, SML and LCOS stay in sync.

| Launcher | Panel file | Role |
|----------|------------|------|
| **CATS CTC** | `cats/panels/HART_CTC.xml` | **Live CTC** — Digicon codes routes / throws; signals `HOLD_ONLY`; **JMRI SML** owns aspects |
| **CATS ABS** | `cats/panels/HART_ABS.xml` | **Live ABS** — `HOLD_ONLY`; SECSIGNALs bound to JMRI masts so Digicon **paints SML**. |

Both desks are generated from the schematic (`tools/schematic/build_cats_panel.py`, all three levels; owner approved in real CATS on 2026-11-15, live since the CATS cut-over). Never edit a desk by hand: change the schematic, the switch facts or the build, then rebuild. `HART_Digicon.xml` and `wire_digicon.py` (now `archive/code/cats-scripts/wire_digicon.py`) built the earlier hand-wired desks; the last of those are in git history at commit `42192d9c`, before the CATS cut-over (`git show 42192d9c:cats/panels/HART_CTC.xml`). The retired West Yard sheet scripts are in `archive/code/cats-scripts/west_yard/`.

Each desk carries a publication title row (Y=1):

- **HART RAILROAD** · **NEVILLE ISLAND OPERATIONS** · **P&CV DIVISION**
- Mode tag (`CTC DIGICON` / `ABS DIGICON`)
- Pub id (`DS-CTC` / `DS-ABS`) · Rev · Effective date

Rebuild both desks (`make desks` also validates them):

```bash
make desks
```

---

## 2. How the pieces interconnect

```text
┌─────────────────┐     route / Hold only              ┌──────────────────┐
│  CATS CTC       │ ── setHeld + ROUTECOMMAND ────────►│  JMRI SignalMast │
│  HOLD_ONLY      │   bind by mast userName            │  Basic SHSM      │
└────────┬────────┘                                    └────────┬─────────┘
         │ turnout throws                                      │ SML aspects
         │ occupancy paints from JMRI sensors                  │ Appearance
         ▼                                                     ▼
┌─────────────────┐                                  ┌──────────────────┐
│ JMRI Turnouts / │◄── live MQTT reports ───────────│ MQTT broker       │
│ Sensors / Blocks│                                  │ Pi (10.0.0.150)   │
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

1. `jmri/layouts/hart/scripts/panel_status.py` — panel status lamps; it never commands plant turnouts: **LCOS** (RESUBSCRIBE), **Turnouts** (TWOSENSOR↔DIRECT), **Signals** (Digicon SML), **Track Power** (LCC PowerManager ON/OFF).
2. `jmri/scripts/signal_coordinator.py` — Digicon SML MQTT bridge: main-window **SML Enabled / SML Disabled** toggle; when Enabled, publish IH appearances on `track/signalhead/<packed>`; when Disabled (global or per-mast SML off), apply `track/signalmast/<packed>` → IH and (on per-mast disable edges / operator Disable) publish `Unheld`. Answers `track/bridge/sml_mode` **query** / **disabling** with **enabled** while globally Enabled. **Boot:** if Digicon dests loaded **Enabled** (stored tables), warning popup, publish **`enabling`** and leave dests on (that instance does not abort). Operator **Force override** (sml_mode already enabled) publishes the same **`enabling`** token. Other agents seeing that token publish **`aborting`**, uncheck immediately (no Hold/Red/Unheld), then **`aborted`**, and stay Disabled. After ~3s the originator publishes **`enabled`**. Solo has nobody to abort; if `enabled` never arrives, the LCOS bridge challenges to **disabled**. Clean boot still holds dests off and **reads** `sml_mode` only (no retain publish); missing/`disabled`/`disabling` → take Digicon (enable); `enabled` / enabling-abort tokens → stay Disabled with **no Unheld** (originator owns resume). Digicon SML dests are stored **Enabled=no** in `tables.xml`: the generator applies it (`tools/schematic/build_tables.py`, `hartlib.tables_sml.disable_digicon`), and `disable_digicon_sml_in_tables.py --check` holds it. **Claims (2026-11-19):** `sml_mode` payloads stay the bare words the LCOS bridge reads. Each `enabling` / `enabled` is followed by a retained claim on `track/bridge/sml_claim`, which only the coordinators read: `enabling <host> <ms>` / `enabled <host> <same ms>`, with ` force` for Force override and stored dests. When two hosts claim at once the smaller key wins (force, then earlier stamp, then host name). Stamps are compared only with each other, so clock skew changes the winner but never gives two owners. Both hosts must run the same coordinator; the bridge needs no change.

(`unhold_signal_masts.py` is retired: masts boot Unheld, so SML runs ABS by default; **Held is CATS CTC's channel** — it holds homes at panel load and unholds when the dispatcher lines a route. A blanket unhold watchdog fought that.)

SML dests are **native**: Layout Editor Discover generates them (`jmri/layouts/hart/scripts/run_sml_discover.sh` one-shot) and they are stored in `tables.xml` with `useLayoutEditor=yes`, so JMRI re-paths them on every load. Re-running Discover is safe; the discover wrapper takes the Store's logic into `data/schematic/discovered_sml.xml` and regenerates `tables.xml` (`tools/schematic/build_tables.py --discovered-from`), which stores Digicon source→dest pairs **Enabled=no** until the Digicon MQTT script enables them (do not Store tables from a live Enabled Digicon session if you want that boot default to stick). The old hand-pair injector `apply_sml_cats_pairs.py` was removed on 2026-11-14; its pairs and the home-made prediction script were retired on 2026-11-16: JMRI's own discovery is the reference, so check signal logic by running stock Discover / Stage 1 in the sandbox rehearsal and comparing the stored pairs with the previous tables. Facing is set by the generated panel (`build_layout_le.py` places each mast from `masts.csv`). Advanced routing is `blockrouting="yes"` on `<layoutblocks>`. Two-head masts use stock **Basic** `two-searchlight` and dwarfs `one-low` (ADR-011); facing and binding are in [`SIGNAL_FACING.md`](SIGNAL_FACING.md).

**PanelPro vs CATS (same profile, sequential — never simultaneous):**

- **PanelPro** — edit/store JMRI tables, connections, Start Up. Then quit. Never Store tables while a CATS layout is open (Rodney Black, cats-users #2534).
- **CATS** — separate JMRI app (`cats.apps.Crandic`). Profile Start Up loads `preference:tables.xml` first (HART equivalent of Designer “Include”), then the Digicon XML. Refers to JMRI beans by user name; does not redefine them. LogixNG hides WiThrottle (IQC:AUTO:0001) and, under CATS only, **HART Railroad** (IQC:AUTO:0004 / `hide_cats_desk_windows.py`) so the Digicon stays up.
- Do **not** run both at once (MQTT client-id + profile lock). Only **one** Digicon should be signal authority (**CATS CTC** or **CATS ABS**).


### JMRI prefixes in Designer

Enable these connection prefixes in Designer. Device bindings come from the switch facts and `tables.xml`; the rows below are what `tables.xml` holds. Bind by **user name** from the occupancy and turnout CSVs wherever Designer allows.

| Prefix | Type | Use |
|--------|------|-----|
| M2S | Sensor | MQTT occupancy and switch feedback (`Block 4-2`, Switch FB) |
| M2T | Turnout | MQTT field switches (`M2T408` = Switch 1) |
| IS | Sensor | Internal: status sensors. The USS CTC lever and panel sensors (`IS3:LEVER`, `IS:RELOADCTC`) and the Dispatcher sensors are parked |
| IT | Turnout | Internal: the main and upper level turnouts (`IT:HART:C3:<n>`) until the device-map import |
| IF$shsm / IF$vsm | Signal mast | Basic signal-head masts and virtual masts; CATS refers to them by user name |

Blank Digicon cells come from CATS source behaviour, not the tables: see [`CATS_SOURCE_PAINT.md`](CATS_SOURCE_PAINT.md).

---

## 3. Digicon geometry and ops features

### Geography (Neville Island)

Digicon schematic covers West Yard / Brick / Plane / OS Barn, South Yard ladder, East End and Princess, matching the Neville Island station maps and the CSX/POV-era trackplan reference.

Princess (ADR-017): east of Switches 39 and 37 the mainline stubs are **Track Helix Outer** and **Track Helix Inner**, and the loop legs are **Track K-1** and **Track K-2**. The desks draw K-1 / K-2 on the outer rows running off the east edge, with the mains in the centre; the Layout Editor panel keeps the physical loop. Mast **40LA** / **38LA** are two-head on the mains and **40LB** / **38LB** are dwarfs on K-1 / K-2. None of the four has field hardware yet.

### Discipline

| Panel | Block `DISCIPLINE` | Dispatcher signal clicks |
|-------|--------------------|---------------------------|
| CATS CTC | `CTC` | Left-click entrance = request route + Unhold; **SML** sets the aspect |
| CATS ABS | `ABS` | No CTC left-click routing; SML follows occupancy / points |

CTC homes start **Held** (CATS holds them at panel load). Left-click codes the route; Digicon drops Hold and SML shows Approach/Clear. Without CATS, masts simply boot Unheld so SML runs ABS — no script needed. **Fleeting** is only for keeping a live route clear for following trains — it is disabled until a route is already ACTIVE.

### Yard ladder lamps (retired)

The hand-wired desk's ten yard-ladder lamp buttons (internal turnouts `IT:HART:YL:L1…R5`, routes `IO:AUTO:0201–0210`) were retired on 2026-11-17 (owner): no desk or panel used them. The builder leaves them out of `tables.xml` (`build_layout_le.py`, `retire_yard_ladder`) and `panel_status.py` no longer paints them.

### Turnout SoR (summary)

Live Digicon follows field feedback for most plants; Digicon `SELECTEDREPORT` and `ROUTECOMMAND` share polarity. Tip SoR for 112 / 114 / 115 is documented in [`TURNOUT_STATE_SOURCES.md`](TURNOUT_STATE_SOURCES.md). Agents must not throw field points to “fix” paint.

### Load safety

CATS is stock. A turnout report that arrives during panel load can kill `RREventManager`, which freezes occupancy until CATS restarts; see `wiki/STATUS.md`.

---

## 4. Signals — nature and LCOS heads

### One family

| Family | JMRI object | Digicon `PHYSIGNAL` | MQTT | Field |
|--------|-------------|---------------------|------|-------|
| **Virtual head + SHSM** (all Digicon lamps) | Virtual `IH###` + `IF$shsm:basic:two-searchlight` two-head / `IF$shsm:basic:one-low` dwarf | stock `single` / `double` (native R-codes remapped to Basic names) | `track/signalhead/<packed>` | LCOS searchlight ports |

Digicon binds by **mast userName** (exact string match). Panel lamps (`LAMP1|2|3`) are Digicon cosmetics; field head count comes from JMRI / LCOS wiring.

### Aspect language

- Digicon internals speak rule codes (`R281` Clear, `R285` Approach, `R292` Stop, `RES_*` Restricting, …).
- **Basic** SHSM aspects are Clear / Approach / Diverging Clear / Diverging Approach / Stop (2-head) or Clear / Approach / Stop (dwarf). `aar_aspect_bridge.py` remaps Digicon R-codes to those names.
- Virtual heads get GREEN / YELLOW / RED appearances; `signal_coordinator.py` publishes those names on `track/signalhead/<packed>`.

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
MQTT   = track/signalhead/<packed>   # IH432 → topic …/432 (bean stays IH432)
Payload = appearance name      # Red / Yellow / Green / Dark / …
```

Full disc × board × G/Y/R map (every mast, every OU including 12V motors and spare/relay pins): [`docs/wiring/README.md`](../../docs/wiring/README.md#digicon-heads-and-ou-boards).

Head roles: **T** top, **B** bottom; dwarfs are a single 3-pin disc.

Appearances for SHSM:

- 1 head → Basic `one-low`: Clear, Approach, Stop
- 2 heads → Basic `two-searchlight`: Clear, Approach, Stop, Diverging Clear, Diverging Approach

No aspects are disabled; Basic has no Advanced Approach to disable.

**Counts:** 90 masts in `tables.xml`: 64 real (24 `two-searchlight`, 40 `one-low`) and 26 virtual.

**Mast 6LB (interim):** a one-low dwarf on `IH432` (C4-OU2-1..3), the only head wired so far. `IH433` stays defined but unwired and on no mast. It returns to two-searchlight when the second head's rows are added to `jmri/layouts/hart/data/wiring.csv`; `build_hart_signal_heads.py` builds each mast from its wired heads only. The wiring docs still show that two-head plan.

Mast icons use the Basic `default` image set (JMRI draws it with its stock AAR-1946 schematic GIFs): scale 1.0 on the Layout Editor panel (45 icons). The USS CTC panel (0.5, 11 icons) is parked.

### Mast index (Digicon name → JMRI)

Full table: [`jmri/layouts/hart/output/signal_head_plan.csv`](../../jmri/layouts/hart/output/signal_head_plan.csv), every wired mast and its JMRI binding  
Port / topic / LCOS inventory: the head rows of [`jmri/layouts/hart/data/wiring.csv`](../../jmri/layouts/hart/data/wiring.csv) (`hartlib.wiring.digicon_rows` gives the pins, IH number and topic)  
The old plan's mast table (history, archived 2026-11-21): [`archive/data/wiring/signals/signal_mast_plan.csv`](../../archive/data/wiring/signals/signal_mast_plan.csv)

Pin map: [`docs/wiring/README.md`](../../docs/wiring/README.md#digicon-heads-and-ou-boards) · CSVs above.

### JMRI ↔ MQTT for Virtual heads

`jmri/scripts/signal_coordinator.py` (Start Up): Digicon plants are discovered from JMRI SignalMasts that carry LCOS Virtual `IH*` heads (UID 32–47). MQTT SET/Unheld requires enrollment from `track/signalmast/<packed>` (bridge + field status). `build_hart_signal_heads.py` no longer patches a `HEAD_NAMES` list.

Digicon SML MQTT controller — toggle **SML Enabled / SML Disabled**, SET publish when Enabled (enrolled heads only), mast→IH when SML off, per-mast `Unheld` on disable **edges**, `track/bridge/sml_mode` query ACK. Digicon SML pairs are stored **Enabled=no** in tables. Stored-Enabled boot or Force override publishes **`enabling`** and does not abort; other agents abort (immediate uncheck, no RELEASE) then **`aborted`**; originator announces **`enabled`** after ~3s. Clean boot holds dests off, **reads** `sml_mode` (no retain publish); missing/`disabled` → enable Digicon; `enabled` / enabling-abort tokens → stay Disabled with no Unheld. SML / SHSM still own aspects while Enabled; Held remains CATS/USS veto.

**LCOS Nano bridge dual path** (`LCOS_ESP32_MQTT_Client`, see [`external/lcos-bridge/docs/signal_dual_path.md`](../../external/lcos-bridge/docs/signal_dual_path.md) in that submodule):

- **Send (Digicon → field):** when SML Enabled for that mast, `track/signalhead/<packed>` → `EVENT_SIGNAL_CMD` SET (Red→Stop, Yellow→Approach, Green→Clear). Global Disable or per-mast SML off → `Unheld` RELEASE. Bridge `sml_mode` **query** / **disabling** timeout also Red→Unheld if no Digicon **enabled** ACK.
- **Receive (field → Digicon IH):** when SML is off for that mast (or globally Disabled), LCOS `track/signalmast/<packed>` (`Stop; Lit; Unheld`, …) is applied to the matching `IH*` head. Status is not published on `signalhead` from the field.

Mast 2L is the same packed-head path (`IH438`/`IH439` on C3-OU3). JMRI no longer publishes `track/signalmast/432`.

Rebuild the head plan (publisher roster is dynamic): `make panels` runs it as its head-plan step, writing `jmri/layouts/hart/output/signal_head_plan.csv`; `make panels CHECK=1` checks it:

```bash
make panels
make panels CHECK=1
```

Head IH numbers in `tables.xml` follow the wiring plan (packed = radio address × 100 + slot); `tools/audit/check_wiring_crosswalk.py` fails in `./tools/check.sh` when a head on a physical mast differs from `wiring.csv`. `build_hart_signal_heads.py` writes only `signal_head_plan.csv`; it never writes `tables.xml`. Change heads and masts in `tables.xml` directly (PanelPro and CATS closed), then run `make panels` and check that `git diff` shows only what you meant. An interim build with fewer heads than planned (Mast 6LB) has only its wired heads' rows in `wiring.csv`, and the head plan follows them.

LE `signalmasticon`s use the stock Basic `default` image set (no custom imagelinks). Digicon binds by userName either way.

---

## 5. Launch (all hosts)

| Host | How |
|------|-----|
| **Mac** | `/Applications/CATS CTC.app` / `CATS ABS.app` or `./cats/scripts/launch_cats.sh` |
| **Pi** | Desktop **CATS CTC** / **CATS ABS** |
| **Windows** | Desktop **CATS CTC** / **CATS ABS** |

Default panel for `launch_cats.sh` is `~/JMRI_UserFiles/cats/panels/HART_CTC.xml`, which deploy installs.

Profile tables (turnouts, signal heads and masts, SML) load from `preference:tables.xml`, which is `JMRI_UserFiles/tables.xml` (repo mirror `jmri/layouts/hart/output/tables.xml`).

### JMRI package (SSH deploy to hosts)

Same package carries the CATS desks, `tables.xml`, the button icons, and the JMRI **web home** override + Start Up scripts:

| Piece | Repo SoR | Installs to |
|-------|----------|-------------|
| CTC / ABS desks | `cats/panels/HART_CTC.xml`, `HART_ABS.xml` | host `JMRI_UserFiles/cats/panels/` |
| Tables | `jmri/layouts/hart/output/tables.xml` | `preference:tables.xml` / `JMRI_UserFiles/tables.xml` |
| Ladder icons | `jmri/resources/buttons/lamp_*.png` | `JMRI_UserFiles/resources/buttons/` |
| Web home + STS | `jmri/resources/jmri-web/servlet/home/Home.html` | `JMRI_UserFiles/web/servlet/home/` (STS link in Home.html → `http://<page host>:8980/sts/`; STS runs on the Pi, ADR-020) |
| JMRI Start Up scripts | `panel_status.py`, `signal_coordinator.py`, `jmri_cmd_watcher.py` (Pi), `sts_car_sync.py` (Pi, Mac) | `preference:jython/`, which is `JMRI_UserFiles/jython/` on every host (ADR-014). `hide_cats_desk_windows.py` is called by LogixNG from the same folder. |

Deploy via SSH (agent does this — no manual batch/Dropbox step):

```bash
./tools/hosts/sync_hart_package.sh --pi    # Pi (rsync + local apply)
./tools/hosts/sync_hart_package.sh --win   # Windows SSH :2222 (one tarball + apply)
./tools/hosts/sync_hart_package.sh --all   # Mac web + Pi + Windows
./tools/hosts/sync_hart_package.sh --pi --dry-run
./tools/hosts/sync_hart_package.sh --stage-only /tmp/pkg   # build the packages only, no ssh
./tools/hosts/deploy_status.sh --pi --win                # commit each host last got (cats/deploy_stamp.txt)
```

Windows runs Win32-OpenSSH 10.4 (winget `Microsoft.OpenSSH.Preview`) on port 2222, with `Subsystem sftp sftp-server.exe` in `C:\ProgramData\ssh\sshd_config`. Deploys copy over SFTP and fall back to legacy `scp -O` with a warning if that line is missing. Its ssh sessions get only the machine PATH; Python 3.12 is a per-user install, so `apply_hart_package_local.ps1` puts the user PATH first, then runs the Start Up retarget with `py -3`, `python` or `python3`, whichever it finds first (Store stubs skipped). With none it warns and skips the retarget rather than failing the deploy.

---

## 6. Source-of-truth scripts

| Script | Purpose |
|--------|---------|
| `tools/schematic/build_cats_panel.py` | Builds `HART_CTC.xml`, `HART_ABS.xml` and `HART_CTC.bindings.json` from the schematic and the railroad's facts (`--check`) |
| `archive/code/cats-scripts/wire_digicon.py` | Archived: built the hand-wired desks from `HART_Digicon.xml` before the CATS cut-over |
| `cats/scripts/cats_turnout_io.py` | Turnout CSV → SWITCHPOINTS IO (used by `build_cats_panel.py`) |
| `archive/code/cats-scripts/aar_aspect_bridge.py` | Archived with `wire_digicon.py`: Digicon R-codes ↔ Basic aspect names |
| `jmri/layouts/hart/scripts/discover_sml.py` | PanelPro one-shot SML Discover (background; do not leave on Start Up) |
| `jmri/layouts/hart/scripts/run_sml_discover.sh` | Launch PanelPro, Discover, store `tables.xml`, quit; then disable Digicon SML dests |
| `jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py` | `--check`: Digicon SML dests are Enabled=no in `tables.xml` (`tools/check.sh`). The generator applies the rule and the deploy ships the committed bytes (R9c); `--panel` patches another tables file only |
| `archive/code/cats-scripts/digicon_header.py` | Archived with `wire_digicon.py`: the publication title row (now `cats/data/generated_desk_header.xml`) |
| `jmri/layouts/hart/scripts/build_hart_signal_heads.py` | The head and mast plan CSVs from `wiring.csv`'s wired heads (one mode; `--wiring-only` still accepted). `tables.xml` is generated (ADR-029) |
| `tools/hosts/sync_hart_package.sh` | Stage the package to a temporary folder on the host; **rsync** to Pi, **tar+scp** to Windows (no git pull). Host apply copies into `JMRI_UserFiles`. `--dry-run`. Before copy, sets Digicon (MQTT) SML dests to Enabled=no in the shipped `tables.xml` |
| `cats/scripts/install_jmri_web_override.sh` | STS link into JMRI `web/` (Mac/Pi) |
| `tools/hosts/windows/apply_hart_package_local.ps1` | Windows host apply step, run over SSH by `sync_hart_package.sh --win` (Pi equivalent: `tools/hosts/pi/apply_hart_package_local.sh`) |
| `jmri/layouts/hart/scripts/jmri_cmd_watcher.py` | Remote-run hook: runs a dropped command file inside JMRI ([`wiki/AGENTS_GIT.md`](../../wiki/AGENTS_GIT.md)) |
| `jmri/scripts/signal_coordinator.py` | Digicon SML MQTT: SET when Enabled, mast→IH when Disabled, sml_mode guard ACK |

---

## 7. Operating rules (short)

1. **CATS CTC** and **CATS ABS** both `HOLD_ONLY`: SML sets aspects; Digicon paints JMRI appearances. CTC also Held/Unhold on coded routes. ABS Hold/Unhold follows Digicon ABS vital logic. Layout Editor is always SML.
2. Never publish turnout “fix” commands at launch.
3. Digicon Refresh Screen = safe (JMRI → Digicon). Refresh Layout pushes Digicon → JMRI — avoid for boot paint fixes.
4. All Digicon lamps are packed `IH*` SHSM — two-head homes on **Basic** (`two-searchlight`), dwarfs on **`one-low`**. No aspects are disabled. Mast 2L is `IH438`/`IH439`.
5. After a schematic or switch-fact change, run `make panels` (its cats step), or `make desks` for the desks alone. Both rebuild both desks, so `HOLD_ONLY` and mast bindings stay in sync.