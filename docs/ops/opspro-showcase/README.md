# Operations Pro showcase: working copy

The Juniper Falls & Northern, an invented railroad built as a test of the Operations Pro plugin. This is a separate copy for working from. It is not HART Operations data, so never load it into the HART profile.

The master copy of the railroad stays in the plugin as an example: `plugins/operations-pro/examples/showcase/` in model-railroad-skills. If the two differ, the plugin's copy is the one its tests check.

| Path | What it is |
|---|---|
| `PLUGIN_FAULTS.md` | The plugin fault list, all resolved, with the known limits. It lives only here |
| `railroad/operations/` | The six Operations XML files, build reports and one backup set |
| `railroad/GUIDE.md` | The tour of the 43 cases |
| `railroad/RESULTS.md` | Per-case results and the review summary |
| `railroad/PLAN.md` | The design plan, with an as-built note |
| `railroad/build/`, `railroad/build.py` | The steps that rebuild the railroad from blank |
| `cases.csv`, `faults.csv`, `hand_edits.csv`, `behaviour.csv` | The final scorecard data |
| `review_claims.csv`, `review_failures.md` | The independent review of 201 guide claims. Its `R/` and `runs/` paths were scratch folders and no longer exist |

`railroad/build.py` expects the plugin's `servers/` folder at its plugin location, so run it from the plugin copy.

The faults were fixed with [`../OPSPRO_PLUGIN_FIXES_PROMPT.md`](../OPSPRO_PLUGIN_FIXES_PROMPT.md), which is kept as history.
