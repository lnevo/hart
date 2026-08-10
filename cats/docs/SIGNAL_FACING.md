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
