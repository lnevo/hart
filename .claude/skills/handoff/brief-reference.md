# Brief reference for code agents

Read by a code agent whose brief points here. Not a skill.

## Quality (code only)

1. Clear domain errors, not raw exceptions.
2. No silent fallbacks (guessing, defaulting, skipping).
3. Invariant checks after mutations.
4. Inputs validated up front.
5. No duplicated helpers or per-call rebuilds.

Test the error paths. Check your whole diff against these five before reporting. Reviews here keep finding: paths (symlinked worktree mirrors such as media/ and ops/car-cards/, cwd-relative names, ../ and ./ segments), git or subprocess failures shown as tracebacks, graph or tree walks (shortest level first, cycles), Markdown parsing (wrapped paragraphs, code fences, HTML comments, multi-line list items, lines that start with bold), links copied into another file without rewriting, and checks that compare more than they claim. Test the ones that apply. Also the habits in `tools/AGENTS.md`: no copied helpers, `from exc` not `from None`, no dated history in comments, behaviour tests not source greps, typed records, annotations that pass mypy.

## Checks

A docs-only lane runs `make static` (or the named static checks), never a local full `./tools/check.sh`; CI runs `check.sh` on the PR.

Single tests while iterating; `make static` (about 20 s) before `make ready`, which runs it again with the other gates, pushes and runs the full `./tools/check.sh` once through `make remote` only when a change feeds a check that reads private files or REMOTE=1 is given (otherwise the PR opens as a draft and GitHub's check is the gate). Take timings from logs, not re-runs.

**Remote run budget** (owner, 2026-11-25, "Do we need to run so many?" after six runs in one stage). One full `make remote CMD="./tools/check.sh"` per PR; a second only to confirm a fix or to prove a skip change (the same commit twice). No `FULL=1` unless no other run ran every job. Stop a superseded run instead of letting it finish. The box has 2 slots shared by every session, and CI runs `check.sh` anyway. Put this budget in every brief that may run `make remote`.

**Keep the whole log** (owner, 2026-11-25, "let's not have a remote run not leave us details"). Save the output of `make remote`, a full `check.sh` and `make panels` to a file (`> <scratchpad>/<lane>-remote.log 2>&1`), then grep it for `--- .* FAILED` and `ALL PASSED`; never keep only the tail. Name the log path in the report. A run that kept 6 lines left the failing job unknown and the 20-minute run was repeated. `make remote` also saves its own copy (see `docs/pipeline-map/checks-and-remote.md`). Rules the static checks enforce: no script outside hartlib reads a layout data file (data-readers); every new script or file in an output folder gets a map box, through `make map` (pipeline-map-coverage); Python files stay under their size limit (py-sizes); plain writing (ai-speak, public-text). Stop your own background jobs by PID or a pattern holding your worktree path, never `pkill -f` a shared script name: other sessions run the same scripts.

## Review (code only)

After `make ready` opens the PR, run `/code-review medium` (high for the code `/done` step 3 names) on it, send each finding through `finding-verifier`, fix what it confirms with a test each, and ship every fix in one more `make ready` run: collect them all into one push, since every push restarts the ~7-minute GitHub check. List the findings and what you did with each in the report.

## Traps every code brief names (waves 1 and 2)

- A dataclass in a module loaded by path without `sys.modules` fails: use a NamedTuple or TypedDict, or register the module.
- Tests that read source text break when code moves: test behaviour.
- Tests name layout data files through the hartlib constants, never literally.
- When code changes from SystemExit to a named error, update every test that asserts SystemExit (grep every test folder).
- A `checks.toml` `quiet_inputs` list keeps the order `test_manifest_scans` expects.
- The Windows box's venv does not follow `requirements.txt` by itself; a new package is installed there by hand.
- A new worktree may need `git submodule update --init`.
- Run a test that reads the private AnyRail plan once with `ANYRAIL_PLAN` set to a missing path before the push; it must skip, not fail.
- Review agents report to their coordinator, not to `main`.
