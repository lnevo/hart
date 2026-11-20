# Turnout state SoR (HART Digicon)

## Rules

1. **Live Digicon state follows FB** for every turnout **except 116–119**.
2. Digicon `SELECTEDREPORT` and `ROUTECOMMAND` always share the **same**
   close/throw polarity. Remapping report-only to chase MQTT makes frogs look
   right and **reverses commands**.
3. **112 / 114 / 115 tip SoR (dispatcher):**
   - **112** THROWN = OS Barn (BOTTOM); CLOSED = through OS110 (LEFT)
   - **114** THROWN = OS K-2 (BOTTOM, default); CLOSED = OS McKeesport (RIGHT)
   - **115** THROWN = K-1 (TOP); CLOSED = OS McKees Rocks (RIGHT) — confirmed good
4. If Digicon shows the **wrong direction**, fix **that one switch only** in
   `jmri/layouts/hart/data/switch_legs.csv` (closed and thrown legs) or
   `switches.csv` (`cats_inverted`), rewire, reload. See
   [`wiki/pipelines/switch-facts.md`](../../wiki/pipelines/switch-facts.md). Do **not** publish MQTT or command JMRI turnouts to “fix” paint.
5. Agents / `launch_cats.sh` must **not** throw field points.
6. **Appearance → Refresh Screen** = JMRI → Digicon (safe). **Refresh Layout** =
   Digicon → JMRI — do not use it to fix boot paint.
7. **Load safety:** CATS is stock, so a turnout report during panel load can kill
   `RREventManager` and freeze occupancy until CATS restarts. Launch does **not** write MQTT.
8. **No boot fill from MQTT retain.** State arrives from live LCOS reports. If frogs look wrong, use
   **Appearance → Refresh Screen** in Digicon.

## Stock CATS load race

On stock CATS, the session log can show `Uncaught Exception … [RREventManager]`
at `PtsVitalLogic.setSelectedTrack` and occupancy freezes until relaunch.

## Diagnose (read-only)

```bash
python3 jmri/layouts/hart/scripts/seed_default_thrown_turnouts.py --diagnose
```

## Digicon NORMAL (current panel)

| Switch | Digicon close (NORMAL) | Digicon throw | Notes |
|--------|------------------------|---------------|-------|
| 100 | LEFT | BOTTOM (100–102) | continuing = THROWN |
| 102 | BOTTOM (Track East Ext) | RIGHT (OS Scale) | |
| 112 | LEFT (OS110 ↔ OS East Lead) | BOTTOM (OS Barn) | THROWN = OS Barn |
| 114 | RIGHT (OS McKeesport) | BOTTOM (OS K-2) | THROWN default = OS K-2 |
| 115 | RIGHT (OS McKees Rocks) | TOP (OS K-1) | confirmed good |

At rest 112/114/115 are typically JMRI/MQTT `THROWN` — Digicon throw frog
matches the field. Commands use the same map.

Layout Editor `continuing` is JMRI `Turnout` state, not 1/2 Closed/Thrown:

| XML | Sense | Frog |
|-----|--------|------|
| `2` | CLOSED | Closed = B / through (114/115 → K stubs) |
| `4` | THROWN | Thrown = B / through |
| `1` | UNKNOWN | both legs drawn; LE ignores table state |

114/115/111/113/117 (idents TOL29, TOR36, TO111, TO113, TO117) stay at **2** in the generated panel (`build_layout_le.py`). Do not write `1`. `audit_panel_contracts.py` (`audit_generated_settings`, run by `check.sh` and the deploy audit) fails on any other value; it also pins `blockrouting="yes"` and the disabled aspects of AAR 2-head masts.

OS McKees Rocks/OS McKeesport stubs are plain (no BLK↔BLK gaps).
