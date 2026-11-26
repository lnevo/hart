# Session 4 designs: items 4, 5 and 6 (drafts)

Status: drafts for the owner to choose from. Nothing here is published or deployed. Items are from the
[session 4 punch list](../SESSION4_PUNCH_LIST.md); the owner's parts (items 8 and 9) put the chosen signs, signals and
board up.

Every fact is read from a source file by `facts.py`; none is typed into a design. The outputs are in `out/`.

## Item 4: control point signs (one per interlocking, for a stick in the benchwork)

Eleven signs, from `jmri/layouts/hart/data/schematic/interlockings.csv` (name, level, switch numbers): Brick, Barn,
East End, Princess (staging); CP 107, CP 123, CP 127 (main); CP 201, CP 211, CP 217, CP 223, CP 225 (upper). The
level names Staging, Main and Upper are the file's levels 1, 2 and 3. Print on US Letter at 100 percent. The stick is
not sized anywhere in the repo, so each design marks a dashed strip for it and none assumes a stick size.

| Option | File | Look |
|--------|------|------|
| A plate | `out/cp-signs-A-plate.pdf` (`.svg`) | Landscape 62 x 42 mm plate, level colour band, big name, switch list. 12 per page, one page. |
| B flag | `out/cp-signs-B-flag.pdf` (`.svg`) | Portrait 40 x 60 mm flag, level colour band down the left, "CP" over the name. 12 per page, one page. |
| C tent | `out/cp-signs-C-tent.pdf` (`-p1/-p2.svg`) | 56 x 36 mm face printed twice, one upside down, folded over the stick top so both sides read. 9 per page, two pages. |

## Item 5: crew board (jobs in sign-up order)

Tabloid (11 x 17 in) landscape, one page each. Jobs and their order are the "Jobs on the Board" list of
`www/data/briefing.json`: D749, NVL, CK1, Yardmaster, Dispatcher, Route 23. Colours per job are from
`ops/hart-ops/data/crew.json` (jobs' `colors`, and the `colors` list for hex values and destinations).

| Option | File | Look |
|--------|------|------|
| A table | `out/crew-board-A-table.pdf` | Six numbered rows: number, code, name, colour chips, a long line for the name. |
| B columns | `out/crew-board-B-columns.pdf` | Six tall cards left to right, number on top, colour chips, a name box at the bottom. |
| C with key | `out/crew-board-C-key.pdf` | Numbered sign-up table at the left, the eight destination colours with their places at the right. |

## Item 6: mock signal (stands beside a sign)

STL in mm, one file per colour per option, in `out/stl/`. The body is black; the lamps are red, yellow and green and
sit in sockets in the body. Each has a 7 x 7 mm peg, 25 mm long, to push into the benchwork foam. Every part is one
watertight piece, far over 9 mm3. Sizes are model millimetres: I did not find a scale for the mock signals in the repo, so
the owner picks the height. Colour order of the lamps (red on top) is a design choice, not a source fact.

| Option | Files | Look |
|--------|-------|------|
| A block | `signal-A-block-*.stl` | 24 x 12 x 45 mm housing, three lamps stacked, on the peg. |
| B mast | `signal-B-mast-*.stl` | 70 mm pole, 30 x 42 mm backing plate with a three-lamp head, 112 mm above the peg. |
| C dwarf | `signal-C-dwarf-*.stl` | 22 x 10 x 30 mm housing, lamps in a triangle, on a 30 x 24 mm foot. |

Print settings follow the repo's 3D rules: one STL per colour, all in the same coordinates, so
load a set together as one object in the slicer. If the body is reprinted under the same name, use Reload from disk.

## Where facts disagree or are missing

- **Rail gaps:** no file lists the interlocking rail gaps or how many each interlocking has. The signs are one per
  interlocking (11), and the mock signals follow the same list; a sign or signal count per gap is the owner's call
  (item 3, the East End and Princess gap, is also still unmarked on the layout).
- **Sign-up order:** no file holds a sign-up order. The order printed is the primer's job list order. The dispatcher
  lineup order in `ops/hart-ops/data/trains.csv` (DS-01 #1 to #7) is by train, not by job, and was not used.
- **Route 23 job:** `www/data/briefing.json` lists a Route 23 streetcar job, but `ops/hart-ops/data/crew.json` has no
  job for it, so its row has no colour chips. Yardmaster and Dispatcher are matched to the crew.json codes YM-01 and
  DS-01 (an alias in `facts.py`).
- **Switch lists differ by file:** `interlockings.csv` gives Brick Switches 1, 3, 5, Barn Switch 7 and East End
  Switches 23, 31, 33. `stations.csv` gives Brick 1, 3, Barn 7, 9, 11, 13 and East End 25, 27, 29, 31, 23, 33. They
  are different groupings (control point against station). The signs use `interlockings.csv`.
- **Public names:** the signs show the `interlockings.csv` names; ADR-005 does not name control points, so whether
  "CP 107" is the public form is unconfirmed.

## Re-run

```
/Users/lnevo/hart/.venv/bin/python -W ignore docs/ops/session4/make_signs.py      # items 4 and 5, SVG and PDF
/Users/lnevo/hart/.venv/bin/python -W ignore docs/ops/session4/make_signals.py    # item 6, STL
/Users/lnevo/hart/.venv/bin/python -W ignore docs/ops/session4/test_session4.py   # the tests
```

`make_signs.py` needs PyMuPDF for the PDFs and `make_signals.py` needs trimesh and manifold3d; the root `.venv` has all three.
