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
6. Live data is read from the repo. `~/sts` gets no sync. ~~Four `~/Desktop/HART` folders stay in step through `sync_desktop_data.py`, which never deletes.~~ Superseded 2026-11-09: `~/Desktop/HART` is retired and the sync tool removed (see the amendment below).

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

## Amendment 2026-11-09 (final cleanup, first pass)

- The repo's `archive/` **stays**. It holds retired material that nothing runs, and the owner keeps it in the tree. This replaces "retire the repo's `archive/`" in decision 1.
- `~/sts` is retired. It had been frozen since 2026-09-05; its photos were already in the repo, and the owner judged its old session files and database not worth keeping. It was moved to the Trash.
- The original car photos behind the card pipeline (`~/Desktop/HART/Car Cards/Images`, the June 2026 shoot) are kept in the owner's Photos library, not on disk. All 84 distinct photos were matched there by file name and shoot date, then the disk copies were moved to the Trash.
- Files in `~/Documents` that were byte-identical copies of repo content (seven research images and `ThisIsShenango.pdf`, all in `media/hart-research`) were moved to the Trash. Kept: the `.any` track plans, the Arduino IDE sketchbook (`~/Documents/Arduino`, `LCOS_Client_Bare`), and two images that belong to other sets (a saved web page and `Layout/For James`).
- `~/Desktop/HART` is retired. Its 1,038 files that were byte-identical to repo content went to the Trash first; the owner then judged the rest (old STS seed and session material in `Car Cards/archive`, a Python environment, older pipeline and wiring copies, and three wiring decks the repo has newer versions of) not worth keeping, and the whole folder went to the Trash. `tools/ops/sync_desktop_data.py` is removed, the car cards, waybills and industry routing run from the hart-ops submodule, and `docs/wiring/` is the only wiring copy.
- With that, the final cleanup epic in decision 1 is complete: this repo is the one home, apart from the `.any` track plans in `~/Documents`, the car photo originals in the Photos library and the repo's own `archive/`.

Records under `consolidation/` that say otherwise, including `AGENTS.md`, `OBJECTIVE.md` and `DECISIONS_RECORDED.md`, are superseded by this ADR.
