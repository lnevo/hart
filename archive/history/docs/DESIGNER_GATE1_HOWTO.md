# Gate 1 in CATS Designer — beginner how-to

You do **not** need to learn all of Designer. This is only Brick → OS Brick-Plane → Plane.

Official manual (full): [`DesignerManual.pdf`](DesignerManual.pdf)  
Geometry checklist: [`GATE1_BRICK_PLANE.md`](GATE1_BRICK_PLANE.md)

## 0. Start Designer

```bash
cd /Users/lnevo/Panel
./cats/scripts/launch_designer.sh
```

A blank grid should appear (or an empty CTC window). Designer is already installed next to JMRI.

**Tip:** Keep this doc + the cheat-sheet table (section 6) open beside Designer.

## 1. Mental picture (what you are drawing)

West → east on **one horizontal row** (do not stack bands):

```
OS Main West ═══[ OS 1 LH ]═══ OS Brick-Plane ═══[ OS 5 ]═══ OS East Main Ext
                  ╲
                   OS 3 (yard)
```

Rules that matter:

- **OS Brick-Plane** = straight track east of Brick (continuing route).
- Yard / OS 3 = the **other** leg of the Brick turnout (down or diagonal).
- Do **not** put 100–102 on a slash that runs into the Plane plant throat.

## 2. How to *draw* (this is the whole trick)

Designer is **not** freehand. You do **not** drag a pencil. You:

1. **Click a grid cell** → it gets a **red frame** (that’s the cursor).  
   Arrow keys also move the cursor.
2. Menu **Details → Tracks**.
3. A popup shows **six track pieces** (pictures + checkboxes), e.g.:
   - horizontal ──  
   - vertical │  
   - diagonals ／ ＼  
   - (combinations for turnouts)
4. **Check** the piece(s) you want in that cell.
5. Click **Accept**.
6. Click the **next cell** to the right → **Details → Tracks** again → check horizontal → **Accept**.
7. Repeat across the row.

That’s drawing.

### Gate 1 sequence (cell by cell)

Start near the left, middle row. Expand the grid if needed: **Edit → Insert Column After** / **Insert Row Below**.

| Step | Cell action | Check in Details→Tracks |
|------|-------------|-------------------------|
| 1–3 | Three cells in a row | **Horizontal** only → OS Main West |
| 4 | Next cell (Brick) | **Horizontal** + a **diagonal** (＼ or ／) so it looks like a LH turnout; continuing = east |
| 5 | Cell below/diagonal from Brick | Track that continues the diverge → toward OS 3 |
| 6–8 | Three cells east of Brick on the main | **Horizontal** only → OS Brick-Plane |
| 9 | Next cell (Plane) | **Horizontal** + diagonal (plant) |
| 10–11 | Two cells east | **Horizontal** → OS East Main Ext |

**Turnout cell** = one cell with **two** track pieces checked (horizontal + slash). That’s how Digicon “draws” a switch.

**Red track** after Accept = normal until you name the block (section 3).

Undo a cell: select it → clear via **Edit** (or uncheck tracks in Details→Tracks → Accept).

**Do not** hand-edit XML. If it’s wrong, clear the cell and Details→Tracks again.

## 3. Name blocks (required or CATS won’t show them)

For each stretch of track:

1. Click a cell that belongs to that block.
2. **Details → Track Ends**
3. On the edge that ends that block, check **Block Boundary** (both sides of a boundary need it).
4. **Define Block** (or equivalent button on that edge):
   - **Block Name** = exact string from the cheat sheet (section 6)
   - **Discipline** = **CTC**
5. Repeat until every Gate 1 track is white/grey (named), not red.

## 4. Occupancy (so CATS turns red from MQTT)

Still in **Define Block** / block detector fields for that block:

| Block name | Occupied sensor (JMRI userName) |
|------------|----------------------------------|
| OS Main West | `Block 2-1` |
| OS 1 | `Block 4-2` |
| OS 3 | `Block 4-1` |
| OS Brick-Plane | `Block 4-6` |
| OS 5 | `Block 4-5` |
| OS East Main Ext | `Block 4-7` |

If Designer asks for JMRI prefix / address, prefer binding by **user name** when offered. MQTT prefixes `M2S` / `M2T` are already on the HART JMRI profile.

After save, you can also run:

```bash
python3 cats/scripts/jmri_to_cats_digicon.py --wire-only cats/panels/HART.xml
```

That fills occupancy from hart without changing your drawn track.

## 5. Switch points (Brick + Plane)

On the Brick turnout cell:

1. **Details → Track Ends** → edge with **two** tracks → **Switch Points** (or similar).
2. Set the **normal / continuing** route to the **east horizontal** into OS Brick-Plane (not the yard diverge).
3. Command turnout: **`M2T408`** (Switch 1).

On Plane:

- Continuing / normal = through toward OS East Main Ext as you intend.
- Command: **`M2T410`** (Switch 5).

OS 3 points (if separate): **`M2T409`**.

Skip signals for Gate 1.

## 6. Cheat sheet (copy exactly)

| Digicon role | Block name (type exactly) | Occupancy | Turnout |
|--------------|---------------------------|-----------|---------|
| Approach | `OS Main West` | `Block 2-1` | — |
| Brick plant | `OS 1` | `Block 4-2` | `M2T408` |
| Yard diverge | `OS 3` | `Block 4-1` | `M2T409` |
| Straight | `OS Brick-Plane` | `Block 4-6` | — |
| Plane | `OS 5` | `Block 4-5` | `M2T410` |
| East of Plane | `OS East Main Ext` | `Block 4-7` | — |

## 7. Save

**File → Save As** →  

`/Users/lnevo/Panel/cats/panels/HART.xml`

(Overwrite the interim Gate 1 file when you are happy.)

Optional magnet copy: `HART_magnet.xml` (no MQTT) — or save once and use `--wire-only` only on `HART.xml`.

## 8. Run CATS and check

```bash
python3 cats/scripts/jmri_to_cats_digicon.py --wire-only cats/panels/HART.xml
python3 cats/scripts/validate_cats_panel.py cats/panels/HART.xml
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh
```

Open **Dispatcher Panel** (not the CTC splash).

Accept:

1. Occupy / force `Block 4-6` → red on **horizontal** 100–102 only.  
2. `Block 4-2` → red on Brick plant.  
3. Yard path is clearly the diverge, not the main.

## If you get stuck

| Problem | What to do |
|---------|------------|
| All track red | Blocks not named — section 3 |
| Blank Digicon / ClassCast | You edited XML by hand or imported a broken fragment — redraw in Designer; don’t splice XML |
| No occupancy colors | Run `--wire-only`; launch with `CATS_LAUNCH_VIA=terminal` (Local Network) |
| Looks like Armstrong again | You opened the old file — File→New and draw Gate 1 only |
| Don’t know which menu | Search the PDF for “Track Ends” / “Switch Points” — [`DesignerManual.pdf`](DesignerManual.pdf) §6 and §9 |

## Suggested first session (20 minutes)

1. File → New  
2. Draw only: horizontal + one LH + straight + one plant + east stub  
3. Name the six blocks  
4. Save as `HART.xml`  
5. `--wire-only` + launch CATS  
6. Fix occupancy / normal route before adding more plants  

Gates 2–5 come later ([`GATE2_PLUS.md`](GATE2_PLUS.md)).