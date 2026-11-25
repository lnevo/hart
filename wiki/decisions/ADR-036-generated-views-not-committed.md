# ADR-036 — Generated views are built where they are used, not committed

- **Status:** Accepted
- **Date:** 2026-11-25
- **Deciders:** lnevo

## Context

In the 14 days to 2026-11-25, `docs/pipeline-map/index.html` changed in 167 commits, `www/library/pipeline-map.html` in 161 and `docs/INDEX.md` in 74; counted by pull request, 86, 84 and 56 of the merges into `main` touched them. Both map pages hold the whole graph on one line, so any two branches that changed the map conflicted there. On 2026-11-25 three of four PRs needed `git merge origin/main` and a map rebuild before CI would run, and one needed it twice. The merge driver written for the pages (`pipeline-map-page` in `tools/ops/merge_pipeline_map.py`) kept one side and asked for a rebuild, and GitHub never runs it.

Nothing reads the map pages from git. People open `docs/pipeline-map/index.html` in a browser on their own machine, the website deploy publishes `www/library/pipeline-map.html`, and `check.sh` and CI only compared the committed bytes with a fresh build. Agents query the graph (`pipeline_map.json`, `tools/ops/pipeline_query.py`), not the pages.

## Decision

1. **Commit sources; build views where they are used.** A file a generator writes, and that only tools, CI or the website build read, is not committed. It is gitignored and built by whatever needs it, and a build that cannot make it fails with the reason.
2. **The pipeline map pages are the first.** `docs/pipeline-map/index.html` and `www/library/pipeline-map.html` are untracked and gitignored. `make map` (`python3 tools/ops/build_pipeline_map.py`) writes both to look at. The website build (`www/scripts/prepare_github_pages.py`, run by `deploy_hartrailroad.sh`) writes its own copy into the build with `site_page()` and stops when the graph is broken or stale or the page fails a check. `check.sh` and CI run `build_pipeline_map.py --check`, which draws both pages in memory and checks each one (no template placeholder left, every box and link in the page's data, the viewer script inlined, the website's leak and private-name checks) instead of comparing bytes.
3. **The page merge driver is retired.** `.gitattributes` names only the graph's driver (`pipeline-map`, still needed: the graph is a source many branches edit). `merge_pipeline_map.py --install` removes the old `merge.pipeline-map-page` section from the git config.
4. **What stays committed:** sources, including those with a generated part (`pipeline_map.json`, `wiki/STATUS.md`); outputs that hosts load or that ship as committed bytes (`tables.xml` under ADR-029, the CATS panels); pages with hand-written prose around generated regions (the repository guide, the tables file page, the JMRI additions page); and files people read on GitHub or agents read by path (`docs/INDEX.md`, the schematic draft). `docs/INDEX.md` stays committed and merges with git's union driver (owner, 2026-11-25): parallel branches' rows are both kept, and `build_docs_index.py --check` fails on a row left twice.

## Consequences

- A PR that changes the map graph no longer conflicts on the pages and no longer needs a rebuild commit; only two edits to one box or link in `pipeline_map.json` conflict.
- A branch from before this change that still edits the pages gets a modify/delete conflict on them when it merges `main`: `git rm` them.
- The local site preview (`serve_portal.py`, which serves `www/` as it is) shows the map only after `make map`.
- The deploy needs a current graph: when the agent-doc lane is stale, the deploy stops and says to run `make map` and commit the graph.
- Further candidates, each needing a build step in the site build and the preview first: `www/data/tables-browser.json` (the site build already rebuilds it), `www/data/layout-index.json` and `layout-index-cats.json`, and the wiring JSON files.

## Amendment (2026-11-25): the site's generated JSON

- **Owner, 2026-11-25:** the next candidates follow, as a stage. `www/data/tables-browser.json`, `www/data/layout-index.json` and `www/data/layout-index-cats.json` are untracked and gitignored. `www/scripts/site_views.py` lists every file built this way (its `VIEWS`, with the map page), each with the builder that returns its checked text; the site build writes them into the build and stops when one cannot be built or a builder returns nothing. The local preview has them too: `serve_portal.py` builds them into `www/` when it starts and removes, and names, one it cannot build; `make site-data` builds them without the server. This replaces the dead link the preview had until `make map` ran.
- Their checks keep their names (`tables-browser`, `layout-index`, `layout-index-cats`) and build the JSON in memory and run its own checks, comparing no committed bytes. The schematic and desk PNGs the layout indexes sit on stay committed; each carries a stamp of what it is drawn from (`www/scripts/png_stamp.py`), which the JSON used to hold, so a PNG drawn from older inputs still fails its check.
- Every reader builds the file itself or is given it: the CATS index joins to the layout index built in memory (it read the file and joined to nothing when it was missing), and the share card recipe and `test_site_device_names` build the index as the site does.
- `www/data/wiring-inventory.json` follows (owner, 2026-11-25), now that `build_wiring_json.py` builds from the wiring model (ADR-039): it is untracked and gitignored, a `site_views.py` view, and the `wiring-json` check builds it in memory and checks it (every list filled, node ids one each, no network detail left). The wiring viewer reads only the copy the site build or the preview wrote.
- `www/exam/answers.html` and `www/play/answers.html` stay committed by the owner's choice (2026-11-25): they change only with the cards.
