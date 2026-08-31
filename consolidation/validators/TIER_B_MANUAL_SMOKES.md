# Tier B — manual smokes (reference)

Checklist for when the consolidation tree is authoritative and layout hosts are updated from it.

> **During consolidation build (D12):** documentation only — no layout-host sync from this workspace.

## Pipeline 5 — CATS Masters

- [ ] Load `HART_Master_CTC_hold.xml` in CATS — routes work; signals **HOLD_ONLY**
- [ ] Load `HART_Master_ABS_hold.xml` — SML paints aspects on SECSIGNAL cells
- [ ] `python3 cats/scripts/validate_cats_panel.py` PASS
- [ ] Do **not** run USS CTC or Dispatcher System from inside CATS simultaneously

## Pipeline 6 — USS CTC

- [ ] USS 20-column machine loads in PanelPro (see `jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md`)
- [ ] Mutually exclusive with live CATS CTC session
- [ ] `python3 jmri/layouts/hart/scripts/ctc_logic_smoke.py` if regen touched CTC data

## Pipeline 7 — Dispatcher System

- [ ] Graph baseline: **91** sections / **688** transits / **1508** traininfo (or documented delta in STATUS)
- [ ] Stage 1 CreateTransits not required every deploy — only after graph edits
- [ ] Facing overlay jython still loads (`hart_dispatcher_startup.py`)

## Pipeline 9 — LCOS / MQTT

- [ ] Broker: subscribe `track/signalmast/#` — non-empty retained masts after bridge connect
- [ ] SET on `track/signalhead/<packed>` gated when mast topic absent
- [ ] Windows bridge **foreground** (`serial_to_mqtt.py --verbose`)
- [ ] Event **125** replay after master RAM wipe (known gap — D10 spec only until D10b)

## Cross-cutting — MQTT mimic

- [ ] PanelPro `mqtt_signalhead_publisher` running if testing aspects
- [ ] `python3 cats/scripts/lcos_mqtt_mimic.py` for Digicon QA (optional)

## Deploy

```bash
./cats/scripts/sync_hart_package.sh --pi    # add --win / --all when needed
```

Record smoke date in live `wiki/STATUS.md` when railroad state or deploy artifacts changed.
