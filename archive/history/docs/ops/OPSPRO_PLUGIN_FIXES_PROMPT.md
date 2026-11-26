# Prompt: fix the Operations Pro plugin faults

**Done on 2026-11-02, kept as history.** See `docs/ops/opspro-showcase/PLUGIN_FAULTS.md` for the results.

Paste everything below the line into a fresh Claude Code session started in the hart repo, with the plugin active:

`claude --plugin-dir <worktree>/plugins/operations-pro`

---

Fix the Operations Pro plugin faults found by the showcase build.

**Read first:** `docs/ops/opspro-showcase/PLUGIN_FAULTS.md` in the hart repo. It is the prioritised list, with reproductions. `docs/ops/opspro-showcase/README.md` says what else is in that folder. If the session's branch does not have that folder yet, read it from hart branch `agent/claude/opspro-showcase-copy`.

**Where:** the model-railroad-skills repo. Make a git worktree on a new branch `agent/claude/ops-fixes`, starting from `agent/claude/ops-showcase`, which holds the showcase example and its tests. Do not work inside the hart submodule checkout. Commit there and push that branch only. Never push main and never move the hart submodule pointer.

**Order:** work through the list from Priority 1 down. Do Priorities 1 to 3 in this run, then Priorities 4 and 5 if they stay small. Stop and report rather than start anything that needs a design decision from the owner. The list's "Not faults" section is out of scope.

**For each fix:**
1. Reproduce it first on a scratch copy of `plugins/operations-pro/examples/showcase/operations/`. If it does not reproduce, say so and move on. The reproductions came from recorded runs and were not re-run when the list was written.
2. Check the correct behaviour against JMRI 5.16 source, tag v5.16, by Java file and line, or a real headless run. The suggested fixes are untried, so don't take one on trust.
3. Add a test that fails before the fix.
4. Fix it. Update whatever the list names: `tests/test_showcase.py` (`INTENDED_FINDINGS` and any case that records the wrong behaviour), `GUIDE.md`, `RESULTS.md` and the skill references.
5. Commit that fix alone, with a one or two sentence message saying why.

**Checks:** the full suite must pass before each push: `OPS_BANNED_TERMS=hart python3 -m unittest discover -s plugins/operations-pro/tests` (about 11 minutes with JMRI 5.16; 675 tests at the start). If a change alters a saved file or `buildstatus/`, rebuild the shipped folder with `build.py --ship` so the showcase stays replayable.

**Rules:**
- The plugin repo is public. Generic content only: no owner layout content and no real names. The banned-word scan is a case-insensitive substring, so avoid words such as "chart".
- Do not touch the owner's Operations data, `tables.xml`, PanelPro or CATS. Run JMRI only on scratch copies.
- Stage files by name, never with `git add -A`. No force-push.
- Tests must not weaken an assertion to pass. If real JMRI disagrees with a test, say which is right and why.
- Long runs: append a line with step, done/total and ETA to a progress file in the scratchpad at each milestone.

**After Priority 5, or at the end of the run:** repeat the plugin-behaviour check. Run fresh `claude -p --plugin-dir` sessions from an unrelated folder with plain-language questions about a copy of the showcase, naming no tool or skill, and allow `Bash` so they can make scratch copies. Record whether the skill triggered, which tools were chosen and whether `ops-diagnoser` ran. It ran in 0 of 5 last time.

**Finish with a report:** each list item as fixed, not reproduced, or left, with why; JMRI file and line for each behaviour change; test count; any `GUIDE.md` case whose text changed; the commit hash and whether it is pushed.
