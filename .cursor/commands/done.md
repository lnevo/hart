# Done

Run the definition of done in `.claude/commands/done.md`, every step, then report as it says (commit hash, pushed?, main's push run after a merge, PanelPro test result, hosts deployed). The guard in `.cursor/hooks.json` blocks commits and pushes on `main`, so branch first.

In step 1, keep the docs findable by AI:

- A new or changed `docs/*.md` has one plain summary sentence right under its H1 (the rule in `tools/ops/build_docs_index.py`); rerun `python3 tools/ops/build_docs_index.py`.
- A status entry is one file under `wiki/status/<section>/`, at most 60 words (current fact, owner, date, link to detail; `status_counts.py --check` fails a longer one); history goes to `wiki/STATUS_LOG.md`. `make status` rebuilds `wiki/STATUS.md`, which is not committed (ADR-038).
- A hand-off or project page carries `Status: active | parked | done (YYYY-MM-DD)` under its H1, and the active list in `wiki/home.md` matches.
- Things the owner said not to list go in `wiki/not-pending.md`.
