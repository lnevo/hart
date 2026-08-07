# Agent instructions (Panel workspace)

**Start here:** [`wiki/home.md`](wiki/home.md) (system of record) and [`docs/AI_CONTEXT.md`](docs/AI_CONTEXT.md).

**Active next-gen layout:** **`hart`** (`export JMRI_LAYOUT=hart`) — see [`wiki/projects/hart-panel.md`](wiki/projects/hart-panel.md).

- Git / multi-agent branches: [`wiki/AGENTS_GIT.md`](wiki/AGENTS_GIT.md)
- Bootstrap: `python3 jmri/scripts/bootstrap_hart_from_linear6.py`
- Checks: `python3 jmri/scripts/check_hart_phase02.py`
- Load panel: `jmri/layouts/hart/output/hart_prod.xml`

Also documented in AI_CONTEXT:

- JMRI vs NextTrain dispatcher pipelines
- linear4 production MQTT panel; linear6 = frozen connectivity reference for hart
- What **not** to run (resize, polish, 2× draw scale) unless asked
- Google Sheets push (`.env.local` — never commit)

For Mac-specific block/sensor/NX detail, see [`jmri/docs/PROJECT_OVERVIEW.md`](jmri/docs/PROJECT_OVERVIEW.md).

**`tables/tables.xml`** is read-only; edit `tables/new_tables.xml` only (see `.cursor/rules/current-tables-readonly-source.mdc`).
