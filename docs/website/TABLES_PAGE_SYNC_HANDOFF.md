# Handoff: keep the tables file page in step with tables.xml

Written 2026-11-12. Built 2026-11-12 on `agent/claude/tables-page-sync` (`www/scripts/tables_page.py`); awaiting the owner's review in the browser, then deploy. Owner request: the public page
[`www/behind/tables-file.html`](../../www/behind/tables-file.html) ("The Tables File: One File That Is the
Railroad") has out-of-date facts, and it should be tied to changes in
`jmri/layouts/hart/output/tables.xml` so it cannot drift again. The owner calls the table browser
on that page "an excellent resource". Keep it, and make sure it always shows the current file.

## Goal

1. Every number or version on the page that describes `tables.xml` comes from the file at site build
   time. It is not typed into the HTML by hand.
2. The table browser's data is rebuilt from the current `tables.xml` on every site build and deploy.
3. A check fails (in `./tools/check.sh` or the portal build, and so in CI) when the page would show a
   fact that no longer matches the file.
4. Fix the facts that are wrong today.

## Known or suspected stale facts (verify each against the file and the source)

These are on the page as of 2026-11-12. Treat every one as unverified until checked:

- "stored by PanelPro **5.15**". The owner believes this is wrong. The profile's web home page is
  described elsewhere as a copy of JMRI 5.16's stock page. Read the version JMRI wrote into
  `tables.xml` (the root element and the file-history section) and use that. Do not assume 5.16.
- "about 2.2 MB and 29,068 lines long, and it has 27 top-level sections".
- The drawn-to-scale Objects/Panels bar, and "about two thirds of the file is objects, then about one
  third is panels".
- The section table (Sensors … File history). Check it against the real top-level sections and
  their order.
- "55 layout blocks get by on 43 detectors", and the examples of shared detectors (yard tracks S-1
  to S-4 split into West/East halves sharing "BS S-1"; OS Switch 37 and Track McKeesport).
- "Add 126 of those and you have the map" (the block count).
- The example XML excerpts: sensor `MS2S100` / "BS K-1", the block for OS Switch 13, the
  `Mast 2036 → Mast 38LB` Signal Mast Logic, the turnout "Switch 35" with its feedback sensors.
  Each must still exist in the file in that form, or be replaced with one that does.
- "The CTC data generator writes the CTC data, including the 20 columns of code buttons". Other pages
  say the lever machine is twenty columns. Confirm both against the CTC data in the file.
- The LogixNG section: "Hide windows on start", in the Initialization Table, "four ConditionalNGs,
  each with one stock action", and the rows of that table.
- "Two older-style logic items" (Logix count) and any other counts in the section table text.

Read the whole page. There may be more numbers than these.

## Approach (suggested, the agent decides the details)

1. Find where the table browser's data comes from. It is a generated file that the page fetches.
   Search `tools/`, `www/scripts/` and `www/scripts/prepare_github_pages.py` for its producer. Find
   out whether the site build regenerates it from `tables.xml` or whether it is a committed snapshot.
   If it is a snapshot, make the build regenerate it.
2. Write one small extractor that reads `tables.xml` and emits a facts JSON: JMRI version, size,
   line count, top-level sections in order with their byte share, object/panel split, counts of
   blocks, layout blocks, detectors, Logix, LogixNG ConditionalNGs, CTC columns, and so on.
   Reuse any existing parser in the repo before writing a new one.
3. Make the page read those facts. Either fill marked placeholders at build time (preferred, so the
   numbers are in the HTML for readers without JS and for share previews), or render from the JSON
   on load like the browser does. Keep the prose, but let the numbers come from the data.
4. For the hand-picked XML excerpts, either pull them from the file by name at build time, or keep
   them hand-written and add a check that each named object still exists with the shown values.
5. Add the check to `./tools/check.sh` (or `check_portal_build.py`) so a `tables.xml` change that
   makes the page wrong fails CI. Add a test for the extractor.
6. Fix today's wrong facts as part of this, through the generated path, not by editing the
   numbers by hand.

## Rules that apply

- Work in a worktree (`make wt TOPIC=tables-page-sync`). Never edit the main checkout.
- Do not run table scripts or touch `tables.xml` with PanelPro or CATS open. This job should only
  *read* `tables.xml`.
- `prepare_github_pages.py` and the deploy scripts are large. Follow AGENTS.md "Working on
  existing scripts": add tests for the behaviour you change.
- Site voice: plain summaries and facts, no narrative or justifying tone, and JMRI is a stock install
  stated as fact. Never spell out what HART stands for.
- Check the page by eye with `python3 tools/ops/screenshot.py www/behind/tables-file.html` (served,
  so the browser loads; `file://` shows "Couldn't load the tables browser", which is expected), and
  open it in the browser for the owner to review before merging.
- Run `/code-review medium` before merging. Deploy with `./www/scripts/deploy_hartrailroad.sh` from the
  worktree (the `media/` and `ops/car-cards` links must be present) and compare the Build counts.

## Done when

- The page shows the current JMRI version and current counts, all from `tables.xml`.
- The table browser data is rebuilt from `tables.xml` on every site build.
- Changing a counted thing in a copy of `tables.xml` makes the check fail until the site is rebuilt.
- The owner has reviewed the page in the browser, and it is deployed.
