# Done

Run the definition of done in `AGENTS.md`, every step, then report as it says (commit hash, pushed?, PanelPro test result, hosts deployed). The guard in `.cursor/hooks.json` blocks commits and pushes on `main`, so branch first.

In step 1, keep the docs findable by AI:

- A new or changed `docs/*.md` has one plain summary sentence right under its H1 (the rule in `tools/ops/build_docs_index.py`); rerun `python3 tools/ops/build_docs_index.py`.
- A `wiki/STATUS.md` entry is one or two sentences (current fact, owner, date, link to detail); history goes to `wiki/STATUS_LOG.md`.
- A hand-off or project page carries `Status: active | parked | done (YYYY-MM-DD)` under its H1, and the active list in `wiki/home.md` matches.
- Things the owner said not to list go in `wiki/not-pending.md`.
