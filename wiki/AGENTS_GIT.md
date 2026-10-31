# Git and multi-agent conventions (HART)

## Repo

- Public GitHub repo: **[lnevo/hart](https://github.com/lnevo/hart)** (local folder `hart`).  
- Single remote: `origin` → `https://github.com/lnevo/hart.git`  
- `main` is protected by convention: merge only with `tools/check.sh` passing and human review.  
- Secrets never commit: `.env.local`, credentials, private keys.

## Cursor Cloud Agents

Cloud agents clone **GitHub**, not your Mac disk. Uncommitted local work is invisible until push.

1. Confirm GitHub + **hart** are linked: [cursor.com/dashboard/cloud-agents](https://cursor.com/dashboard/cloud-agents) (Environments → select `lnevo/hart`).  
2. Integrations: [cursor.com/dashboard/integrations](https://cursor.com/dashboard/integrations).  
3. Prefer Agents Window → env dropdown **Cloud**, or `/in-cloud` for a cloud subagent.  
4. Repo env defaults: [`.cursor/environment.json`](../.cursor/environment.json).  
5. Before handoff: commit + `git push -u origin HEAD` on an `agent/...` branch (never push to `main` from agents).

GUI CATS / JMRI on the Mac stays **local**. Cloud work = XML/scripts/docs + static verify; human launches CATS on the layout host.

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
2. Agents do not push to `main`.  
3. Do not amend pushed commits.  
4. Prefer `git worktree` for parallel agents on the same machine.  
5. **Close-out:** the definition of done in [`AGENTS.md`](../AGENTS.md).  
6. Update `wiki/` when a decision changes; chat is not SoR.

## Hooks

A fresh clone needs `git config core.hooksPath .githooks` to enable the pre-commit tracked-file check.

## Where agent instructions live

`AGENTS.md` is the one source of rules. Everything else points at it, so a rule changes in one place. `tools/audit/check_agent_docs.py` (part of `tools/check.sh`) fails if these files name a path that no longer exists.

| What | Where | Holds |
|------|-------|-------|
| Rules for every tool | `AGENTS.md` | Commands, close-out, do-nots |
| Scoped rules | `cats/AGENTS.md` | Only what applies under that folder |
| Cursor | `.cursor/rules/close-out.mdc`, `.cursor/commands/done.md` | Pointers only; Cursor also reads `AGENTS.md` |
| Claude Code | `.claude/commands/done.md` | Pointer only; Claude Code reads `AGENTS.md` |
| Subagents | `.claude/agents/` | Five project agents; see below |
| Facts and decisions | `wiki/`, ADRs | Never in chat or tool memory |
| Build handoffs | `docs/benchwork/helix/` | Update `HART_Neville_Helix_BUILD_STATUS.md` in place; old handoffs stay in `docs/benchwork/helix/history/` |
| Tool memory | Per-machine, outside git | Preferences only. Anything every agent needs goes in `AGENTS.md` or an ADR |
| Submodules | Their own repos | `external/*` rules travel with each repo |

## Claude subagents

| Agent | Use for | Access | Model |
|-------|---------|--------|-------|
| `site-builder` | Website pages and data | Edits, no publishing | Sonnet |
| `site-reviewer` | Website review; name the lens in the brief | Read-only | Sonnet |
| `panel-tracer` | Why the panel or signals behave as they do | Read-only | Opus |
| `repo-auditor` | Dead code, stale docs, structure | Read-only | Sonnet |
| `archive-researcher` | History and archive proposals | Read-only | Sonnet |

- The definition holds the standing rules. The brief holds only the goal, the scope and what is already ruled out.
- The main session commits, pushes, deploys and verifies. `.claude/hooks/subagent_guard.py` blocks those commands in subagents, but `Bash` can still write, so read-only also rests on the agent's instructions.
- Split a job likely to pass 50 turns into stages. At `maxTurns` the agent stops with partial output and can be resumed.
- Run builders one at a time. `isolation: "worktree"` branches from `main`, not the current branch, so it suits only work that does not depend on unmerged changes.
- Add an agent only when a task recurs. Do not add agents for deploys or live hardware; those stay visible in the main session.

## Layout env

```bash
export JMRI_LAYOUT=hart
```
