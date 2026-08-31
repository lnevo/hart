# ADR — Consolidation vs promotion hygiene (draft)

**Status:** Draft — pending D1 in [`DECISIONS_PENDING.md`](../../DECISIONS_PENDING.md).

## During consolidation

- All writes under `consolidation/` only.
- Validators read live; reports under `consolidation/audits/`.
- Findings update: manifest row + audit markdown + draft wiki guide.

## On promotion (future, user-approved)

1. User approves specific files in `DECISIONS_PENDING.md`.
2. Tier A validators green against live.
3. Apply change to live path(s).
4. Update live `wiki/STATUS.md` + pipeline guide.
5. Deploy if live artifacts changed (`sync_hart_package.sh`).

## Do not

- Patch live workflows to “fix forward” during review.
- Add one-shot deletes to immortal cleanup lists without audit (D5).
