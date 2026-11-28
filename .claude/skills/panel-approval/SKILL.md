---
name: panel-approval
description: Use before asking the owner to approve a panel, CATS desk, schematic or other drawing, or a published look; when a panel, desk or drawing change is ready for the owner to look at; when an approval fingerprint (check_approved.py, approved_*.sha256) changed; or before publishing a new look on the site.
---

# Before asking for an approval

## Ask only for a new decision

- Fingerprint unchanged (`python3 tools/schematic/check_approved.py --check`): nothing is needed.
- Small change with a stated visible effect (a track loses one anchor, a label moves): record it yourself (`check_approved.py --approve <key>`) and send a before/after crop of what changed, for example a pixel diff of `www/assets/layout/HART_le_schematic.png` against main. If the permission system blocks the command, give it to the owner to run.
- A refresh of something already published (a regenerated film, a page with the same look) or a step of a plan already reviewed: build, review, merge and deploy, then report. Stated constraints still hold.
- Ask for a new look or drawing, layout moves, a design choice, a live write or a deletion.

## Before building

- When the owner picks a next step that is theirs to decide (for example "let's work on #2", ordering the source-data exceptions list), review it with them first in batched multiple-choice questions, then edit. On 2026-11-20 rows were edited at once and the owner said "I thought we'd review, you just started going".
- Owner words behind the small-change rule: "skip the approvals or just grant them, or send me screenshots" (2026-11-20). Behind the data-first rule: "stop making me quit, tables.xml changes don't require quitting, only reloading without a store. Either way you should be able to validate the x-over directions from the anyrail file without rebuilding things. Please validate before we waste a ton of time doing full builds" (2026-11-16).
- Check switch and crossover facts in the data first (AnyRail plan, `jmri/layouts/hart/data/switches.csv`, the live panel). Report them and build after the owner confirms.
- Approved track geometry (grid, rows, cuts, anchors) is fixed during label work. Check that a label step changed no track coordinate. If labels do not fit, change the label method or ask; never stretch the track. A remark in a hand-off is not a request to change the layout.
- Labels, readouts and buttons may go in any spot that fits cleanly: try ranked candidate spots with a no-overlap check and take the first clean one. Do not ask the owner for a placement rule.

## Show it

- Panel or `tables.xml`: first check that `~/JMRI_UserFiles/tables.xml` on the Mac matches main's (no unpulled Store) and keep a dated backup beside it. Install the exact file the approval covers, plus any new resources, then quit and relaunch PanelPro yourself (`panelpro` skill). For `le-panel` that is the live `tables.xml` after sandbox SML discovery, not the discovery base. Say if it is view-only (no discovery run yet) and that it must not be Stored.
- Never ask the owner to quit PanelPro between review rounds; they reload the panel without a Store.
- A desk or panel look or fit on a layout host: offer to copy the built files to the host the owner uses, with backups of the old ones, how to roll back, and a warning that a deploy from main overwrites them. Copy only after a yes, and the operating flag still applies. Tests, reviews, the PR and a normal deploy follow the owner's verdict. The owner (2026-11-18, a CATS desk fit on the Windows box): "that was nice to see the change quickly and do the work after"; they judge a look on the real screen, not from tests or renders.
- Site pages and mockups: build with `python3 www/scripts/prepare_github_pages.py`, serve the output with `python3 -m http.server`, and open the URL in the browser. Screenshots are for your own checks only: "stop rendering png's just open the html in the browser" (owner, 2026-11-09). Stop the server when done.

## Ask

- Fetch main first. If another session changed the same sheet, its approved version is the baseline.
- On 2026-11-14 a second session published a schematic revision after a preview was shown only here; the owner said "The other session is approved. You didn't show me your plan here." Several sessions work on the schematic, so an approval given in another session wins over anything not shown here.
- State in chat the exact steps and what will change, not only in a question dialog, and wait for an explicit yes. An impatient reply is not a yes: restate the plan briefly and ask once.
- Approvals of a new look are the owner's to record.

## Sources

- `tools/schematic/check_approved.py`, `tools/schematic/approval.py`, `jmri/layouts/hart/data/schematic/approved_*.sha256`
- `panelpro` and `operating-flag` skills
