# ADR-007 — Repository layout

- **Status:** Accepted. Amended 2026-10-31: the dissolve in decision 3 is complete. The leftover `archive/consolidation/` folder was removed the same day and remains in git history.
- **Date:** 2026-10-31
- **Deciders:** lnevo

## Context

`consolidation/` was built to bring the railroad's scattered work into one place. It worked: the operator website, submodules, benchwork and mirrors now live in this repo. Its charter still says the live tree is read-only, which is no longer how the project runs. Separately, `cats/` collected material that has nothing to do with the CTC overlay, such as station maps.

## Decision

1. The end state is one home in this repo. `~/sts`, `~/Desktop/HART`, duplicates in `~/Documents` and the repo's `archive/` are retired by a final, undated epic. The `.any` track plans stay in `~/Documents`.
2. `cats/` is only the CTC overlay for JMRI. Its `scripts/pi`, `scripts/windows` and `sync_hart_package.sh` stay as a documented exception because host paths depend on them.
3. `consolidation/` is dissolved into the root. Until then it remains the live home of what it holds, so edit that content in place.
4. Target root: `jmri/`, `cats/`, `docs/`, `www/`, `ops/`, `external/`, `media/`, `tools/`, `wiki/`, `archive/`.
   - `www/` is the public website, renamed from `ops-portal/`.
   - `external/` holds only the four submodules and the STS data.
   - `media/` is gitignored photo, video and archive material.
   - `archive/` holds retired material; nothing in it runs.
5. All created documents live in `docs/`. One file per purpose. Tools stay live; superseded outputs go to `archive/`.
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
| D11, P3a | Closed by ADR-013: hart-ops holds the one car repository |
| Validation tiers | Replaced by the deploy gates, one `check` command and a pre-session checklist |
| D8, D10, D10b | Closed |
| P4a | Closed 2026-10-31: the loose `~/Desktop/HART` files are sorted into `media/hart-research`. The owner confirmed the two wiring `.pptx` and three root `.docx` left there are older copies to ignore: `docs/` holds the current versions, including `docs/wiring/Layout Documentation.pptx` and the recovered `docs/wiring/terminal_blocks.md` |

Records under `consolidation/` that say otherwise, including `AGENTS.md`, `OBJECTIVE.md` and `DECISIONS_RECORDED.md`, are superseded by this ADR.
