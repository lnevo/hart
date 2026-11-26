# Session 4 designs: control point signs and crew board

Status: owner's picks made, drafts for printing. Nothing here is published. From the
[session 4 punch list](../SESSION4_PUNCH_LIST.md), items 4 and 5.

## The picks

- **Item 4, control point signs:** option A, the plate (owner, 2026-11-26). `out/cp-signs-A-plate.pdf` (and `.svg`):
  eleven plates, 62 x 42 mm, one page on US Letter at 100 percent. Each has a level colour band, the name and its
  switches, and a dashed strip below it that marks where the stick is glued on the back.
- **Item 5, crew board:** option B, the columns (owner, 2026-11-26). `out/crew-board-B-columns.pdf` (and `.svg`):
  tabloid (11 x 17 in) landscape, six tall cards left to right with the order number on top, destination colour
  chips and a name box at the bottom.
- **Item 6, mock signals:** not wanted (owner, 2026-11-26); items 6 and 8 are marked so on the punch list.

## Where the facts come from

- Control points, names, levels and switches: the interlockings of every level, read through hartlib
  (`railroad_facts.read_interlockings`). Eleven signs: Brick, Barn, East End, Princess (staging); CP 107, CP 123,
  CP 127 (main); CP 201, CP 211, CP 217, CP 223, CP 225 (upper). Staging, Main and Upper are levels 1, 2 and 3.
- Jobs and their order: "Jobs on the Board" in `www/data/briefing.json`: D749, NVL, CK1, Yardmaster, Dispatcher,
  Route 23.
- Job colours and the colours' hex values: `ops/hart-ops/data/crew.json`.

## Gaps and disagreements

- No file lists the interlocking rail gaps or how many each interlocking has. The signs are one per interlocking.
- The stick is not sized anywhere in the repo, so the plate marks a strip for it and assumes no size.
- No file holds a sign-up order. The board uses the primer's job order. The DS-01 lineup is by train, not by job.
- `briefing.json` lists a Route 23 job; `crew.json` has none, so its card has no colour chips. Yardmaster and
  Dispatcher are matched to the `crew.json` codes YM-01 and DS-01 (an alias in `facts.py`).
- The interlockings file and `stations.csv` list different switches (Brick 1, 3, 5 against 1, 3; Barn 7 against
  7, 9, 11, 13; East End 23, 31, 33 against 23, 25, 27, 29, 31, 33). They group by control point and by station. The
  signs use the interlockings.
- ADR-005 does not name control points, so "CP 107" as the public form is unconfirmed. The sign wording "CONTROL
  POINT" and the level names are drafted here.
- Not test-printed; the PDFs are checked on screen only.

## Re-run

```
/Users/lnevo/hart/.venv/bin/python -W ignore docs/ops/session4/make_signs.py
/Users/lnevo/hart/.venv/bin/python -W ignore docs/ops/session4/test_session4.py
```

`make_signs.py` needs PyMuPDF for the PDFs (the root `.venv` has it); without it only the SVGs are written.
