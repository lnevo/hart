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
| Subagents | None defined | Add one only when a task recurs |
| Facts and decisions | `wiki/`, ADRs | Never in chat or tool memory |
| Build handoffs | `benchwork/helix/` | Update `HART_Neville_Helix_BUILD_STATUS.md` in place; old handoffs stay in `docs/helix/history/` |
| Tool memory | Per-machine, outside git | Preferences only. Anything every agent needs goes in `AGENTS.md` or an ADR |
| Submodules | Their own repos | `external/*` rules travel with each repo |

## Layout env

```bash
export JMRI_LAYOUT=hart
```
