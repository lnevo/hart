# Code-quality wave (2026-11-26)

Status: active
Coordinator: hart-bb, since 2026-11-26 10:16 (from hart-6d, owner's decision; it also runs this wave's deploys)

A read-only review on 2026-11-26 graded the repo's 781 scripts at B- overall. The code was decent, with recurring AI habits:
- helpers copied between files until the copies drift
- `str(exc) from None`, which drops the traceback
- dated history in comments
- tests that search source text instead of running it
- annotations that no checker runs
- records kept in bare dicts and tuples

It also found a bug: the operating-flag guard missed `$(ssh …)` and `xargs ssh`. This wave fixes those habits and reviews every C- and D-graded file. The AGENTS.md "Scripts" rules (#1225) cover new code.

## Owner's choices (2026-11-26)

- **History notes:** delete a note when an ADR, a wiki page or git already records the decision. Move a decision that only the comment records into the wiki. Keep the why in the code, without dates.
- **mypy:** strict for hartlib. Every other CPython folder runs in basic mode against a per-file baseline that may only go down. Jython is excluded.
- **Parked code:** `gen_ctc_track_plan.py` and the parked rules in `refresh_bean_comments.py` stay as they are.
- **Guard against regressions:** a ratchet check (`check_habits.py`) plus the AGENTS.md rules. ruff stays on F rules only.
- **Deploys:** deploy each merge that ships straight away, with no live try ("just deploy, consider everything tested").

## Lanes

| Lane | Scope | PR |
|---|---|---|
| L0 | AGENTS.md and handoff rules | #1225 merged |
| L1 | Guard parser: one shared `shell_parse.py` for main_guard and subagent_guard | |
| L2 | hartlib types and the mypy check | |
| L4 | tools/ drift, the habits ratchet, the C and D files in tools/ | |
| L5a | ops drift (colours, OOXML, shim) and car and waybill types | |
| L6a | jmri source-grep tests, sml_handoff, the C and D files in jmri/ | |
| L3 | tools/schematic types and C and D files (after L2) | |
| L5b | publications and station maps C and D files (after L5a) | |
| L6b | speedmatch C and D files | |
| L7 | www/scripts, exam and play C and D files | |
