# ADR-040 — Website deploys are recorded, current and one at a time

- **Status:** Accepted
- **Date:** 2026-11-25
- **Deciders:** lnevo
- **Related:** [ADR-036](ADR-036-generated-views-not-committed.md) (generated views are built, not committed)

## Context

`www/scripts/deploy_hartrailroad.sh` builds the site from the local working tree, on any branch, and copies it to the web server with `rsync --delete`, which replaces the whole site. On 2026-11-25 several agent sessions were merging into `main` at once, and a review of the deploy found:

- The only record of a deploy is `.deploy-manifest.json` in the main checkout, which held counts (files, archive items, logos, gallery and fleet items) and nothing about what was shipped. The last deploy that day could not be traced to a commit, branch or session. `make deploy-status` covers only the layout hosts.
- Nothing stopped a deploy from a worktree that lacked commits already on `origin/main`. Such a deploy takes another session's merged pages off the site, and nobody would see it.
- Nothing stopped two deploys at once.
- The 10% drop check counted archive items, logos, gallery and fleet items and all files. A lost page or share card was seen only if the total file count fell 10%.
- The script's header still named VestaCP. The server is HestiaCP on Lightsail since 2026-11-23.

## Decision

1. **Every deploy is recorded.** After the copy, the deploy adds a `deploy` object to `.deploy-manifest.json`: `commit`, `branch`, `dirty`, `worktree`, `started` and `finished` (UTC). `make orient` shows a `website:` line under its last deploys, with the number of `origin/main` commits under `www/` that the site lacks and a note when the deployed commit is not on `origin/main`. `deploy_hartrailroad.sh --status` prints the record. When the record cannot be written after the copy, the deploy says the site is live and the record is not.
2. **A deploy is never behind `origin/main`.** The deploy fetches `origin/main` and stops when `HEAD` does not contain it, naming how many missing commits touch `www/`. It also stops when the fetch fails. `--allow-behind` overrides both, for an owner's rollback or when GitHub is down. A deploy from a branch other than `main`, or with uncommitted changes, warns and goes ahead, since work-in-progress deploys stay allowed. The usual deploy, from the main checkout after pulling `main`, passes.
3. **One deploy at a time.** A lock directory, `hart-site-deploy.lock` in the shared git directory, covers every worktree. It is built under a private name with the owner's PID and checkout, then renamed into place, so it never exists without its PID. A second deploy stops while that PID is alive. When the PID is gone, the lock is renamed aside, checked to be the same stale lock, and taken. The lock is released on exit.
4. **The drop check counts pages and share cards.** The manifest adds `html_pages` and `share_cards` (`assets/share/*.jpg`). The deploy record is not a count, so the drop check skips it. A manifest written before this ADR lacks the new counts, so its first comparison checks only the old ones.
5. The script header names HestiaCP on Lightsail.

Tests: `www/scripts/tests/test_deploy_script.py` runs the script in a throwaway repo with a stub build (behind, override, lock held, stale lock, `--status`). `test_deploy_guards.py` covers the counts, and `tools/audit/tests/test_orient.py` the `website:` line.

### Under ADR-036, assigned to its session

- `www/data/wiring-inventory.json` (`build_wiring_json.py`) is built by the site build and the local preview, not committed.
- `www/exam/answers.html` and `www/play/answers.html` stay committed static files until the cards change, with no build step and no check job (owner, 2026-11-25, in the ADR-036 session; that session's follow-up adds it to ADR-036). Rerun `build_exam_answers.js` or `build_play_answers.js` by hand after changing `run.js` or `runs.js`.

### Later, after that follow-up merges

- Rename `prepare_github_pages.py`, whose name predates the move off GitHub Pages, with `tools/ops/move_path.py`, for example to `build_site.py`.
- `prepare_github_pages.py` (1,484 lines) is the next script for the "leave it safer" rule in `AGENTS.md`: split it the next time a change touches it.

Kept as they are: `www/assets/share/` (the cards need a renderer, and `share_cards.py` checks them on every build) and `www/data/speedmatch/` (exported run data, not a rebuildable view).

## Consequences

- A deploy from a stale worktree stops before the build. The fix is to merge `origin/main`, not to pass `--allow-behind`.
- Every deploy needs network access to GitHub as well as to the web server.
- `make orient` tells sessions what the site is running, so a session can see a deploy is owed after a merge under `www/`.
