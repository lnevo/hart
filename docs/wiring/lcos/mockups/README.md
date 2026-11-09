# LCOS Signal Manager mockup: occupancy and turnout rules

`lcos-signal-manager-occupancy-local-remote-mockup.png` is a mockup from a design
discussion (Cursor, 2026) on making LCOS signals behave more like prototype
signals without building full prototype logic. It is a sketch, not an
implemented screen.

## What the mockup shows

- **Aspect to port map.** Each signal maps STOP, APPROACH and CLEAR to output
  ports A, B and C.
- **Occupancy gating, "STOP unless blocks are clear".** Two panels:
  - *Approach* needs the checked blocks clear.
  - *Clear* needs its own checked blocks clear and also needs the Approach
    blocks clear (the cascade).
  - Blocks are split into **Local** (0-7) and **Remote** (8-15) groups.
- **Turnout rules, local 0-7 and remote 8-15.** Per turnout: a "Motion Only"
  option, "STOP unless aligned", and the aspect allowed when the turnout is
  MAIN (CLEAR or APPROACH) or DIVERGED (APPROACH or N/A).

## Idea in one line

A small fixed rule set (block occupancy, then turnout alignment, then pick
the most permissive allowed aspect) in place of full prototype signalling.

Only the image survives; no written spec was found in the repo. Expand this
note if the design is picked up again.
