# Git and multi-agent conventions (HART)

## Repo

- Public GitHub repo: **[lnevo/hart](https://github.com/lnevo/hart)** (local folder may be named `Panel`).  
- Single remote: `origin` → `https://github.com/lnevo/hart.git`  
- `main` is protected by convention: merge only with green checks + human review.  
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
5. Irreversible ops (Pi deploy, Sheets push) stay human-gated; not in phases 0–2.  
6. Update `wiki/` when a decision changes; chat is not SoR.

## Layout env

```bash
export JMRI_LAYOUT=hart
```
