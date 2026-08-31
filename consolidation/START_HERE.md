# Good morning — start here

## 1. Open the browse portal

```
/Users/lnevo/hart/consolidation/index.html
```

Categories: pipelines, CATS, MQTT, wiring, LCOS, audits, ADRs, archive taxonomy, repos.

## 2. Decisions

**Recorded:** [`DECISIONS_RECORDED.md`](DECISIONS_RECORDED.md) (D1–D10, D2a–f, ADR-set)

**Next work:** [`NEXT_ROUND.md`](NEXT_ROUND.md) — bench freeze active; build in consolidation + hart-ops only

## 3. Validators

```bash
cd /Users/lnevo/hart
bash consolidation/validators/run_all.sh
```

Tier B manual checklist: [`validators/TIER_B_MANUAL_SMOKES.md`](validators/TIER_B_MANUAL_SMOKES.md)

## 4. Workspace rule

All review work under `consolidation/` — live sources and **`~/Desktop/HART/` read-only**. No Pi deploy or cutover until a separate cleanup project (D12).

Agent rule: `.cursor/rules/consolidation-workspace.mdc`

## 5. Tree at a glance

| Path | Contents |
|------|----------|
| `index.html` | Browse portal |
| `manifest.yaml` | Pipelines + Tier A validators |
| `wiki/pipelines/` | Draft runbooks with SoR tables |
| `wiki/decisions/` | Accepted consolidation ADRs |
| `wiki/archive/INDEX.md` | Desktop taxonomy (P4 pending) |
| `wiki/REPOS.md` | Submodule recipe (P3 pending) |
| `validators/` | Automated + Tier B smokes |
| `audits/` | Reports + validator logs |
| `sor/` | Names, wiring crosswalk, desktop CSV |
| `cross-repo/` | Submodule pins, hart-ops migration docs |
| `external/` | Live submodule checkouts (sibling repos) |

Rebuild portal: `python3 consolidation/scripts/build_site.py`
