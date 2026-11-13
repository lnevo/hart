# AnyRail plan reader (prototype)

Reverse-engineered reader for AnyRail `.any` files, used once for
[`docs/jmri/speedmatching/ANYRAIL_LENGTHS.md`](../../../docs/jmri/speedmatching/ANYRAIL_LENGTHS.md).
The plan files are the owner's and are never committed; copy one into a scratch folder outside
the repo as `plan.any` and run the scripts there, in order:

    python3 parse1.py plan.any      # part names and endpoints -> raw.json
    python3 parse2.py               # parts, Bezier curves, flex lengths -> parts.json
    python3 graph.py                # joins and connected levels -> graph.json
    python3 anygraph.py 1           # turnout-to-turnout runs of the staging level -> any_c1.json
    python3 loop_route.py           # PLAN_LOOP_MM and PLAN_TURNOUT_MM for infer_block_lengths.py
    python3 draw.py                 # optional: PNG of each level (needs matplotlib)
    python3 hartgraph.py <tables.xml>   # HART's turnout-to-turnout graph -> hart.json

They write their JSON into the current folder. A generic, tested version is planned for the
public model-railroad-skills plugin after the speed-matching run.
