# Context for AI assistants

Read [`../AGENTS.md`](../AGENTS.md) and [`../wiki/home.md`](../wiki/home.md) first.

- **One tables file:** `jmri/layouts/hart/output/tables.xml` holds the beans, SML, Dispatcher panel and USS CTC data. JMRI loads it and deploy ships it (ADR-008).
- **Signals:** stock Basic. Homes are `two-searchlight`, dwarfs and virtuals `one-low` (ADR-011).
- **CATS** owns routes; **JMRI SML** owns aspects (`HOLD_ONLY`).
- **Only one desk:** CATS CTC or USS, never both.
- **Layout:** the repo structure is in ADR-007. `cats/` is the CTC overlay only.
- **Gitignored data:** `media/`, `ops/car-cards/`, `docs/wiring/bench/`, and the STS database and backups. Git does not protect these.
- **Never:** command field turnouts from scripts, Store from a CATS session, or patch Dispatcher System.

Older linear4 and NextTrain context is in [`archive/docs/AI_CONTEXT_history.md`](../archive/docs/AI_CONTEXT_history.md).
