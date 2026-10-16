# ADR — Consolidation vs promotion hygiene

**Status:** Accepted (consolidation) · 2026-08-31  
**Locks:** D1, D5 · [`DECISIONS_RECORDED.md`](../../DECISIONS_RECORDED.md)

## During consolidation

- All writes under `consolidation/` only.
- Validators **read** live; reports under `consolidation/audits/`.
- Findings update: manifest row + audit markdown + draft wiki guide.
- Retired one-shots → `unused-modules/` (not immortal live delete lists).

## On promotion (explicit user request only)

1. User names the artifact(s) to promote.
2. Tier A validators green against live.
3. Apply change to live path(s).
4. Update live `wiki/STATUS.md` + pipeline guide when railroad state changed.
5. Deploy if live artifacts changed (`sync_hart_package.sh`).

## Do not

- Patch live workflows to “fix forward” during review.
- Add one-shot deletes to active cleanup scripts without `unused-modules/` entry (D5).
- Auto-promote because a consolidation ADR or decision is “approved.”
