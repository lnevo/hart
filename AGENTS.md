# Agent instructions (HART)

Read [`wiki/home.md`](wiki/home.md) first. Chat is a scratchpad; decisions live in `wiki/`.

**Layout:** `hart` (`export JMRI_LAYOUT=hart`). Load `jmri/layouts/hart/output/hart_prod.xml`.

## Commands

| Do | Command |
|----|---------|
| Checks | `python3 jmri/scripts/check_hart_phase02.py` · `python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict` |
| Deploy to layout hosts | `./cats/scripts/sync_hart_package.sh --pi` · add `--win` (or `--all`) when Windows needs it |
| CATS source (Bitbucket) | `./tools/cats/fetch_cats_src.sh` → `tools/cats/src-repo/` |
| CATS binaries | `./tools/cats/fetch_cats_3.2.sh` then `./tools/cats/install_into_jmri.sh` |

`/done` runs the close-out below.

## Definition of done

After any task that **changed files**, do not wait to be asked:

1. **Wiki** — if a live decision or railroad state changed, update `wiki/STATUS.md` (and an ADR if it is a decision).
2. **Commit** on the current branch. Conventional one- or two-sentence message (why, not a file list). Never commit `.env.local`, credentials, or `tools/cats/src-repo/`.
3. **Push** that branch (`git push -u origin HEAD`). Never push or merge to `main`.
4. **Deploy** when live artifacts changed (panels, `tables.xml` bundle, jython, web home, CTC icons, hart-aar, CATS resources). Run `sync_hart_package.sh` as above. Skip deploy for docs-only / AGENTS / wiki-only and say so.
5. **Report** commit hash, pushed?, hosts deployed.

Sheets push (`.env.local`) stays human-gated. Do not force-push `main`.

## Do not

- Edit `tables/tables.xml` — write `tables/new_tables.xml` only.
- Explode or decompile `cats.jar` into `cats/`. CATS is open source: [Kb0oys/cats](https://bitbucket.org/Kb0oys/cats/src/master/).
- Command field turnouts / publish `track/cmd` from launch or “fix paint” scripts.
- Run `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry`, or 2× draw scale unless asked.
- Remove **F30-S-0** where the layout includes it.
- Store JMRI tables from a CATS session. PanelPro owns `tables.xml`.
- Run CATS CTC and the USS CTC machine (or Dispatcher System from inside CATS) at the same time.
- Patch or wrap Dispatcher System / JMRI (`CreateTransits`, `CreateIcons`, `Startup.py`, `TransitCreationTool`). Fix `tables/new_tables.xml` so stock Discover and Stage 1 succeed.

New JMRI track: **Mainline → Yes** (`mainline="yes"`). Geometry **1:1**. Dispatcher sizing is only `dispatcher/export_options.json`.

## Pointers

- Pipelines / landmines: [`docs/AI_CONTEXT.md`](docs/AI_CONTEXT.md)
- Git / branches: [`wiki/AGENTS_GIT.md`](wiki/AGENTS_GIT.md)
- CATS: [`cats/README.md`](cats/README.md) · [`cats/AGENTS.md`](cats/AGENTS.md)
- Public names: [ADR-005](wiki/decisions/ADR-005-public-equipment-names.md) · `jmri/layouts/hart/data/public_name_map.csv`
