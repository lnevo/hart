# AnyRail plan reader (prototype)

Archived 2026-11-23 from `tools/anyrail/prototype/` (repo review, owner's choice): no other script calls these scripts, and speed matching, the only user of their output, is parked.

The schematic-maps plugin's plan reader (`schematic anyplan`, in `external/model-railroad-skills`) replaces
`parse1.py`, `parse2.py` and `graph.py` for reading a plan: it reads every maker's track, the first end point in the file and per-file record tags, which these scripts do not (they misread
5.3b's part 0, drop the Walthers double crossover and read nothing from 5.3c). They are kept here for the outputs built on
them: the speed-matching lengths, and the PLAN_ constants in `jmri/layouts/hart/scripts/infer_block_lengths.py`, which
`loop_route.py` prints. Rerun it from here if the plan changes.

Reverse-engineered reader for AnyRail `.any` files, used once for
[`docs/jmri/speedmatching/ANYRAIL_LENGTHS.md`](../../docs/jmri/speedmatching/ANYRAIL_LENGTHS.md).
The plan files are the owner's and are never committed; copy one into a scratch folder outside
the repo as `plan.any` and run the scripts there, in order:

    python3 parse1.py plan.any      # part names and endpoints -> raw.json
    python3 parse2.py               # parts, Bezier curves, flex lengths -> parts.json
    python3 graph.py                # joins and connected levels -> graph.json
    python3 anygraph.py 1           # turnout-to-turnout runs of the staging level -> any_c1.json
    python3 loop_route.py           # the plan constants of loop 1 and loop 2 for infer_block_lengths.py
    python3 draw.py                 # optional: PNG of each level (needs matplotlib)
    python3 hartgraph.py <tables.xml>   # HART's turnout-to-turnout graph -> hart.json

They write their JSON into the current folder.

Level plans page (`www/build/track-plan.html`): `tools/anyrail/levels_svg.py` draws the three levels to scale from the plan with
the plugin's plan reader (track only; it needs no prototype script) and `tools/anyrail/levels_page.py` builds the page from those drawings,
`block_lengths.csv` and `plan_overrides.json`. See the docstrings of both.
