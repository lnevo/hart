# HART pipelines

One page per **source → generated artifact** flow. Runtime desks (PanelPro, CATS, USS, MQTT broker) and host deploy (`sync_hart_package.sh`) are not pipelines.

NextTrain / Google Sheets is **not** on this list (abandoned for hart).

| # | Pipeline | Status | Guide |
|---|----------|--------|-------|
| 1 | JMRI AnyRail panel | Tool; frozen for hart | [jmri-anyrail.md](jmri-anyrail.md) |
| 2 | Public names + comments | Live | [public-names.md](public-names.md) |
| 3 | Digicon signal beans | Live | [digicon-signal-beans.md](digicon-signal-beans.md) |
| 4 | Native SML + NX | Live | [native-sml.md](native-sml.md) |
| 5 | CATS Digicon Masters | Live | [cats-masters.md](cats-masters.md) |
| 6 | USS CTC machine | Live (not with CATS) | [uss-ctc.md](uss-ctc.md) |
| 7 | Dispatcher System graph | Live | [dispatcher-system.md](dispatcher-system.md) |
| 8 | Wiring documentation | Live | [wiring-docs.md](wiring-docs.md) |
| 9 | LCOS Nano firmware | Live (other repo) | [lcos-firmware.md](lcos-firmware.md) |
| 11 | Speed matching | Parked | [speed-matching.md](speed-matching.md) |
| 12 | Car cards | Live (hart-ops, ADR-010) | [car-cards.md](car-cards.md) |
| 13 | Waybills | Live (hart-ops, ADR-010) | [waybills.md](waybills.md) |
| 14 | STS | Live (`external/sts-docker-data`) | [sts.md](sts.md) |
| 15 | Ops publications | Live (hart-ops, ADR-010) | [ops-publications.md](ops-publications.md) |
| 16 | Industry routing | Live (hart-ops, ADR-010) | [industry-routing.md](industry-routing.md) |
| 17 | Website | Live | [`www/README.md`](../../www/README.md) |
| 18 | MQTT mimic | Tool | [mqtt-mimic.md](mqtt-mimic.md) |

**Do not** encode one-off table deletes into immortal leftover lists (`cleanup_uss_ctc_leftovers.py` and friends). That is a review of pipeline 2, not a 17th flow.
