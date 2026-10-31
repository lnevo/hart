# ADR-007 — Repository layout

- **Status:** Accepted
- **Date:** 2026-10-31
- **Deciders:** lnevo

## Context

`consolidation/` was built to bring the railroad's scattered work into one place. It worked: the operator website, submodules, benchwork and mirrors now live in this repo. Its charter still says the live tree is read-only, which is no longer how the project runs. Separately, `cats/` collected material that has nothing to do with the CTC overlay, such as station maps.

## Decision

1. The end state is one home in this repo. `~/sts`, `~/Desktop/HART` and duplicates in `~/Documents` are retired by a final, undated epic. The `.any` track plans stay in `~/Documents`.
2. `cats/` is only the CTC overlay for JMRI. Its `scripts/pi`, `scripts/windows` and `sync_hart_package.sh` stay as a documented exception because host paths depend on them.
3. `consolidation/` is dissolved into the root. Until then it remains the live home of what it holds, so edit that content in place.
4. Target root: `jmri/`, `cats/`, `docs/`, `www/`, `ops/`, `benchwork/`, `external/`, `media/`, `tools/`, `wiki/`, `archive/`.
   - `www/` is the public website, renamed from `ops-portal/`.
   - `external/` holds only the four submodules and the STS data.
   - `media/` is gitignored photo, video and archive material.
   - `archive/` holds retired material; nothing in it runs.
5. One file per purpose. Tools stay live; superseded outputs go to `archive/`.
6. Live data is read from the repo. `~/sts` gets no sync. Four `~/Desktop/HART` folders stay in step through `sync_desktop_data.py`, which never deletes.

## Consequences

Consolidation decisions:

| Decision | Outcome |
|---|---|
| D1, D12 | Closed as complete |
| D3 | Superseded by the single-file tables decision (ADR-008) |
| D9 | Superseded: the website is public. Moving the STS web and scale interface to the Pi stays an optional, low-priority goal |
| D5 | Kept; retired logic goes to `archive/` |
| D7, P3b | Kept; submodules move to `external/` |
| D2f | Closed; the 22 live virtual masts are correct |
| D2, D2e | Kept; `public_name_map.csv` is the single names source |
| D4, D6 | Kept |
| D11, P3a | Open goal: hart-ops is the intended car source, but no authoritative car workflow exists yet |
| Validation tiers | Replaced by the deploy gates, one `check` command and a pre-session checklist |
| D8, D10, D10b | Closed. Event 125 auto-resend is a known issue; `RESUBSCRIBE FORCE` is the manual recovery |
| P4a | Open: the loose `~/Desktop/HART` files still need sorting before that folder retires |

Records under `consolidation/` that say otherwise, including `AGENTS.md`, `OBJECTIVE.md` and `DECISIONS_RECORDED.md`, are superseded by this ADR.
