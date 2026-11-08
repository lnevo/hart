# Draft CV changes: match CSX 2738 to CSX 2121

**Draft for the owner's review. Nothing here has been programmed.** The goal is that
2738 runs at 2121's speed at every throttle step and has the same momentum.

## What to change on 2738 (Soundtraxx MC2H104P9)

| CV | Now | Draft | Why |
|---|---:|---:|---|
| 25 Speed Table Selection | 0 | **16** | 0 is "Disabled, Speed Curves not used"; 16 is the User Defined Speed Table (2121 uses 16) |
| 29 | 34 | **50** | sets bit 4 so the speed table is used; same value as 2121 |
| 67 to 94 speed table | 9, 18, 27 ... 255 | see below | the measured fit to 2121's speed curve |
| 3 acceleration | 0 | **26** | 2121's value |
| 4 deceleration | 0 | **24** | 2121's value |
| 2, 5, 6 | 0, 0, 0 | leave | 2121 has CV2 = CV5 = CV6 = 0 as well |
| 66, 95 trim | 128 | leave | same as 2121 |

### Speed table (CV67 to CV94)

Calculated by `propose_table.py` from the measured curves:

```
12, 27, 50, 73, 94, 115, 135, 146, 155, 165, 174, 179, 184, 190,
191, 191, 191, 191, 191, 191, 191, 191, 191, 191, 191, 191, 191, 191
```

For comparison, 2121's own table:

```
0, 26, 51, 73, 92, 110, 126, 140, 153, 165, 175, 185, 193, 199,
199, 199, 199, 199, 199, 199, 199, 199, 199, 199, 199, 199, 199, 199
```

The two are close (within about 5 to 10 units) from entry 3 upward, which is a good
sign that the decoders respond alike. They differ at entry 1 (12 against 26) and the
top (191 against 199).

**Two options**

1. **Use the calculated table.** Built from measurements, but assumes entry k acts at
   throttle step 126k/28 and the follower's pre-change drive was proportional to the step.
2. **Copy 2121's table to 2738.** Simpler. The result is probably within a few percent
   mid-range, with 2738 a little quicker at the very bottom.

Either way, re-run the profile afterwards. The measurement takes about 45 minutes per
loco (steps 8 to 126).

## What to check before programming

- Momentum: both are Soundtraxx, but the scale of CV3/CV4 on the MC2 and the Tsunami2
  has not been confirmed from the decoder definitions. After programming, compare
  start and stop distances at a mid step. 2121 also has a momentum override mapped to a
  function (Extended Function Map Momentum Override = 14); leave that as it is.
- Programming: the owner does not want to program on the main while other engines are
  on the track, unless that proves necessary. Plan the writes for the programming track.
- Speeds below step 8 were not measured. The first table entry (12) is extrapolated.
- A roster re-read after programming keeps the repo and roster in step.
