# Git and multi-agent conventions (HART)

## Repo

- Public GitHub repo: **[lnevo/hart](https://github.com/lnevo/hart)** (local folder `hart`).  
- Single remote: `origin` → `https://github.com/lnevo/hart.git`  
- `main` is protected on GitHub: PRs and a passing `check` job are required, no force-push or deletion. The owner can bypass this.  
- Secrets never commit: `.env.local`, credentials, private keys.
- `archive/` stays in the tree but `.ignore` hides it from ripgrep (and tools that honour it); search it with `rg --no-ignore <term> archive`.

## Branch naming

| Pattern | Use |
|---------|-----|
| `main` | Accepted SoR + releasable hart panel |
| `agent/<agent-id>/<short-topic>` | Parallel agent worktrees |
| `spike/<topic>` | Time-boxed unknowns |
| `human/<topic>` | Direct human edits |

Examples: `agent/composer/naming-csv`, `spike/duplicate-blocks`.

## Rules

1. One behavior per PR / branch when practical.  
2. Agents do not push to `main`. `main` takes a change only through a pull request whose `check` has passed on its last commit, and since 2026-11-17 that holds for admins too (branch protection "Do not allow bypassing"), so `gh pr merge` from the owner's account is refused until the check passes.  
3. Do not amend pushed commits.  
4. Every agent works in its own worktree, `.claude/worktrees/<topic>/` (`make wt TOPIC=<topic>`, or `isolation: "worktree"` for a subagent). Never edit, commit or switch branches in the main checkout; it stays on `main` for pulls and deploys, and hooks enforce it. A second session in a shared checkout can switch the branch under the first, so its next commit lands on the wrong branch. Merged, clean worktrees are removed after `gh pr merge` and at session start (`tools/agent/worktrees.py`). A detached worktree whose commit is on `origin/main` is removed once it is clean and untouched for a day; a running session's lock keeps it.  
   Cursor: `make wt TOPIC=<topic> AGENT=cursor`, then open that folder as the workspace.  
   The sweep removes a merged worktree and its local branch once the merge is 30 minutes old; one with uncommitted work, and the running session's own, are kept; one with commits after the merged head is removed only when each of them is already on `origin/main` (`git cherry`, or merging it would change nothing) (`make wt-sweep` runs it by hand). At session start the hook prints one summary line that names only the worktrees that need a look; the full lines are in `.claude/logs/worktree-sweep.log`. The same hook moves progress files of finished lanes (two days untouched, topic used by no worktree, open PR or active project page) to `.claude/progress/archive/` (`tools/agent/progress_prune.py`), and warns in one line when the auto-memory folder passes 40 files or has a broken link or index entry. Claude Code locks each `agent-<id>` worktree to its session's pid: the sweep keeps it while that session runs and removes it once the session has exited and the worktree has sat untouched for an hour. A long session clears its own merged agent worktrees with `git worktree unlock <path>` and then `make wt-sweep`, which keeps the checks for uncommitted work and unpushed submodule commits.  
   `make wt` checks out the `model-railroad-skills` submodule the schematic and Layout Editor checks import; in a worktree it did not make (a subagent's), `tools/check.sh` checks it out on its first run.  
   `docs/pipeline-map/pipeline_map.json` merges itself locally by box id and link ends (`tools/ops/merge_pipeline_map.py`, a git merge driver set in the shared git config by `make wt` and the session-start hook; `--install` sets it by hand). GitHub never runs it: when a PR shows a conflict there, merge `origin/main` into the branch locally and run `python3 tools/ops/build_pipeline_map.py --check`. The map pages are built, not committed (`make map` for a local look; [ADR-036](decisions/ADR-036-generated-views-not-committed.md)).  
5. **Who works on what:** `make orient` (`tools/ops/orient.py`) prints the claims, every worktree with commits not on `origin/main` or locked by a running session (branch, last commit, lock, PR), the operating flag, what each layout host last got, the open PRs, and what a host holds that is waiting to come into the repo (one line per source with the command that pulls it in: a PanelPro Store on the Pi or the Mac, the Pi's Operations Pro files, the DecoderPro roster against the Mac copy; the live STS is not checked, and the line says why), asked read-only of the checks the pulls and the deploy gate make; a part it cannot read, or a Pi that does not answer, is one line. Its Overlap section lists every file changed in two or more places (each live worktree's commits since its merge base with `origin/main`, plus its staged, unstaged and untracked files; each open PR's files from the same `gh pr list` call; a PR with a local worktree counts once; the main checkout and merged branches are skipped), naming the branches or PRs; files with a merge driver in `.gitattributes` (`pipeline_map.json`, `STATUS_LOG.md`, `docs/INDEX.md`, `hand_tables.csv`, `py_sizes.csv`) are listed apart as auto-merges, not clashes ([`tools/ops/orient_overlap.py`](../tools/ops/orient_overlap.py); `overlaps_for(paths, exclude_worktree)` answers the same for one branch's files before a push). The session-start hook prints the claims, the worktrees and one Overlap line when a file is changed in two places (local worktrees only, no network). A coordinator reads the Overlap lines for which lane touches which file instead of keeping that list by hand; a file in two lanes still goes to the earlier one, and the later lane waits or merges main in after it. A claim is one line directly under the `Status:` line of an active `wiki/projects/` page, `Claimed: <branch>, <absolute worktree path>, since YYYY-MM-DD HH:MM`; more claims follow each other. `orient.py claim <page>` writes it in your worktree when you start on that project and `orient.py unclaim <page>` removes it in the commit that ends the work, so main never carries one. Orient reads every worktree's copy of the pages, committed or not, so a claim shows as soon as it is written; one whose worktree is gone or on another branch shows as stale, and a malformed or misplaced line, or a claim on a page that is not active, as a problem.  
6. **Close-out:** the definition of done in [`.claude/commands/done.md`](../.claude/commands/done.md) (`/done`).  
7. Update `wiki/` when a decision changes; chat is not SoR. Each status entry is its own file under `wiki/status/` ([README](status/README.md), ADR-038), so branches that each add an entry do not conflict and two that edit one entry get a real conflict; `wiki/STATUS.md` is built (`make status`) and not committed. A branch from before the split that edited `wiki/STATUS.md` moves its edit into the entry file and runs `git rm wiki/STATUS.md`. `wiki/STATUS_LOG.md` still merges with git's union driver (`.gitattributes`).

## Hooks

A fresh clone needs `git config core.hooksPath .githooks` to enable the pre-commit tracked-file check.

## Where agent instructions live

`AGENTS.md` is the one source of rules. Everything else points at it, so a rule changes in one place. `tools/audit/check_agent_docs.py` (part of `tools/check.sh`) fails if these files name a path that no longer exists.

| What | Where | Holds |
|------|-------|-------|
| Rules for every tool | `AGENTS.md` | Daily commands, the close-out rule, owner, subagents, do-nots; capped by `check_agent_docs.py` |
| Close-out steps | `.claude/commands/done.md` | The definition of done; Cursor's close-out points at it |
| Scoped rules | `cats/`, `jmri/`, `tools/schematic/`, `ops/hart-ops/` `AGENTS.md` | Only what applies under that folder; loaded when a session works there |
| Cursor | `.cursor/rules/close-out.mdc`, `.cursor/commands/done.md`, `.cursor/hooks.json`, `.cursor/hooks/main_guard.py` | Pointers, plus a hook that runs the Claude guard's rules on every shell command; Cursor also reads `AGENTS.md`. When a rule or guard changes, carry it here too |
| Claude Code | `.claude/commands/done.md`, `.claude/settings.json`, `.claude/hooks/main_guard.py` | Pointer and guard hook; Claude Code reads `AGENTS.md` |
| Subagents | `.claude/agents/` | The project agents; see below |
| Facts and decisions | `wiki/`, ADRs | Never in chat or tool memory |
| Build handoffs | `docs/benchwork/helix/` | Update `HART_Neville_Helix_BUILD_STATUS.md` in place; old handoffs go to `archive/history/helix/` |
| Tool memory | Per-machine, outside git | Preferences only. Anything every agent needs goes in `AGENTS.md` or an ADR |
| Submodules | Their own repos | `external/*` rules travel with each repo |

## Claude subagents

| Agent | Use for | Access | Model |
|-------|---------|--------|-------|
| `site-builder` | Website pages and data | Edits in a worktree, ships with `make ready`, no merge or publishing | Sonnet |
| `site-reviewer` | Website review; name the lens in the brief | Read-only | Sonnet |
| `panel-tracer` | Why the panel or signals behave as they do | Read-only | Opus |
| `repo-auditor` | Dead code, stale docs, structure | Read-only | Sonnet |
| `archive-researcher` | History and archive proposals | Read-only | Sonnet |
| `voice-reviewer` | Any text against the writing rules | Read-only | Sonnet |
| `schematic-builder` | Schematic, panel and device-map code | Edits in a worktree, ships with `make ready`, no merge | Opus |
| `finding-verifier` | One claimed bug against the code | Read-only | Sonnet |
| `data-lane` | One ADR-039 data-masters lane outside `tools/schematic/` and `tools/hartlib/` | Edits in a worktree, ships with `make ready`, no merge | Opus |
| `tool-fixer` | Splits with no change in behaviour, and fixes to repo tools and checks where no other agent owns the paths | Edits in a worktree, ships with `make ready`, no merge | Opus |

- The definition holds the standing rules. The brief holds only the goal, the scope and what is already ruled out.
- Editing agents ship their own work with `make ready` (`tools/agent/ready.py`): it commits the files they name, merges `origin/main` only when needed, regenerates and checks, pushes, runs `make remote` unless the change is light, and opens the PR; it never merges, deploys or touches a host. The coordinator writes the attribution lines to `.claude/ready-attribution.json` in the main checkout (gitignored) or names a file in `HART_READY_ATTRIBUTION`. The main session merges (`make land PR=N`, `tools/agent/land.py`, which the guard blocks in subagents), deploys and verifies. `.claude/hooks/subagent_guard.py` blocks every other git and gh write, deploys and host actions in subagents. It reads only the command line, so the git and gh calls `make ready` makes are held by `ready.py`'s own rules. `Bash` can still write, so read-only also rests on the agent's instructions.
- Split a job likely to pass 50 turns into stages. At `maxTurns` the agent stops with partial output and can be resumed.
- Agents that edit files may run in parallel, each in its own worktree, when they touch different files and do not need each other's unmerged work (`isolation: "worktree"` branches from `main`, not the current branch). One agent at a time owns a shared generated output (`tables.xml`, panels, `docs/INDEX.md`); the others regenerate it on rebase. Heavy builds and checks go to the Windows box (`make remote`). Mac-only PanelPro jobs (`make panelpro-test`, SML discovery, screenshots) run one at a time across all sessions.
- A subagent with `isolation: "worktree"` has no submodules; plugin edits (`external/model-railroad-skills`) stay in the coordinator's own worktree.
- Add an agent only when a task recurs. Do not add agents for deploys or live hardware; those stay visible in the main session.

## JMRI command watcher

`jmri/layouts/hart/scripts/jmri_cmd_watcher.py` is a standing part of the Pi Start Up. The package also copies the file to the Mac and Windows, but it is not in their Start Up lists, so it does not run there. It runs any file dropped at `/tmp/jmri_cmd.py` inside JMRI and writes the result to `/tmp/jmri_cmd.out`, which gives agents a live way to query JMRI. That code has JMRI's full access, so the rules on field turnouts and `track/cmd` apply to it, and subagents cannot reach it: their guard (`.claude/hooks/subagent_guard.py`) allows `ssh` only for plain read-only commands (no quotes, `=`, `$`, redirects or grouping; a short list of programs that cannot write). The guard is a guardrail against mistakes, not a security boundary.

## Layout env

```bash
export JMRI_LAYOUT=hart
```

## Cursor Cloud Agents (secondary tool)

Cloud agents clone **GitHub**, not your Mac disk. Uncommitted local work is invisible until push.

1. Confirm GitHub + **hart** are linked: [cursor.com/dashboard/cloud-agents](https://cursor.com/dashboard/cloud-agents) (Environments → select `lnevo/hart`).  
2. Integrations: [cursor.com/dashboard/integrations](https://cursor.com/dashboard/integrations).  
3. Prefer Agents Window → env dropdown **Cloud**, or `/in-cloud` for a cloud subagent.  
4. Repo env defaults: [`.cursor/environment.json`](../.cursor/environment.json) installs what CI installs and runs `./tools/check.sh` once.  
5. Before handoff: commit + `git push -u origin HEAD` on an `agent/...` branch (never push to `main` from agents).

GUI CATS / JMRI on the Mac stays **local**. Cloud work = XML/scripts/docs + static verify; human launches CATS on the layout host.
