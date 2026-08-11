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
- **Stub routes into W-Y:** Digicon indication is Restricting (no next signal). `aar-single` remaps `RES_*` → **Approach** for the AAR MQTT mast `464` (Restricting is disabled on that mast). Panel `COLORDEFINITION RESTRICTING` stays stock (same red as Stop unless you change it in Designer).

**Do not use Digicon `SPUR="true"` on Brick SW100/101** without a coded switch-unlock. Spur makes only the Normal route clear `CONFLICTINGSIGNALLOCK` on the points; that lock is in `GUISwitchLocks`, so the dispatcher cannot throw the turnout (especially once lined reverse). Westbound “priority” needs a different approach than Spur on this plant.

**CTC opposing faces:** lining the switch only opens the frog. Digicon still grants **one direction of authority** per route. An active eastbound route holds the opposing face via `CONFLICTINGSIGNALLOCK` until cancelled. Into W-Y stubs expect Restricting→Approach on `464`, not Clear.

**W-1 / W-2 spur ends:** Digicon “Joins to adjacent track” unchecked on the west faces is encoded as BLK cuts (`wire_hart_sheet_west_yard2.py`): spur tip | mid-spur gap | anon lamp mate | OS101 lamp. That marks the yards as dead-end stubs for aspect search.

### Digicon → virtual heads + SHSM (all faces except Brick East Main West)

All West Yard Digicon lamps except **`Brick East Main West`** (`aar-single` / MQTT mast `464`) use Virtual Signal Heads + `cats-masts` SignalHeadSignalMasts.

| Area | Radio → MQTT node | Parent board | Packed heads |
|------|-------------------|--------------|--------------|
| Plane + W-1 / W-2 | `4` | C4 | `IH432`–`IH437` |
| Barn / West Yard 117 | `013` → **13** | C1 | `IH1332`–`IH1338` |
| East End | `012` → **12** | C7 | `IH1232`–`IH1241` |
| Princess | `1` | D1 | `IH132`–`IH141` |

- Packing: `displayNode*100 + UID` (`UID = 32 + signal_index`) — see `mqtt_serial.h`
- Appearances: `cats-virtual` / `cats-virtual-2` / `cats-virtual-3` (1/2/3 heads)
- Digicon `PHYSIGNAL`: stock `single` / `double` / `triple` (native R-codes)
- Ports + topics: `cats/data/signal_wiring.csv` (also updates LCOS inventory DNOU8)
- Mast index: `cats/data/signal_head_plan.csv` / enriched `signal_mast_plan.csv`
- Rebuild: `python3 cats/scripts/build_hart_signal_heads.py`
- Signal heads: `jmri/scripts/mqtt_signalhead_publisher.py` paints Virtual heads
  from `track/signalhead/IH###` retain at boot (no publish on that pass), then
  listens for Appearance changes and **publishes** JMRI → MQTT so CATS / CATS ABS
  Digicon aspects reach LCOS. ABS-RO (`HOLD_ONLY`) still only Held/Unheld; field
  retain is the aspect SoR for those lamps.
- Do **not** put cats-virtual LE `signalmasticon`s on Windows tables (NPE); Digicon binds by userName

**Plane East East Main Ext** @ `(9,8) RIGHT` is now `IH432`/`IH433` (was POC `IH465`/`IH466`).
