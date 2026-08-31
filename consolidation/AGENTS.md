# AGENTS — consolidation workspace

**Read this file first** when the task touches pipeline review, SoR consolidation, validators, or railroad documentation refactor.

## Golden rule

**Write only under `hart/consolidation/`.** Live paths in [`LIVE_SOURCES.md`](LIVE_SOURCES.md) are **read-only**.

**Promotion** = copying a named consolidation artifact or script change into live paths. Happens **only when you explicitly request it** for that item. Approved decisions (D1–D10, D2a–e) describe the target; they do not auto-promote.

## Bench freeze (2026-08-31)

Consolidation **builds the new workspace**; it does **not** cut over operations yet.

| Do not touch | Notes |
|------------|-------|
| `~/Desktop/HART/` | Read-only for audits/inventory; no moves, slim, or symlink swaps |
| Live `hart` tree | `jmri/`, `cats/`, `tables/`, live `wiki/`, `docs/` — no edits unless explicit **promote** |
| Pi / Windows layout hosts | No deploy, no roster push, no `sync_hart_package.sh` from consolidation work |
| Original STS/JMRI runtime state | No seed apply or live session changes from here |

**Build targets:** `consolidation/`, `external/*`, **`hart-ops`** (new repo). Desktop slim, Pi sync, and live promotion belong to a **separate cutover/cleanup project** after rebuild is verified.

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

## Promotion gate (on request only)

Cutover to live requires: **explicit user request** for that artifact, validators green, deploy checklist, `wiki/STATUS.md` update. Until then, all drafts stay in `consolidation/`.

## Do not

- Edit `tables/tables.xml` (read-only legacy)
- Edit vendor `lcos/` or `reference/` in LCOS repo without explicit ask
- Commit secrets or `.env.local`
- Start Windows serial bridge from an agent (foreground only)
