# Block assignment in tables.xml

## What’s in tables.xml

### 1. Blocks table (global)

Blocks are defined under `<blocks class="jmri.configurexml.BlockManagerXml">` around lines 375–466. Each block looks like:

```xml
<block systemName="IB:AUTO:0001" length="0.0" curve="0">
  <systemName>IB:AUTO:0001</systemName>
  <userName>Block 4-1</userName>
  <permissive>no</permissive>
  <occupancysensor>Block 4-1</occupancysensor>
</block>
```

- **systemName** – JMRI internal id (e.g. `IB:AUTO:0001`). Auto-generated if you create a block from the panel.
- **userName** – Display name (e.g. `Block 4-1`). This is the name you see and the one to use when assigning layout elements.
- **occupancysensor** – Optional sensor name used for occupancy (often same as or derived from userName).

You currently have **Block 4-1** through **Block 4-8** (and `IB1` / AUTOBLK:1) defined here.

### 2. Layout elements (inside LayoutEditor)

- **Track segments** – `<tracksegment ident="..." connect1name="..." type1="..." connect2name="..." type2="..." ... class="...TrackSegmentXml" />`
- **Layout turnouts** – `<layoutturnout ident="..." type="LH_TURNOUT" ... />`

In your **tables.xml**, none of these layout elements have any attribute that references a block. So:

- The **Blocks** table defines which blocks exist (and their userName).
- The **layout** (track segments and turnouts) does **not** currently store “which block this belongs to” in the file.

So **tables.xml does not show where the block name is specified for a track segment** in your current file—that assignment isn’t present yet.

---

## How JMRI assigns blocks to layout elements

From JMRI docs:

- You assign a block to a **track segment** via:
  - **Block: Name** in the toolbar before drawing the segment, or  
  - **Edit Track Segment** → block name field.
- You can also assign blocks to **layout turnouts** (and level crossings).
- The name you enter is the block’s **user name** (e.g. `Block 4-1`). If that block doesn’t exist, JMRI can create it.
- Layout block usage is saved with the configuration. Only blocks with at least one layout element assigned are persisted as “in use.”

So the **block name for a track segment** is specified in the UI; when the panel is saved, JMRI must write that link somewhere in the XML.

---

## Where it is stored in XML (confirmed from mac_jmri2.xml)

**Confirmed:** JMRI stores the block on the **track segment** as the attribute **`blockname`** with the block’s **user name** (e.g. `Block 4-1`).

Example from your saved panel **mac_jmri2.xml** (segment F35026-S-0 assigned to Block 4-1):

```xml
<tracksegment ident="F35026-S-0" blockname="Block 4-1" connect1name="A192" type1="POS_POINT" connect2name="A170" type2="POS_POINT" dashed="no" mainline="yes" hidden="no" arc="yes" ... class="jmri.jmrit.display.layoutEditor.configurexml.TrackSegmentXml" />
```

So for each track segment (and layout turnout if JMRI uses the same attribute there), add **`blockname="Block X-Y"`** (or whatever block user name you use) to assign it to that block.

---

## (Obsolete) What you could do to get a precise sample

*No longer needed—format confirmed from mac_jmri2.xml (see above).*

---

## Summary

| Question | Answer |
|----------|--------|
| Does tables.xml indicate where the block name is specified for a track segment? | **Yes (now confirmed).** It’s the **`blockname`** attribute on `<tracksegment>` (value = block user name, e.g. `Block 4-1`). See mac_jmri2.xml. |
| Format for assigning a segment to a block | Add **`blockname="Block 4-1"`** (or the block’s userName) to that segment’s `<tracksegment ... />` in the panel XML. |
| Blocks table structure | Shown above: `<block systemName="..." length="0.0" curve="0">` with `<userName>Block 4-1</userName>` and optional `<occupancysensor>`. |

With the confirmed format (`blockname="Block 4-1"` on `<tracksegment>`), we can script adding block names to every track segment from your **layout_blocks.xlsx** block map (and layout turnouts too if JMRI uses the same attribute there).
