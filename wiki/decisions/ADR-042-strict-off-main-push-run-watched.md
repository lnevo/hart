# ADR-042 — Main no longer requires branches to be up to date

- **Status:** Accepted (owner, 2026-11-27); in force once the owner turns `strict` off on main's branch protection
- **Date:** 2026-11-27
- **Deciders:** lnevo
- **Related:** [ADR-041](ADR-041-baselines-lowered-at-wave-end.md) (baselines lowered at wave end)

## Context

Main's branch protection required the `check` status and `strict`: a PR could merge only when its branch held the latest `main`. With several sessions merging at once, every merge sent each other open PR back to merge `main` in, push and wait for another CI run, even when the two PRs shared no file. ADR-041 removed the largest source of those merges, the baseline lists every PR rewrote. This ADR removes the rule itself.

The order was set by the owner on 2026-11-27: PR A (ADR-041: the baseline sweep and the union merge for the two ratchet lists) and PR B (the deploy gate stops on a red main, and the Main red rule in the `coordinate` skill) merge first, with `strict` still on. Then the owner turns `strict` off and keeps `check` as the one required status. PR C changes the agent rule text to match.

## Decision

1. **`strict` goes off after PR A and PR B** (owner). `check` stays required on the PR's head.
2. **A PR merges once `check` passes on its head** and, beside other sessions, the queue holder gives go. It does not merge `main` in again because main moved.
3. **Merge `main` in only when GitHub shows a conflict**, or when the PR's last `check` run is older than the latest change on main to a file the PR touches.
4. **Files with merge drivers merge locally only.** The union merge (`tools/audit/hand_tables.csv`, `tools/audit/py_sizes.csv`, `wiki/STATUS_LOG.md`, `docs/INDEX.md`) and the pipeline-map driver (`docs/pipeline-map/pipeline_map.json`) run in a local `git merge origin/main`, never in GitHub's merge button, update-branch or the web conflict editor. A PR that touches one of them merges main locally and pushes. `.gitattributes` holds the full list.
5. **Whoever merged watches main's push run** of `check.yml` for the merge commit and reports how it ended. A red run falls under the Main red rule in the `coordinate` skill.

### Deploys (owner rulings, 2026-11-27)

The layout deploy gate (G0c in `tools/hosts/deploy/gate.sh`) and the website deploy ask `ci_pass.py --main-red` about main's push run:

- a run that ended red (failure, cancelled or timed out) stops the deploy;
- a run still in progress does not block;
- no push run for the commit yet does not block, and the deploy says so;
- a `gh` or API error does not block: the deploy prints a warning naming the error and goes on to G4.

## What is caught where

- **On the PR:** the `check` job runs on GitHub's merge of the PR head with main as it was when the run started. It catches what the PR breaks on its own and against that main. A docs-only or light PR runs the quick checks only, and a full PR skips jobs whose inputs match main's last passing stamps (`docs/pipeline-map/checks-and-remote.md`).
- **On main after the merge:** the push run takes the full path, every job with no stamp skips. It catches what two PRs break together when neither run saw the other's change, and what a PR's skips or light path missed. The weekly scheduled run stays as a second net.

## Consequences

- An open PR no longer waits for a fresh CI run each time another PR merges.
- A break between two PRs shows on main, not on a PR. The merger's watch, the Main red rule and the deploy gate keep it from shipping or piling up.
- The rule text lives in the `handoff` skill (Merge), the `coordinate` skill (Merge queue) and `/done` step 3.
