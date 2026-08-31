# HART consolidation — objective

**Charter:** Produce a validated, browsable, refactor-ready picture of the entire HART railroad software stack **without changing live operational sources**.

## Success criteria

1. **Live inventory** — every pipeline documents what it reads/writes today (`LIVE_SOURCES.md`).
2. **Proposed SoR** — draft canonical artifacts under `sor/` (not promoted until approved).
3. **Draft runbooks** — pipeline guides under `wiki/pipelines/` with SoR tables and consolidation notes.
4. **Read-only validators** — `validators/run_all.sh` checks live state; reports go to `audits/`.
5. **Batch decisions** — open choices in `DECISIONS_PENDING.md` for owner approval in parallel.
6. **Human navigation** — open [`index.html`](index.html) in a browser to browse categories.

## Non-goals (this phase)

- Editing `jmri/`, `cats/`, `tables/`, live `wiki/`, or `docs/wiring/`.
- PanelPro reload, CATS deploy, broker changes, or `sync_hart_package.sh` behavior changes.
- Promoting consolidation drafts into live paths (separate **promotion gate**).

## Lead engineer role

Review live code and docs as **read-only references**. Write improvements, audits, ADRs, and refactored script **copies** only under `consolidation/`. Flag gaps; do not patch live workflows to “fix forward” during consolidation.

## Related

- [`AGENTS.md`](AGENTS.md) — mandatory agent instructions
- [`DECISIONS_PENDING.md`](DECISIONS_PENDING.md) — approve these in parallel
- [`manifest.yaml`](manifest.yaml) — pipeline registry
