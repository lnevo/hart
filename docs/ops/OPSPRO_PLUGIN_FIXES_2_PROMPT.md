# Prompt: fix the Operations Pro plugin faults from the HART build

Written 2026-11-02 after the HART build ([`OPSPRO_FOLLOWUP.md`](OPSPRO_FOLLOWUP.md) section 2 is the list). Paste everything below the line into a fresh Claude Code session started in the hart repo on `main`, with the plugin active from a worktree:

`claude --plugin-dir <worktree>/plugins/operations-pro`

---

Fix the Operations Pro plugin faults found while building the HART railroad with it.

**Read first, in the hart repo:** `docs/ops/OPSPRO_FOLLOWUP.md` section 2 (items P1 to P19, grouped worst first, each with the fault id and the fix sketched), then `docs/ops/opspro-build/plugin_faults.csv` (the 25 raw faults with what was called, what came back and the workaround) and `docs/ops/opspro-build/lessons.csv` (22 lessons; L3, L5, L7, L8, L12, L14, L15, L18, L19 and L20 belong in SKILL.md or its references). The railroad that found them is `jmri/layouts/hart/operations/` in the hart repo; `docs/ops/opspro-build/ordered_session.py` is the script that chained the worker to run a session in order.

**Where:** the model-railroad-skills repo. Make a git worktree on a new branch `agent/claude/ops-fixes-2`, starting from `main` (8522528, plugin version 0.1.2). Do not work inside the hart submodule checkout. Commit there and push that branch only. Never push main and never move the hart submodule pointer.

**Order:** P1 to P4 in this run, then P5 to P12 if they stay small, then P13 to P19 as time allows. Stop and report rather than start anything that needs a design decision from the owner. P4 needs one: it asks `ops_dry_run` for an `order` option, a list of jobs (each a list of trains to build, then terminate, saving between jobs on the same copy), which is what `ordered_session.py` does by chaining `run_worker` with `only`, `terminate`, `save` and `keep`; implement it that way unless a smaller change gives the same result, and keep the one-pass behaviour as the default.

**For each fix:**
1. Reproduce it first on a scratch copy. For P1 to P3 and P7 to P12 the showcase example (`plugins/operations-pro/examples/showcase/operations/`) is enough; for P4 to P6 and P15 copy the HART folder from the hart repo into the scratchpad (it is the owner's data: read it, never write it back, and keep its names out of tests and docs, since the plugin repo is public and its banned-word scan is a case-insensitive substring).
2. Check the correct behaviour against JMRI 5.16 source, tag v5.16, by Java file and line, or a real headless run. The suggested fixes are untried.
3. Add a test that fails before the fix.
4. Fix it, and update SKILL.md, the references and `ops_actions` help where the fault was a wrong or missing description.
5. Commit that fix alone, with a one or two sentence message saying why.

**Checks:** the full suite must pass before each push: `OPS_BANNED_TERMS=hart python3 plugins/operations-pro/tests/run.py` (about 5 minutes; `fast` while working). If a change alters a saved showcase file or its `buildstatus/`, rebuild the shipped folder with `build.py --ship` so the showcase stays replayable.

**Rules:**
- Generic content only: no owner layout content, no real names, no owner words in tests or docs.
- Do not touch the owner's Operations data, `tables.xml`, PanelPro or CATS. Run JMRI only on scratch copies.
- Stage files by name, never with `git add -A`. No force-push.
- Tests must not weaken an assertion to pass. If real JMRI disagrees with a test, say which is right and why.
- Long runs: append a line with step, done/total and ETA to a progress file in the scratchpad at each milestone.

**At the end:** run `docs/ops/opspro-build/ordered_session.py` from the hart repo against a scratch copy of the HART folder with the fixed plugin on `sys.path`, and confirm every train still builds in the same order as `docs/ops/opspro-build/ordered_session.csv` records. If P4 landed, run the same order through `ops_dry_run` and compare. Then bump the plugin version in `plugin.json` so `claude plugin update` picks the fixes up.

**Finish with a report:** each item P1 to P19 as fixed, not reproduced, or left, with why; JMRI file and line for each behaviour change; test count before and after; the commit hashes and whether the branch is pushed; and the new plugin version.
