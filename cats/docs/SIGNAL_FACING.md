# Digicon signals + existing JMRI MQTT masts

## Facing (West Yard sheet)

Panel lamps (`SECSIGNAL` / `PANELSIGNAL`) tip **into** the named BLOCK on that edge.

| Edge | `SIGORIENT` |
|------|-------------|
| LEFT | RIGHT |
| RIGHT | LEFT |
| TOP | BOTTOM |
| BOTTOM | TOP |

| Type | Heads | Use |
|------|-------|-----|
| `LAMP1` / single | 1 | Yard / stub — Stop / Approach / Clear |
| `LAMP2` / double | 2 | Main / CP |
| `LAMP3` / triple | 3 | High-speed exits |

SoR wire: `cats/scripts/wire_hart_sheet_west_yard2.py` → `SIGNAL_DEFS`  
Plan: `cats/data/signal_mast_plan.csv`

---

## How to attach Digicon to an **existing** JMRI mast

Do **not** recreate or retype the JMRI Signal Mast. Leave its systemName / MQTT topic alone.

### Prerequisites (stock JMRI — already true for mast 464)

- MQTT Signal Mast exists, e.g.  
  `IF$mqm:AAR-1946:SL-1-high-abs($464)`  
  userName `Brick East Main West`  
  topic `track/signalmast/464` (from `($464)`)
- Mast aspects are AAR names: **Clear**, **Approach**, **Stop** (Restricting optional/disabled)

### Digicon-only steps

1. **Name match** — Digicon `SECSIGNAL` text = JMRI mast **userName** exactly  
   (CATS looks up `getSignalMast(name)` by userName, then systemName).

2. **Panel heads** — `SIGPANTYPE` / `LAMP1|2|3` for Digicon look only (can differ from field head count).

3. **Aspect name bridge** — stock Digicon `PHYSIGNAL` templates (`single` / `double` / `triple`) call  
   `setAspect("R281"|"R285"|"R292"|…)`.  
   AAR masts reject those. Add a small `SIGNALTEMPLATE` that remaps AppearanceKeys to AAR names, e.g. `aar-single`:

```xml
<SIGNALTEMPLATE TEMPLATEKIND="Lamp" TEMPLATEHEADS="2" TEMPLATENAME="aar-single"
  R281="Clear" R285="Approach" R292="Stop"
  …all other IndicationNames → Clear|Approach|Stop…>
  <ASPECTMAP
    R281="green|off" R285="yellow|off" R292="red|off" … />
</SIGNALTEMPLATE>

<SECSIGNAL>
  Brick East Main West
  <PANELSIGNAL SIGLOCATION="…" SIGORIENT="…" SIGPANTYPE="LAMP2" />
  <PHYSIGNAL>aar-single</PHYSIGNAL>
</SECSIGNAL>
```

4. **Authority**
   - **CATS drives aspects** (this layout): omit `HOLD_ONLY`. No route → CATS sets **Stop**; route → Approach/Clear. Field need not support Held/Unheld.
   - **Field drives aspects**: `HOLD_ONLY="true"` on that template’s `ASPECTMAP`. CATS only Held/Unheld; Digicon paints from MQTT. Only works if the field honors Hold **or** always publishes Stop when idle.

### What Aaron provided vs what we used

| Piece | Needed? | Notes |
|-------|---------|--------|
| Name = userName bind | **Yes** | Stock CATS behavior |
| `cats-masts` / `cats-virtual` signal system | **No** | Would retype the mast to R-code aspects; broke LE load here; wrong MQTT vocabulary for AAR field |
| Recreate MQTT mast | **No** | Existing AAR mast + topic was fine |
| `aar-single` AppearanceKey remap | **Yes** | The real gap between Digicon R-codes and AAR Clear/Approach/Stop |
| Hold only | **Optional** | Nice for field→Digicon listen; wrong if field ignores Held/Unheld |

Aaron’s screenshots correctly showed: bind by name, and CATS speaks rule-code aspects. His `cats-virtual` mast is one way to make JMRI speak those codes. For an **existing AAR mast**, keep the mast and remap Digicon → AAR names instead.

### Brick 464 (current)

- Digicon name `Brick East Main West` @ Brick east main face  
- `LAMP2` + `aar-single` (top follows Clear/Approach/Stop; bottom `off` until a 2-head JMRI mast exists)  
- CATS owns aspects (no Hold only)  
- **Stub routes:** Digicon Restricting (no next signal) maps to **Approach** on `aar-single` for MQTT; Digicon panel color uses `COLORDEFINITION RESTRICTING` (yellow, same as Approach) — stock Designer had Restricting=`-65536` identical to Stop, so every RES_* OS lamp looked stuck red

**CTC opposing faces (not a bug):** lining SW100 west only opens the frog. Digicon still grants **one direction of authority**. Eastbound green on `Brick West Yard 1/2` with westbound red on `Brick East Main West` means an eastbound route is active (or was); the opposing face is held by `CONFLICTINGSIGNALLOCK`. Empty track does not clear both ways. Cancel the eastbound route, then request from **Brick East Main West** for westbound (into W-Y stubs expect Restricting→Approach, not Clear).

**W-1 / W-2 spur ends:** Digicon “Joins to adjacent track” unchecked on the west faces is encoded as BLK cuts (`wire_hart_sheet_west_yard2.py`): spur tip | mid-spur gap | anon lamp mate | OS101 lamp. That marks the yards as dead-end stubs for aspect search.

### Plane East East Main Ext (2 virtual heads → MQTT) — POC

Lower Plane face on the **normal route** (SW102 closed → East Main Ext) @ `(9,8) RIGHT`.

- Digicon name / JMRI userName: **`Plane East East Main Ext`**
- JMRI: Virtual heads `IH465` / `IH466` + SignalHeadSignalMast  
  `IF$shsm:cats-masts:cats-virtual-2(IH465)(IH466)`
- Head systemNames use **LCOS packed addresses** (same family as mast `464`):
  `displayNode*100 + UID` per `LCOS_ESP32_MQTT_Client/mqtt_serial.h` / Public API UID Map
  (Signal 0..15 = UID 32..47). Strip `signalhead/` + optional `IH` → `465` / `466`.
- Digicon `PHYSIGNAL` = stock `double` (native R-codes; requires `cats-masts` signal system installed)
- Publish head colors: `jmri/scripts/mqtt_signalhead_publisher.py` → `track/signalhead/IH465|IH466`
- POC pair: **one** MQTT Signal Mast (`464` / Brick East Main West) + **one** head-based mast (this)
- Do not add a second Plane mast (Plane North Brick was removed)
