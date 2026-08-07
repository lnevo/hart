# Block 101 and Block 114 (same spur?)

You noted these two blocks may should be the same block. In the layout XML:

- **Block 101**: Track from endpoint **EB297** to turnout **TOL35427** (throat). Segments: F35584-S-0, T-I-TOL35427.
- **Block 114**: Track between endpoints **EB295** and **EB296**. Single segment: F35582-S-0.

**Cause:** In `my_layout.xml`, **EB296** and **EB297** are both `END_BUMPER` at the **same coordinates** (200.44, 383.87), but they are **different positionable points**. So in the connectivity graph they are two separate vertices. That gives:

- One spur: EB295 — F35582-S-0 — EB296  
- Another spur: EB297 — F35584-S-0 — A254 — TOL35427  

So the layout has two end bumpers at the same location instead of one. To have a single block for that spur you can either:

1. **In Layout Editor:** Replace the two bumpers (EB296 and EB297) with a single endpoint and reconnect the track, then re-export and re-run the block script, or  
2. **In the panel XML:** Manually merge the two blocks (e.g. assign all segments from both blocks to one block and remove the other) if you want one block for that spur.

No change was made to block 101/114 in the script; the block list and `mac_jmri_blocked.xml` still have 101 and 114 as separate blocks until the layout or XML is edited as above.
