# AGENTS — consolidation workspace

**Read this file first** when the task touches pipeline review, SoR consolidation, validators, or railroad documentation refactor.

## Golden rule

**Write only under `hart/consolidation/`.** Live paths listed in [`LIVE_SOURCES.md`](LIVE_SOURCES.md) are **read-only** unless the user explicitly requests **promotion** to live.

## Read order

1. This file (`consolidation/AGENTS.md`)
2. [`OBJECTIVE.md`](OBJECTIVE.md)
3. [`LIVE_SOURCES.md`](LIVE_SOURCES.md)
4. [`DECISIONS_PENDING.md`](DECISIONS_PENDING.md) — do not resolve without user approval
5. [`.cursor/plans/pipeline_audit_umbrella_ad0458b1.plan.md`](../../.cursor/plans/pipeline_audit_umbrella_ad0458b1.plan.md) (if present)

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

## Promotion gate (future)

Cutover to live requires: user approval, validators green, deploy checklist, `wiki/STATUS.md` update. Until then, live tree stays frozen.

## Do not

- Edit `tables/tables.xml` (read-only legacy)
- Edit vendor `lcos/` or `reference/` in LCOS repo without explicit ask
- Commit secrets or `.env.local`
- Start Windows serial bridge from an agent (foreground only)
