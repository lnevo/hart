# Pipeline guides (consolidation drafts)

Draft runbooks with **SoR tables** and consolidation notes. Live [`wiki/pipelines/`](../../../wiki/pipelines/) stays read-only until explicit promotion.

Open the [browse portal](../../index.html) for HTML navigation.

| # | Guide | Tier | Consolidation notes |
|---|-------|------|---------------------|
| 1 | [jmri-anyrail](jmri-anyrail.md) | — | **Frozen for hart** — not the live path |
| 2 | [public-names](public-names.md) | A | D2 single SoR; merged map in `sor/names/` |
| 3 | [digicon-signal-beans](digicon-signal-beans.md) | A | Wiring crosswalk validator |
| 4 | [native-sml](native-sml.md) | A | 93 destinations invariant |
| 5 | [cats-masters](cats-masters.md) | B | CTC + ABS hold copies |
| 6 | [uss-ctc](uss-ctc.md) | B | Mutually exclusive with CATS CTC |
| 7 | [dispatcher-system](dispatcher-system.md) | B | Stage 1 graph |
| 8 | [wiring-docs](wiring-docs.md) | A | Crosswalk gap documented |
| 9 | [lcos-firmware](lcos-firmware.md) | B | Submodule pin in `cross-repo/lcos/` |
| — | [mqtt-mimic](mqtt-mimic.md) | B | Cross-cutting QA (pipelines 3/5/9) |
| 11 | [speed-matching](speed-matching.md) | — | Parked |
| 12 | [car-cards](car-cards.md) | C | **hart-ops** — car SoR |
| 13 | [waybills](waybills.md) | C | **hart-ops** |
| 14 | [sts](sts.md) | C | `external/sts-docker` + `sts-helpers` |
| 15 | [ops-publications](ops-publications.md) | C | **hart-ops** |
| 16 | [industry-routing](industry-routing.md) | C | **hart-ops** |

**Project (not numbered pipeline):** [cats-integration](../projects/cats-integration.md)

Registry: [`manifest.yaml`](../../manifest.yaml) · decisions: [`DECISIONS_RECORDED.md`](../../DECISIONS_RECORDED.md)
