# ADR-018 — Staged intake for cars and locomotives

- **Status:** Accepted. Extends ADR-013. Built 2026-11-08.
- **Date:** 2026-11-08
- **Deciders:** lnevo

## Context

ADR-013 gave cars one repository and one intake. Locomotives had none: the DecoderPro roster, the Operations Pro engine roster, the CS-105 sync and the Dispatcher traininfo files were each updated by hand. Photos, records and live systems were changed in one step, so a bad crop or a misread number could reach STS and JMRI before anyone looked.

## Decision

1. Intake runs in stages, and no stage starts until the owner has approved the one before. Each stage ends with a review sheet.
2. Stages: (1) photo intake, validation and adjustment; (2) repository records; (3) cars into STS and Operations Pro; (4) locomotives into JMRI; (5) cards and public pages; (6) decoder programming and speed matching, per loco, later.
3. Stages 1 and 2 write nothing outside the repository. Stages 3 and 4 take a backup first and show a dry run.
4. Locomotives use a `locos` subcommand in the same hart-ops tool as cars, with the same repository, queue and review sheet.
5. Stage 1 asks the owner only about flagged photos (unreadable number, duplicate, mismatch with the repository). Unflagged photos are approved in bulk from the contact sheet.
6. Each batch records its approval in a committed manifest.
7. The AI review is a manual step before approval. The AI suggests readings and flags disagreements; only the owner approves.
8. Stage 3 runs only when every photo is recorded or rejected. `publish --only ID` tests one car alone. Publish also checks that stage 2 is committed, the Pi's Operations files match the repo, and an STS backup under 12 hours old exists.

## Consequences

- A loco has one entry point and one record, and Stage 4 works from it.
- The repository stays the master (ADR-015); STS stays the master of car position (ADR-016).
- Locos without a decoder programmed yet stop at Stage 4 and wait for Stage 6.
