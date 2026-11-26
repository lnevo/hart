# CATS integration (HART)

[CATS](http://cats4ctc.wikidot.com/) is a Digicon-style CTC suite that runs **on JMRI** for hardware I/O and owns interlocking via a **Designer** panel XML (not a Layout Editor import).

| Piece | Role |
|-------|------|
| **Designer** | Draw CTC schematic; bind JMRI sensors/turnouts/signals |
| **CATS** | Runtime dispatcher panel (routes, N/X, occupancy colors, train labels) |
| **TrainStat** | Optional yard/trainmaster client ([download](http://cats4ctc.wikidot.com/main:downloadts)) |

**SoR:** [`wiki/decisions/ADR-004-cats-ctc.md`](../wiki/decisions/ADR-004-cats-ctc.md)

## JMRI pin

Use **CATS 3.2** with **JMRI 4.24–5.16** ([downloads](http://cats4ctc.wikidot.com/main:downloads)).  
HART runs JMRI **5.16**, the newest version 3.2 supports.

```bash
./tools/cats/fetch_cats_src.sh   # Bitbucket source → tools/cats/src-repo/ (gitignored)
./tools/cats/fetch_cats_3.2.sh   # → tools/cats/release3.2/ (gitignored binaries)
```

Do **not** unzip or decompile `cats.jar` into `cats/` — that folder is HART panels/scripts. See [`AGENTS.md`](AGENTS.md).

The layout deploy and the Pi and Windows host scripts live in [`tools/hosts/`](../tools/hosts/) (ADR-007 amendment 2026-11-12). `cats/scripts/sync_hart_package.sh` is a wrapper that runs `tools/hosts/sync_hart_package.sh`. The deploy still installs the host scripts at `cats/scripts/pi/` and `cats/scripts/windows/` inside the package, as the hosts expect.

## Bindings from hart panel

| File | Use in Designer |
|------|-----------------|
| [`data/occupancy_bindings.csv`](data/occupancy_bindings.csv) | Block → occupancy sensor userName |

## Decisions (Accepted)

- JMRI: **current** host (**5.16**, the newest CATS 3.2 supports)
- CTC throws: **CATS**
- Digicon desks: **generated from the schematic** since the CATS cut-over (ADR-023); **start here:** [`wiki/pipelines/cats-panels.md`](../wiki/pipelines/cats-panels.md)
  ```bash
  make desks   # writes HART_CTC.xml and HART_ABS.xml (all three levels)
  ```
  - Plant map: [`docs/ctc/DIGICON_SCHEMATIC.md`](../docs/ctc/DIGICON_SCHEMATIC.md)
- Check: `make panels CHECK=1` (the desks are byte-checked against a rebuild and against the approved fingerprints)

## Install + run (macOS)

CATS **must** be copied into your JMRI folder (`cats.jar` next to `jmri.jar`). Running it from this repo alone fails with `Could not find or load main class cats.apps.Crandic`.

```bash
# once:
./tools/cats/fetch_cats_3.2.sh          # if needed
./tools/cats/install_into_jmri.sh       # → /Applications/JMRI

# each session (no sudo):
#   PanelPro — edit/store JMRI tables and connections, then quit.
#   CATS    — loads the same profile tables.xml, then the Digicon XML.
# Never run both on the same profile; never Store tables with CATS open.
./cats/scripts/launch_cats.sh
# Digicon XML is auto-opened (default: cats/panels/HART_CTC.xml)

./cats/scripts/launch_designer.sh       # optional polish only
```

### macOS Local Network (MQTT / agent launches)

Agent-launched JMRI inherits **Cursor**’s Local Network permission. PanelPro often never shows up in that list — ignore that.

**Fix:** System Settings → Privacy & Security → Local Network → **Cursor** on, then **restart Cursor** and relaunch CATS. After that, `./cats/scripts/launch_cats.sh` (direct) gets MQTT.

Fallback if Cursor is still blocked: `CATS_LAUNCH_VIA=terminal`.

`readelf` warnings on macOS from `cats.csh` are harmless ARM probes.

## Authority rule

**CATS** commands turnouts/routes in CTC sessions. Layout Editor stays view / local (no dual-command).

Do **not** save CATS-created SignalHead/Mast objects into JMRI tables (load-crash risk).
JMRI tables are owned by **PanelPro**: edit and Store there only. CATS refers to those beans by JMRI user names and must not redefine them (cats-users #2534).

## Guides

- **Dispatcher (CTC ops):** [`docs/ctc/DISPATCHER_GUIDE_CTC.md`](../docs/ctc/DISPATCHER_GUIDE_CTC.md) — how to be a dispatcher on the Digicon panel (routes, stacking, fleeting, call-on). Complements, does not replace, the JMRI USS lever guide at `jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md`.
- Manuals (after fetch): `tools/cats/release3.2/{DesignerManual,catsManual,ReadMe}.pdf`
- Site: [User Guides](http://cats4ctc.wikidot.com/main:userguides)
