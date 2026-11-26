# Sensor numbering reference

This document describes the sensor system names and user names used in the panel (e.g. `mac_jmri_blocked.xml`) and how they are assigned by `apply_blocks_to_panel.py`.

**Order in the sensor table:** (1) Block occupancy, (2) Turnout feedback, (3) NX (Entry/Exit) boundary sensors, (4) any other sensors.

---

## 1. Block occupancy sensors (first range)

**Purpose:** One sensor per block for occupancy detection (layout blocks, dispatcher).

| Range | systemName | userName | Count |
|-------|------------|----------|--------|
| 1–N   | ISIS1 … ISIS*N* | Block Sensor *n* or **BS *&lt;turnout&gt;*** | N = number of blocks (e.g. 175) |

- **systemName:** ISIS1, ISIS2, … ISIS*N* (one per block in order).
- **userName:** For blocks that contain at least one layout turnout: **BS** followed by the turnout ident (e.g. **BS TOL35287**). For blocks with no turnouts: **Block Sensor** *n* (e.g. Block Sensor 42).
- Block and layoutblock elements reference these by the same userName (BS TOLxxx or Block Sensor N).

---

## 2. Turnout feedback sensors (second range)

**Purpose:** Two sensors per turnout for position feedback (TWOSENSOR). Normal = closed, Reverse = thrown.

| systemName   | userName pattern     | Turnout table |
|--------------|----------------------|---------------|
| ISIS(N+1), ISIS(N+2), … | *&lt;turnout&gt;* FB_N, *&lt;turnout&gt;* FB_R | sensor1 = *&lt;turnout&gt;* FB_R (reverse), sensor2 = *&lt;turnout&gt;* FB_N (normal) |

- **systemName:** Normal ISIS range immediately after block sensors: ISIS(N+1), ISIS(N+2), … (two per turnout; N = number of blocks).
- **userName:** Turnout roster name + `" FB_N"` (normal/closed) or `" FB_R"` (reverse/thrown).
- **feedback:** Each turnout is set to `feedback="TWOSENSOR"` with sensor1 = Thrown (reverse), sensor2 = Closed (normal).

---

## 3. NX (Entry/Exit) boundary sensors (third range)

**Purpose:** Boundary sensors for Entry/Exit pairs (dispatcher, auto-generate paths). Placed where blocks meet.

| Range   | systemName   | userName pattern | Meaning |
|---------|--------------|------------------|--------|
| 200+    | ISIS200 …    | See below        | Assigned in **sorted order by userName** (alphabetically). |

**userName patterns:**

| Type | userName | Example | Where |
|------|----------|---------|--------|
| End bumper | `NX <ident>` | NX EB269, NX EB265 | Positionable point type END_BUMPER; one sensor per bumper. |
| Anchor (block boundary) | `NX <ident>-E`, `NX <ident>-W` | NX A48-E, NX A48-W | Positionable point type ANCHOR where the two connected segments have different blocks; east and west boundary. |
| Turnout leg | `NX <turnout>-A`, `-B`, `-C`, `-D` | NX TOL35427-A, NX TOL35281-B | Layout turnout leg (A=throat, B/C=diverging/normal, D=double crossover) where the connected segment’s block ≠ turnout block. |

- **systemName:** NX sensors start at **ISIS200** (`NX_SENSOR_BASE` in the script) and increment (ISIS200, ISIS201, …) in the order of **sorted(userName)**.

---

## 4. Quick reference

| Sensor type        | systemName / range | userName pattern        | Order |
|--------------------|--------------------|-------------------------|-------|
| Block occupancy    | ISIS1–ISIS*N*      | Block Sensor *n* or BS *turnout* | 1 |
| Turnout feedback   | ISIS(N+1)… (after blocks) | *turnout* FB_N / FB_R | 2 |
| NX bumper          | ISIS200+           | NX *point_ident*        | 3 |
| NX anchor          | ISIS200+           | NX *point_ident*-E / -W | 3 |
| NX turnout leg     | ISIS200+           | NX *turnout*-A / -B / -C / -D | 3 |

---

## 5. Constants in code

- **Block sensors:** `ISIS{i}` for `i = 1 .. len(block_names)`; userName = `BS <turnout>` for blocks that have turnouts (from `turnout_to_block`), else `Block Sensor {num}`.
- **Turnout feedback:** systemName ISIS(N+1), ISIS(N+2), … (N = block count; two per turnout); userName `"<turnout> FB_N"`, `"<turnout> FB_R"`.
- **NX start:** First NX sensor index = N + 1 + 2×(number of turnout feedback sensors) so NX range follows block + feedback.
- **Document order:** Block sensors first, then turnout feedback sensors, then NX boundary sensors, so ranges do not overlap and the table is easy to read.
