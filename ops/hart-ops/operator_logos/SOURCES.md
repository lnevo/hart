# Logo and template sources

Where every logo under `operator_logos/` came from is in the archive catalogue,
[`www/scripts/archive_catalogue.csv`](../../../www/scripts/archive_catalogue.csv): one row of collection `logo` per
file, with its credit, source link, how sure the credit is (`credit_confidence`), the licence or terms (`rights`)
and, for a copy made here, the row it was made from (`derived_from`). The columns are described in
`archive_catalogue.columns.csv`. Add a row there for a new logo; the catalogue is the one place for logo credits
(owner, 2026-11-25).

The logos identify real railroads and industries on a model railroad's cards, waybills, sticker sheets and website;
they are trademarks of their owners and are used here for reference only. Any owner can ask for a file to be
removed. "Public domain" for a Wikimedia Commons logo is the Commons copyright tag; the trademark still applies.

Every logo was checked on 2026-11-09 by comparing each image by eye, by checksum and against Wikipedia and Commons
file pages.

## Files that are not logos

| File | What it is |
|---|---|
| `downloads/industry_logo_stickers.pdf`, `downloads/industry_logo_stickers_preview.png` | Sticker sheet on the Apostrophe Games poker-size layout, filled with the CSX, Aristech, Calgon Carbon, A. Stucki, Ferrellgas and Kosmos logos; the PNG is a render of the PDF. Made here |
| `party_logo_map.json` | Made here: which logo each industry party uses |

## Templates

The car cards, waybills and sticker sheets are printed on Apostrophe Games' free poker-size
sticker template (9 per US Letter page): https://www.apostrophegames.com/pages/blank-sticker-templates

It is their file and their page states no terms for passing it on, so it is **not in the repo**.
The card tools read the Word version from `card_pipeline/assets/Poker Size Sticker Sheet Template.docx`
(gitignored); download it once from that page and save it under that name. Without it the tools
stop and print the link. The PDF version is not used.
