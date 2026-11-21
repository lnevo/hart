# Context for AI assistants

Short list of the layout facts and landmines an AI assistant needs before touching tables, panels or signals in this repo.

Read [`../AGENTS.md`](../AGENTS.md) and [`../wiki/home.md`](../wiki/home.md) first.

- **One tables file:** `jmri/layouts/hart/output/tables.xml` holds the beans and SML. The Dispatcher panel, Entry/Exit (NX) and USS CTC data are parked since the helix-join release (November 2026), kept in `jmri/layouts/hart/parked/`. JMRI loads it and deploy ships it (ADR-008).
- **Signals:** stock Basic. Homes are `two-searchlight`, dwarfs and virtuals `one-low` (ADR-011).
- **CATS** owns routes; **JMRI SML** owns aspects (`HOLD_ONLY`).
- **Python tools:** CPython scripts read and write tables.xml, repo paths and host settings through `hartlib` ([`tools/hartlib/README.md`](../tools/hartlib/README.md)). Jython scripts that run inside JMRI never import it.
- **Layout:** the repo structure is in ADR-007. `cats/` is the CTC overlay only.
- **Gitignored data:** `media/`, `ops/car-cards/`, `docs/wiring/bench/`, and the STS database and backups. Git does not protect these.

Older linear4 and NextTrain context is in [`archive/docs/AI_CONTEXT_history.md`](../archive/docs/AI_CONTEXT_history.md).
