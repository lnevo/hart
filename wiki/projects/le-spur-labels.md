# LE spur names beside their tracks (2026-11-27)

Status: done (2026-11-27)
Coordinator: hart-6d, since 2026-11-27 18:13
Dashboard: https://claude.ai/artifact/3RUni5hx1sRXCYarGXYQxa

The owner asked on 2026-11-27 for the Layout Editor names of 101 Spur 1, 101 Spur 2 and 103 Spur to stand next to their tracks, with the block contents icons moved outward. Layout Editor only: the CATS desks and the schematic stay as they are (owner). The rule is the Main band's `names_first` ([schematic-panels](../pipelines/schematic-panels.md)). Track 101-103's icon is left out; the owner does not need it shown. The owner approved the rendered look, with the Upper band 6 px higher on the combined panel.

## Steps

| Step | What |
|------|------|
| LS-L1 | `names_first` in schematic-maps 0.1.55 and the Main band's list in `preferences.json` |
| LS-L2 | `make panels CHECK=1`, `./tools/check.sh`, one `make remote` |
| LS-L3 | `/code-review high`, findings through `finding-verifier` |
| LS-L4 | Owner approval of the LE look (`approved_le_panel.sha256`) |
| LS-L5 | Merge, main's push run of `check` |
| LS-L6 | `make panelpro-test` on the Mac |
| LS-L7 | Deploy to the Pi and Windows |
