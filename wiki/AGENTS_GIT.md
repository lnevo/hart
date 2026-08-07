# Git and multi-agent conventions (HART)

## Repo

- Public GitHub repo for this workspace (Panel / HART).  
- `main` is protected by convention: merge only with green checks + human review.  
- Secrets never commit: `.env.local`, credentials, private keys.

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
