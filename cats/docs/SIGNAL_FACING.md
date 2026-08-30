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
| `LAMP1` / single | 1 | Yard / stub / single-route connector — Stop / Approach / Clear |
| `LAMP2` / double | 2 | Main / CP home — high vs medium or restricting (two speed classes) |
| `LAMP3` / triple | 3 | High + medium + slow at one mast (none on HART Master today) |

SoR wire: `cats/scripts/wire_hart_master4.py` (`SIGNAL_DEFS` / occupancy ANCHORS)  
Plan: `cats/data/signal_mast_plan.csv`

---

## How to attach Digicon to an **existing** JMRI mast

Mast 2L used to be this MQTT-mast case (`track/signalmast/432`). It is now Virtual heads + SHSM like the others (`IH438`/`IH439`). Keep the notes below only if you attach another leftover MQTT mast.

Do **not** recreate or retype the JMRI Signal Mast. Leave its systemName / MQTT topic alone.

### Prerequisites (stock JMRI — already true for mast 432)

- MQTT Signal Mast exists, e.g.  
  `IF$mqm:AAR-1946:SL-2-high-abs($432)`  
  userName `Mast 2L`  
  topic `track/signalmast/432` (from `($432)`)
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
    R281="green|red" R285="yellow|red" R292="red|red" … />
</SIGNALTEMPLATE>

<SECSIGNAL>
  Mast 2L
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

### Mast 2L

- Digicon name `Mast 2L` @ Brick east main face  
- `LAMP2` + `double` — same Virtual-head + AAR-1946 SHSM path as the other homes  
- Packed heads `IH438` / `IH439` on C3-OU3-1 / C3-OU3-2 (`track/signalhead/IH438`, `track/signalhead/IH439`)  
- JMRI does **not** publish `track/signalmast/432` (old MQTT mast retired; that topic collided with LCOS status for Plane `IH432`)

**Do not use Digicon `SPUR="true"` on Brick SW100/101** without a coded switch-unlock. Spur makes only the Normal route clear `CONFLICTINGSIGNALLOCK` on the points; that lock is in `GUISwitchLocks`, so the dispatcher cannot throw the turnout (especially once lined reverse). Westbound “priority” needs a different approach than Spur on this plant.

**CTC opposing faces:** lining the switch only opens the frog. Digicon still grants **one direction of authority** per route. An active eastbound route holds the opposing face via `CONFLICTINGSIGNALLOCK` until cancelled. Into W-Y stubs expect Restricting, not Clear.

**OS W-1 / OS W-2 spur ends:** Digicon “Joins to adjacent track” unchecked on the west faces is encoded as BLK cuts (`wire_hart_master4.py`): spur tip | mid-spur gap | anon lamp mate | OS101 lamp. That marks the yards as dead-end stubs for aspect search.

### Digicon → virtual heads + SHSM (hart-aar two-head, AAR-1946 dwarfs)

All West Yard Digicon lamps use Virtual Signal Heads + SignalHeadSignalMasts: two-head homes are custom **`hart-aar` `SL-2-digicon`** (Clear G/R, Approach Y/R, Medium Clear R/G, Medium Approach R/Y, Stop R/R), dwarfs stay stock **AAR-1946 `SL-1-low`**. SML uses AAR speeds (Clear=Normal, Approach/Medium=Medium, Stop=Stop; dwarfs Slow Clear / Restricting / Stop).

**Why not stock `SL-2-high-abs`:** its aspect mapping for a destination at *Approach* only offers *Advance Approach* / *Approach Medium* — aspects these two-lamp heads cannot display (they were in `disabledAspects`) — so SML pinned every mast behind an Approach at **Stop** (the "always red" family). `hart-aar` (in `cats/resources/signals/hart-aar/`, deployed to each JMRI user-files `resources/signals/` by `sync_hart_package.sh`) keeps AAR aspect names but chains as 3-aspect ABS: dest Approach-or-better → Clear (Medium Clear when the route diverges), dest Stop/Restricting/Slow Clear → Approach (Medium Approach diverging). Dwarf `SL-1-low` chains fine unchanged (Clear→Slow Clear, Approach/Stop→Restricting).

Every disc, OU board (including 12V motors / relays / spares), and G/Y/R port: [`docs/wiring/README.md`](../../docs/wiring/README.md#digicon-heads-and-ou-boards).

Princess east exits are **2-head** (main vs OS K-1/OS K-2 restricting). Balloon intermediates **Mast 2035** / **Mast 2036** (was 115R / 114R) stay **SL-1-low** (Slow Clear / Restricting / Stop — Restricting is yellow). All other Digicon **LAMP1** masts use `SL-1-low` dwarfs on Layout Editor (T6, OS S-R, OS 31, OS W-1/OS W-2, OS K-1/OS K-2). Packed IDs: Mast 2036 `IH1133` / Mast 2035 `IH1134`; east Princess dwarfs `IH1136` (40LA) on C11; west Princess `IH143` (38LA) on C1.

- Packing: `displayNode*100 + UID` (`UID = 32 + signal_index`) — see `mqtt_serial.h`
- Appearances: custom `hart-aar` `SL-2-digicon` two-head / stock `AAR-1946` `SL-1-low` dwarfs (not `cats-masts`)
- Digicon `PHYSIGNAL`: templates remapped to AAR names (`cats/scripts/aar_aspect_bridge.py`); CATS CTC is `HOLD_ONLY`; CATS ABS SECSIGNAL names are unbound (`unbind_abs_from_jmri_masts.py`) so SML owns LE
- Layout Editor facing: `cats/data/le_signal_boundaries.csv` → `python3 cats/scripts/apply_le_sml_facing.py` (`signalAMast` / `eastboundsignalmast`). Balloon A48 joins the east ends of the two loop blocks, so the mast named for its approach track must protect the opposite block: **OS McKeesport / `IH134` protects OS McKees Rocks and OS 39** (`westboundsignalmast`), while **OS McKees Rocks / `IH141` protects OS McKeesport and OS 37** (`eastboundsignalmast`). CATS display locations and physical IH wiring remain OS McKeesport at (45,7) TOP and Rocks at (45,6) BOTTOM; do not swap those outputs to correct the Layout Editor facing. 114/115 C homes face west (CATS SIGORIENT LEFT, LE deg 270); dest WME `111a` when 113 is normal, OS East Lead when 113 is reverse. OS K-1 / OS K-2 dwarfs dest the same westbound next masts (`111a` / OS East Lead), not the opposing 113a/113b faces. South line (Plane EME ↔ OS Barn D) dest each other across OS East Main Ext — not East End OS Main West.
- SML dests: **native** — discovered by Layout Editor (`cats/scripts/run_sml_discover.sh`, one-shot) and stored in `tables.xml` with `useLayoutEditor=yes`; JMRI re-paths them on every load. The old hand-pair injector `apply_sml_cats_pairs.py` is retired (its `PAIRS` list is kept as a regression oracle for `validate_le_signalling.py --dests`); the startup Jython re-apply is removed from all profiles. Runtime criteria can be inspected with `jmri/layouts/hart/scripts/dump_sml_criteria.py` (one-shot, same harness env as `discover_sml.py`). CATS ABS is the visual reference only — it must not `setAspect` on JMRI masts.
- Plant dests (CATS MQTT compare): OS Barn D (lower west) dests OS 33 when 117 is closed (east into OS Main East), not back across OS East Main Ext. 117b dests Plane EME when 117 is closed (westbound). OS East Lead dests 117b only when 112 is thrown (diverge to OS Main East). OS 33 dests 113a when 112 is thrown. OS 31 dests 113a only when 110 is thrown **and** 112 is closed (ladder into OS East Lead); 110 closed → Stop. 111 through (closed): 111a dests Brick, West OS Main West dests 113b; 111 thrown → both Stop.
- Ports + topics: `cats/data/signal_wiring.csv` (also updates `docs/wiring/LCOS_Layout_Inventory_v85.xlsx` DNOU8)
- Mast index: `cats/data/signal_head_plan.csv` / enriched `signal_mast_plan.csv`
- Rebuild heads: `python3 cats/scripts/build_hart_signal_heads.py`
- Signal heads: `jmri/scripts/mqtt_signalhead_publisher.py` listens to SHSM / SML
  and **publishes** Virtual-head appearances JMRI → MQTT (`track/signalhead/IH###`)
  so LCOS sees SML / Digicon state. JMRI’s MQTT connection is the transport;
  no mosquitto CLI, no retain-paint of heads, no `setAppearance`.
- LE `signalmasticon`s use AAR schematic GIFs (stock JMRI). Deploy via `sync_hart_package.sh` (full `tables.xml`).

**Mast 6LB** @ `(9,8) RIGHT` is now `IH432`/`IH433` (was POC `IH465`/`IH466`).
