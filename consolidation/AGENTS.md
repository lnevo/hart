# AGENTS — consolidation workspace

**Read this file first** when the task touches pipeline review, SoR consolidation, validators, or railroad documentation refactor.

## Golden rule

**Write only under `hart/consolidation/`.** Live paths in [`LIVE_SOURCES.md`](LIVE_SOURCES.md) are **read-only**.

We are **building a new authoritative tree** under `consolidation/` (and `consolidation/external/*`). The live `jmri/`, `cats/`, `tables/`, and Desktop/HART paths stay untouched until that tree is complete and you switch over.

## Bench freeze (2026-08-31)

Consolidation **builds the new workspace** only.

| Do not touch | Notes |
|------------|-------|
| `~/Desktop/HART/` | Read-only for audits/inventory; browse via [`html/archive/f-root-index.html`](html/archive/f-root-index.html) |
| Live `hart` tree | `jmri/`, `cats/`, `tables/`, live `wiki/`, `docs/` — no edits from consolidation work |
| Pi / Windows layout hosts | No deploy, no roster push, no `sync_hart_package.sh` from consolidation work |
| Original STS/JMRI runtime state | No seed apply or live session changes from here |

**Build targets:** `consolidation/` and **`consolidation/external/*`** submodules only. Do not create standalone clones under `$HOME` (e.g. no `~/hart-ops`).

## Read order

1. This file (`consolidation/AGENTS.md`)
2. [`OBJECTIVE.md`](OBJECTIVE.md)
3. [`BACKLOG.md`](BACKLOG.md)
4. [`LIVE_SOURCES.md`](LIVE_SOURCES.md)
5. [`DECISIONS_RECORDED.md`](DECISIONS_RECORDED.md)

Browse portal: [`index.html`](index.html)

## Where to put work

| Kind | Path |
|------|------|
| Draft pipeline guides | `consolidation/wiki/pipelines/` |
| Draft ADRs | `consolidation/wiki/decisions/` |
| Proposed SoR files | `consolidation/sor/` |
| Refactored script copies | `consolidation/scripts/` |
| Validators (read live) | `consolidation/validators/` |
| Audit reports | `consolidation/audits/` |
| LCOS / sibling specs | `consolidation/cross-repo/` |
| Browse site | `consolidation/index.html`, `consolidation/html/` |

## Validators

- Run from repo root: `bash consolidation/validators/run_all.sh`
- Validators may **read** live XML/CSV and **write** only under `consolidation/audits/`
- Wrappers call live scripts (`audit_panel_contracts.py`, `check_hart_phase02.py`) — do not fork logic into live tree

## Do not

- Edit `tables/tables.xml` (read-only legacy)
- Edit vendor `lcos/` or `reference/` in LCOS repo without explicit ask
- Commit secrets or `.env.local`
- Start Windows serial bridge from an agent (foreground only)
