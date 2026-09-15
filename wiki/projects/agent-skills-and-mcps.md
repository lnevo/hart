# Cursor skills and MCPs (review later)

- **Owner:** lnevo
- **Status:** Parked — review before building anything
- **Date:** 2026-09-14
- **Do not start:** no `SKILL.md` files, no MCP servers, until this page is reviewed

Inventory of **reusable** Cursor skills and MCP servers we could invest in, distilled from git history, pipeline READMEs, leftover scripts, and landmine docs. Goal is to help people (and agents) who use the **same software**, not to export HART-only railroad knowledge.

Chat source: skills/MCP backlog discussion, 2026-09-14.

---

## Review questions

1. Which of these (if any) should become **project** skills (`.cursor/skills/`) vs **personal** (`~/.cursor/skills/`)?
2. Build **two MCPs first** (`jmri-json` + `mqtt-layout`) or skills-only for a while?
3. Keep HART landmines as **rules** (already in `.cursor/rules/`) and only generalize the rest?

---

## Skills vs MCPs

| | Skills | MCPs |
|---|--------|------|
| What | Markdown the agent reads: landmines, workflows, do/don’t | Live tools the agent calls |
| When | Knowledge is in git history / scripts / “never do X” | Software already has HTTP/JSON or MQTT |
| Not | A second copy of HART ADRs | Serial ports, throttles, CATS Swing, flashing Nanos |

**Already in the room:** Chrome DevTools MCP (ops portal, GitHub Pages, STS HTML, JMRI web). GitHub/`gh` and generic Docker MCPs exist off the shelf — don’t rebuild.

**Already encoded as HART rules** (don’t duplicate as portable skills unless we want them off this railroad): LCOS bridge foreground-only; Dispatcher System is stock; `tables.xml` read-only; consolidation write-only tree; commit-by-default close-out.

**Keep HART-only (not skills):** public-name ADRs, packed `IH432` radio math, “don’t delete F30-S-0,” Neville Island industries.

---

## Skills — proposed investment list

### Tier 1 — write first

Hard-won landmines. Other JMRI / CATS / MQTT layouts hit these.

| # | Skill | Software | Why it exists here | What it would teach |
|---|--------|----------|--------------------|---------------------|
| 1 | `jmri-panel-xml` | JMRI Layout Editor | `prepare_tables_from_anyrail`, `apply_blocks_to_panel`, linear3 polish disasters | 1:1 geometry, `mainline="yes"`, integer `x`/`y`, never run fit/polish unless asked, panel XML vs tables XML |
| 2 | `jmri-tables-hygiene` | JMRI PanelPro tables | `tables.xml` vs `new_tables.xml`, never Store from CATS | Snapshot vs working file; PanelPro owns beans; CATS only refers to user names |
| 3 | `jmri-dispatcher-system` | JMRI Dispatcher System | Stage 1 launchers, traininfo retarget, stock-only rule | Run stock Discover/Stage 1; fix mast bindings and block comments; never wrap `CreateTransits` |
| 4 | `jmri-sml-nx` | JMRI SML + NX | `run_sml_discover.sh`, `run_nx_discover.sh`, facing scripts | Discover from PanelPro (modals visible); frozen NX ids; Enable lists ≠ MQTT allow-list |
| 5 | `cats-on-jmri` | CATS 3.2 + Designer | `fetch_cats_3.2`, `install_into_jmri`, `validate_cats_panel` | JMRI 4.24–5.16 pin; install next to `jmri.jar`; Designer-first CTC; never decompile `cats.jar` |
| 6 | `jmri-mqtt-layout` | JMRI MQTT + Mosquitto | `mqtt_signalhead_publisher`, retain-clear, packed topics | `track/turnout\|sensor\|signalhead\|signalmast`; retain storms; don’t put `IH` in the topic leaf |
| 7 | `lcos-serial-mqtt` | LCOS Nano + Arduino + Python bridge | `serial_to_mqtt.py`, event 125, foreground-only | Flash Nano; COM 250000; **foreground bridge**; subscribe/RESUBSCRIBE; lab start/stop |

### Tier 2 — strong pipelines, narrower audience

| # | Skill | Software | Why it exists here | What it would teach |
|---|--------|----------|--------------------|---------------------|
| 8 | `anyrail-to-jmri` | AnyRail → JMRI | Pipeline 1 (frozen for hart; live for linear4/mac) | Export → prepare `--scale 1` → blocks Excel → apply with a style panel |
| 9 | `jmri-uss-ctc` | JMRI USS CTC | `gen_ctc_track_plan.py`, icon deploy | Generate from a plan; regenerate instead of string-replacing `GUIObjects.xml`; never with CATS CTC |
| 10 | `openlcb-mqtt-twins` | OpenLCB / LCC + MQTT | `lcc_turnout_contract.py`, MTT* restore | Keep LCC aliases as required twins of MQTT turnouts; don’t “clean up” `MTT*` |
| 11 | `layout-host-deploy` | rsync / SSH / Pi / Windows JMRI | `sync_hart_package.sh` | Stage panels, jython, icons, tables bundle to JMRI user-files on two OSes |
| 12 | `mosquitto-layout-bus` | Mosquitto | mqtt-broker package, mimic, retain gates | Broker as layout bus; ping/ACK; same host for JMRI and the serial bridge |
| 13 | `sts-docker` | Shipit (STS) + Docker + MySQL | `sts_compose.sh`, seed/session helpers | Compose bind paths, seed roster/waybills, warm-start, switch lists, session backups |
| 14 | `car-cards-ocr` | Python + OCR + Word | `process_car_images`, `generate_all_cards` | Lightbox photos → crop → OCR → poker-size sticker sheets |
| 15 | `waybills-and-industries` | Excel/CSV + STS seed | waybill scripts, industry matrix validators | Commodity/car-type rules; keep paper CSV in sync with STS seed |
| 16 | `decoderpro-speed-matching` | DecoderPro / JMRI roster | parked STRR SOP under `jmri/docs/speedmatching` | Measured speed tables vs synthetic Dispatcher profiles; adapt sensors/scale |
| 17 | `kicad-pcbway-bom` | KiCad + Mouser + PCBWay | LCOS `build_esp32io_pcbway_bom.py` | Interactive BOM HTML + Mouser cart → manufacturing xlsx (Gerbers alone are not enough) |
| 18 | `jython-jmri-startup` | JMRI Jython | startup patchers, ShutdownTask, LogixNG | `preference:jython/` pitfalls (`from __future__` breaks Dispatcher); boot vs quit MQTT |
| 19 | `layout-wiring-docs` | Excel + PowerPoint from CSV | `refresh_wiring_docs.py`, schematic PPTX | Pin maps → inventory workbook + per-node slides; Desktop ARCHIVE one-offs are not SoR |

### Tier 3 — useful, but more “our stack” or already generic

| # | Skill | Software | Notes |
|---|--------|----------|-------|
| 20 | `google-sheets-bulk-push` | Google Sheets API | Abandoned for hart; still: `clear()` + bulk `addRows`, never per-row delete (429) |
| 21 | `jmri-to-schematic-xlsx` | NextTrain / xlsx export | Coordinate transform via `export_options.json`; same scale for segments and control points |
| 22 | `ops-docx-pptx` | python-docx / python-pptx | Crew pubs, station maps — don’t hand-edit generated Word |
| 23 | `github-pages-ops-site` | GitHub Pages + Actions | Static crew portal; JSON pages need HTTP, not `file://` |
| 24 | `macos-launchagents-helpers` | launchd | Portal / mimic agents that survive Cursor quit |
| 25 | `mqtt-hardware-mimic` | MQTT QA without field hardware | Enroll from live `signalmast` roster, not a static allow-list |
| 26 | `generated-xml-discipline` | any generator | Change the CSV/script, regenerate; never search-replace generated CATS/USS/signal XML |
| 27 | `live-vs-consolidation-tree` | git workspaces | Parallel SoR tree; live paths read-only; validators write only to audits |

### Suggested skill build order (if we invest a little at a time)

1. `jmri-panel-xml` + `jmri-tables-hygiene`
2. `jmri-sml-nx` + `jmri-dispatcher-system`
3. `cats-on-jmri`
4. `jmri-mqtt-layout` + `lcos-serial-mqtt`
5. One **ops** skill (`sts-docker` or `car-cards-ocr`) and one **docs/hardware** skill (`layout-wiring-docs` or `kicad-pcbway-bom`)

Evidence in-repo: [`wiki/pipelines/README.md`](../pipelines/README.md) (16 flows), [`docs/AI_CONTEXT.md`](../../docs/AI_CONTEXT.md), `cats/scripts/`, `jmri/scripts/`, `consolidation/packages/`.

---

## MCPs — proposed investment list

Rule of thumb: **HTTP/JSON or MQTT → MCP. Landmines and file pipelines → skill. Operator-owned console → neither.**

### Tier 1 — worth building

| # | MCP | Talks to | Why this repo wants it | Safe default |
|---|-----|----------|------------------------|--------------|
| 1 | `jmri-json` | PanelPro web JSON (`/json/turnout`, `/json/sensor`, `/json/signalMast`, `/json/block`, roster, power) | Mimic QA already curls `:12080`. Live bean bus; any JMRI layout could use it. | **Read-only** list/get. Writes (throw turnout, set appearance) off by default. |
| 2 | `mqtt-layout` | Mosquitto (`track/#`) | Shell-outs to `mosquitto_pub/sub` in mimic, retain-clear, turnout FB sync, PING. | Subscribe + dump retained. **Never** publish `track/cmd` unless the user asked. Clear-retain is a named dangerous tool. |

Pair `mqtt-layout` with the `jmri-mqtt-layout` skill: MCP is generic pub/sub/list; packed-leaf / enroll-from-roster stays in the skill.

If we only build **two** MCPs, build these.

### Tier 2 — useful, narrower

| # | MCP | Talks to | Notes |
|---|-----|----------|-------|
| 3 | `sts` | `localhost:8980` + MySQL `hart_seed` | List cars, spots, switch lists, session state. Read-only first; seed apply stays a script. |
| 4 | `jmri-xml-query` (or HART-shaped `hart-panel-audit`) | Files, not a running app | Wrap `audit_panel_contracts`, public-name map, occupancy/turnout CSVs. Pattern is reusable; names are HART-shaped. |
| 5 | `xlsx-inventory` | Wiring / industry / car-card workbooks | Only if agents keep grepping xlsx badly. Scripts + a skill may be cheaper. |

### Don’t build

| Tempting MCP | Why not |
|--------------|---------|
| LCOS serial / COM / `serial_to_mqtt` | Foreground, operator-owned; don’t steal COM3. Probe MQTT `track/bridge/status`, never the serial port. |
| CATS Designer / CTC | No stable API (Swing). Validate XML + screenshots. |
| Arduino flash | Human + IDE / `flash_nano.py`. |
| Google Sheets | Abandoned for hart; official Sheets MCP exists if ever needed. |
| KiCad | We only merge Interactive BOM HTML. |
| WiThrottle / DCC command | Shared throttle vs AutoActiveTrain already burned us. |
| Ops-portal review POST | Tiny local HTTP; `curl` or Chrome is enough. |
| rsync deploy to Pi/Windows | Keep as a script the skill tells the agent to run. |

### MCP design constraints (lock before coding)

1. **Read-first.** List/get/subscribe default. Throws, SET aspects, retain-clear, seed-apply require an explicit user ask.
2. **No field commands from “fix paint.”** Same as [`AGENTS.md`](../../AGENTS.md): must not publish `track/cmd` as a convenience.
3. **No serial, no JMRI monkey-patch, no CATS Store.**
4. **Local-only.** Lab broker / `127.0.0.1:12080` / STS Docker — don’t expose layout hosts to make Cloud Agents happy.
5. **Pair every MCP with a skill.** JSON servlet won’t tell you Enable ≠ MQTT allow-list, or that CATS and USS mustn’t run together.

### Skill ↔ MCP map

```text
Skill (knowledge)              MCP (live tools)
─────────────────              ────────────────
jmri-panel-xml                 jmri-xml-query (optional)
jmri-tables-hygiene            —
jmri-sml-nx                    jmri-json (read SML/masts)
jmri-dispatcher-system         jmri-json (roster/power) — still no Stage 1 from MCP
cats-on-jmri                   — (files + Chrome if web)
jmri-mqtt-layout               mqtt-layout
lcos-serial-mqtt               mqtt-layout (status only)
sts-docker                     sts (read) + Docker (generic)
car-cards / waybills           — (scripts)
layout-host-deploy             — (script)
```

---

## When this is accepted

1. Tick the review questions at the top.
2. If building: start with skill authoring (`~/.cursor/skills-cursor/create-skill` pattern) for Tier 1 #1–2, or the two MCPs — not both at once unless we mean to.
3. Move this page from **Parked** to Active (or drop it) and clear the pointer in [`WAITING_ON_HUMAN.md`](../WAITING_ON_HUMAN.md).
