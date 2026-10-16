# HART consolidation workspace

Parallel review and refactor track for the HART model railroad. **Live ops are untouched.**

## Start here

| Open in browser | Purpose |
|-----------------|---------|
| **[index.html](index.html)** | Browse categories — JMRI, CATS, MQTT, STS, wiring, pipelines |

| Read first | Purpose |
|------------|---------|
| [OBJECTIVE.md](OBJECTIVE.md) | Charter and success criteria |
| [AGENTS.md](AGENTS.md) | Rules for humans and AI agents |
| [DECISIONS_PENDING.md](DECISIONS_PENDING.md) | **Approve these decisions** (batch) |
| [LIVE_SOURCES.md](LIVE_SOURCES.md) | Live paths — do not edit |
| [manifest.yaml](manifest.yaml) | Pipeline registry + validators |

## Layout

```
consolidation/
  index.html              ← browse portal
  html/                   ← generated pages from wiki
  manifest.yaml
  sor/                    ← proposed canonical artifacts (drafts)
  validators/             ← read-only checks
  audits/                 ← validator output + review reports
  scripts/                ← refactored copies (not live)
  wiki/                   ← draft guides + ADRs
  cross-repo/             ← LCOS, STS specs
```

## Run validators

```bash
cd /Users/lnevo/hart
bash consolidation/validators/run_all.sh
```

Reports land in `consolidation/audits/`.
