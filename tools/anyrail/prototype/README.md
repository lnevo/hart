# AnyRail plan reader (prototype)

Reverse-engineered reader for AnyRail `.any` files, used once for
[`docs/jmri/speedmatching/ANYRAIL_LENGTHS.md`](../../../docs/jmri/speedmatching/ANYRAIL_LENGTHS.md).
The plan files are the owner's and are never committed; copy one into a scratch folder outside
the repo as `plan.any` and run the scripts there, in order:

    python3 parse1.py plan.any      # part names and endpoints -> raw.json
    python3 parse2.py               # parts, Bezier curves, flex lengths -> parts.json
    python3 graph.py                # joins and connected levels -> graph.json
    python3 anygraph.py 1           # turnout-to-turnout runs of the staging level -> any_c1.json
    python3 loop_route.py           # the plan constants of loop 1 and loop 2 for infer_block_lengths.py
    python3 draw.py                 # optional: PNG of each level (needs matplotlib)
    python3 hartgraph.py <tables.xml>   # HART's turnout-to-turnout graph -> hart.json

They write their JSON into the current folder. A generic, tested version is planned for the
public model-railroad-skills plugin after the speed-matching run.

Level plans page (`www/build/track-plan.html`, also published as an artifact): `../levels_svg.py parts.json graph.json OUT`
draws the main and upper level to scale (track only), and `../levels_page.py OUT ../staging_plan.svg PANEL|- site.html artifact.html`
builds the page. `staging_plan.svg` is the staging level's track drawing, with the test loop and the Switch 5 to Switch 15 run
marked; the Switch 7 and 13 markers come from the loop 2 passes (`infer_block_lengths.py --route loop2 --locate`).
