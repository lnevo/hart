# Turnout state SoR (HART Digicon)

## Rules

1. **Live Digicon state follows FB** for every turnout **except 116–119**.
2. Digicon `SELECTEDREPORT` and `ROUTECOMMAND` always share the **same**
   close/throw polarity. Remapping report-only to chase MQTT makes frogs look
   right and **reverses commands**.
3. **112 / 114 / 115 tip SoR (dispatcher):**
   - **112** THROWN = Barn (BOTTOM); CLOSED = through OS110 (LEFT)
   - **114** THROWN = McKeesport (BOTTOM, default); CLOSED = K-2 (RIGHT)
   - **115** THROWN = Rocks (TOP); CLOSED = K-1 (RIGHT) — confirmed good
4. If Digicon shows the **wrong direction**, flip **that one switch only** in
   `cats/scripts/wire_hart_sheet_west_yard2.py` `PLANTS` (NORMAL leg), rewire,
   reload. Do **not** publish MQTT or command JMRI turnouts to “fix” paint.
5. Agents / `launch_cats.sh` must **not** throw field points.
6. **Appearance → Refresh Screen** = JMRI → Digicon (safe). **Refresh Layout** =
   Digicon → JMRI — do not use it to fix boot paint.
7. **Load safety:** `install_into_jmri.sh` overlays known-good
   `cats-pts-nullguard.jar` so stock’s early-SELECTEDREPORT NPE cannot kill
   `RREventManager` (occupancy). Launch does **not** write MQTT.
8. **Boot state from MQTT retain (standard on Mac / Pi / Windows):** CATS
   profile Start Up runs `jmri/layouts/hart/scripts/apply_maintain_mqtt.py`
   after `tables.xml`. Script **reads** broker retain only (never publishes):
   sensors via `setOwnState`; non-TWOSENSOR turnouts via `newKnownState`;
   TWOSENSOR plants via `setInitialKnownStateFromFeedback()`. Auto-picks
   MQTT host (`MQTT_HOST` / JMRI connection / `127.0.0.1` /
   `192.168.137.2` / `minipc-e5h6x.local`). Alias:
   `apply_mqtt_retain_at_startup.py`. Rebuild tables with
   `python3 jmri/scripts/extract_hart_mqtt_tables_from_linear6.py`.
   If Digicon frogs still look wrong: **Appearance → Refresh Screen**.

## Stock CATS load race

Without the overlay, the session log shows `Uncaught Exception … [RREventManager]`
at `PtsVitalLogic.setSelectedTrack` and occupancy freezes until relaunch.

## Diagnose (read-only)

```bash
python3 cats/scripts/seed_default_thrown_turnouts.py --diagnose
```

## Digicon NORMAL (current panel)

| Switch | Digicon close (NORMAL) | Digicon throw | Notes |
|--------|------------------------|---------------|-------|
| 100 | LEFT | BOTTOM (100–102) | continuing = THROWN |
| 102 | BOTTOM (East Main Ext) | RIGHT (Yard T1) | |
| 112 | LEFT (OS110 ↔ East Lead) | BOTTOM (Barn) | THROWN = Barn |
| 114 | RIGHT (K-2) | BOTTOM (McKeesport) | THROWN default = McKeesport |
| 115 | RIGHT (K-1) | TOP (McKees Rocks) | confirmed good |

At rest 112/114/115 are typically JMRI/MQTT `THROWN` — Digicon throw frog
matches the field. Commands use the same map.

K-1/K-2 stubs are plain (no BLK↔BLK gaps).
