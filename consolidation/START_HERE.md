# Good morning — start here

## 1. Open the browse portal

**Double-click or open in Chrome:**

```
/Users/lnevo/hart/consolidation/index.html
```

Dark-themed portal with categories: JMRI, CATS, MQTT mimic, STS, wiring, LCOS, audits, ADRs.

## 2. Decisions — recorded

All ten approved **2026-08-31:** [`DECISIONS_RECORDED.md`](DECISIONS_RECORDED.md)

Next work: [`NEXT_ROUND.md`](NEXT_ROUND.md)

## 3. Validator status

Last run: **ALL PASSED** (see `audits/latest.log`).

Re-run anytime:

```bash
cd /Users/lnevo/hart
bash consolidation/validators/run_all.sh
```

## 4. What changed overnight

- **New folder:** `hart/consolidation/` — all review work lives here
- **Live sources untouched:** `jmri/`, `cats/`, `tables/`, `docs/wiring/`, live `wiki/`
- **Agent rule:** `.cursor/rules/consolidation-workspace.mdc`

## 5. Tree at a glance

| Path | Contents |
|------|----------|
| `index.html` | Browse portal |
| `DECISIONS_PENDING.md` | Batch approvals |
| `manifest.yaml` | 15 pipelines + validators |
| `wiki/pipelines/` | Draft guides with SoR headers |
| `wiki/decisions/` | 4 draft ADRs |
| `validators/` | Read-only checks (wraps live audit) |
| `audits/` | Reports + validator logs |
| `sor/names/` | CSV snapshots |
| `scripts/` | build_site, sync guides, cleanup copy |

Nothing was committed (per your git preferences).
