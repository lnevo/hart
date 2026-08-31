# Good morning — start here

## 1. Open the browse portal

```
/Users/lnevo/hart/consolidation/index.html
```

**Desktop/HART F-root (124 files):** [`html/archive/f-root-index.html`](html/archive/f-root-index.html) — browse, archive, and skip rows with local `file://` links.

Categories: pipelines, CATS, MQTT, wiring, LCOS, audits, ADRs, archive, repos, backlog.

## 2. Build status

**Backlog:** [`BACKLOG.md`](BACKLOG.md)  
**Decisions:** [`DECISIONS_RECORDED.md`](DECISIONS_RECORDED.md) (D1–D12)  
**Next work:** [`NEXT_ROUND.md`](NEXT_ROUND.md)

## 3. Validators

```bash
cd /Users/lnevo/hart
bash consolidation/scripts/mirror_all_live.sh   # refresh mirrors + validate
# or validators only:
bash consolidation/validators/run_all.sh
```

**Workspace map:** [`WORKSPACE.md`](WORKSPACE.md) · **Gaps:** [`audits/standalone-gaps.md`](audits/standalone-gaps.md)

Tier B manual checklist: [`validators/TIER_B_MANUAL_SMOKES.md`](validators/TIER_B_MANUAL_SMOKES.md) (reference during build)

## 4. Workspace rule

All build work under `consolidation/` — live sources and **`~/Desktop/HART/` read-only**.

Agent rule: `.cursor/rules/consolidation-workspace.mdc`

## 5. Tree at a glance

| Path | Contents |
|------|----------|
| `index.html` | Browse portal |
| `html/archive/f-root-index.html` | **F-root file browser** |
| `BACKLOG.md` | Build checklist |
| `manifest.yaml` | Pipelines + Tier A validators |
| `wiki/pipelines/` | Draft runbooks with SoR tables |
| `wiki/decisions/` | Consolidation ADRs |
| `wiki/archive/INDEX.md` | Desktop taxonomy |
| `wiki/REPOS.md` | Submodule recipe |
| `validators/` | Automated + Tier B smokes |
| `audits/` | Reports + validator logs |
| `sor/` | Names, wiring crosswalk, desktop CSV |
| `cross-repo/` | Submodule pins, hart-ops migration docs |
| `consolidation/external/` | Git submodules + runtime mirrors |
| `WORKSPACE.md` | Complete standalone tree map |

Rebuild portal: `python3 consolidation/scripts/build_site.py`
