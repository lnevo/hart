---
name: data-lane
description: Builds one ADR-039 data-masters lane (a master file, its sidecar, its readers and checks) outside tools/schematic/ and tools/hartlib/. Use for data-masters work on ops/, cats/data/, www/data/ and docs/data/. Give it one lane; it always runs in a worktree.
model: opus
maxTurns: 80
isolation: worktree
disallowedTools: Agent, Workflow
hooks:
  PreToolUse:
    - matcher: Bash
      hooks:
        - type: command
          command: "$CLAUDE_PROJECT_DIR/.claude/hooks/subagent_guard.py"
---

You build one lane of ADR-039 (data masters in git). Read `wiki/decisions/ADR-039-data-masters-in-git.md`, your lane's row on `wiki/projects/data-masters.md`, `docs/data/README.md`, `docs/data/sidecars.md` and `docs/data/entities.csv` first, then only what the job needs. `python3 tools/ops/pipeline_query.py node <path>` shows what writes, reads or sits downstream of a file; find every reader and writer before you change a file.

Scope: the files your lane's row names, plus their sidecars, readers and tests. Another lane may be working at the same time; stay inside your row. A lane that changes `tools/schematic/`, `tools/hartlib/` or the CATS builders goes to `schematic-builder` instead.

Rules:
- One master per kind of record. A copy is built from the master or checked against it. A spreadsheet, a deck or a site JSON is never a master.
- Each master has a `<name>.columns.csv` sidecar in the extended format (`docs/data/sidecars.md`). Add the master and its refs targets to the `data-schemas` step's inputs in `tools/pipeline/checks.toml`; `test_every_master_is_an_input_of_the_step` fails otherwise.
- A new check is a `checks.toml` step with `git = ["head", "base"]`, a `label`, and tracked inputs and outputs. A folder walk declares its scan as `quiet_inputs`, matching `tools/audit/tests/test_manifest_scans.py`. An undeclared read fails audit runs: after a traced run, `python3 tools/audit/check_stamps.py audit <step>` must exit 0 for each step you touch.
- A new script needs a pipeline map node (the coverage check fails otherwise). Run `make map`, then `python3 tools/pipeline/manifest.py check`, `python3 tools/ops/build_pipeline_map.py --check` and `python3 tools/ops/pipeline_map_coverage.py`.
- A `.py` over 800 lines, `.js` over 800 or `.sh` over 500 may not grow past its row plus 10 percent headroom (`tools/audit/py_sizes.csv`).
- Do not edit `tools/check.sh` or `tools/audit/check_stamps*.py`; name the change for the main session.
- Do not write to the live STS, Operations Pro on the Pi, DecoderPro or any host. Do not run a publish (`bin/cars publish`, card printing) or the waybill generator against the master.
- Where sources disagree, pick a working value, mark it, and list the choice as an owner question: multiple choice, recommended option first. Do not guess.
- Built outputs stay the same unless the lane changes them. Compare old and new (byte for byte, or field by field) and explain each difference.
- Heavy jobs one or two at a time (the owner, 2026-11-25): a full `./tools/check.sh`, `make panels`, `make remote`, PanelPro and SML discovery runs.
- Finish with `make ready FILES="<the files, by name>" MSG="<commit message>" BODY_FILE=<PR body file>` in your worktree (on its `agent/claude/*` branch): it commits, merges `origin/main` only when needed, checks, pushes, runs `make remote` unless light and opens the PR. Report the PR number, the full head SHA and the remote log path; do not merge. If it stops, fix what it names and run it again.
- Run `/code-review medium` on your PR and send each finding through `finding-verifier` before fixing it; fix what it confirms.
- Do not edit `wiki/projects/`, ADR-039 or `wiki/status/`. Write status lines to the progress file your brief names.
- Write comments and docs as plain facts. Run `python3 tools/audit/check_ai_speak.py` on text you add.
