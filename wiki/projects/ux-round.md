# Website UX round (2026-11-28)

Status: done (2026-11-28)
Dashboard: https://claude.ai/artifact/NZ8CuEbwCs7VmhGmfLxodA

Fixes from the first Website UX card ([report-cards](../report-cards.md#website-ux), 6.8 of 10 on 2026-11-28). The owner asked for the round on 2026-11-28; the rescore after the deploy closes it.

## Owner's choices (2026-11-28)

- The crew hub is **Crew sheets** in the nav, its title and the home page. `docs/` stays Publications.
- The five section links show inline in the header at 980 px and wider; the menu button stays on narrower screens.
- The home page keeps both the hero buttons and the door cards' Explore buttons. Do not flag the repeat again.
- The parked guides leave the Operations menu; their pages stay up by link.

## Lanes

| Lane | Scope | Agent | Ships |
|------|-------|-------|-------|
| UX-L1 Pages without JavaScript | Header home and section links, crew sheets, the primer and the JS-built pages show content or a `<noscript>` line; `HARTCrew.page` shows an error when its data fails | `site-builder`, opus | site |
| UX-L2 Page descriptions | A one-sentence meta description on the 52 pages without one | `site-builder`, sonnet | site |
| UX-L3 Contents lists | "On this page" lists and h2 ids on the long library articles, crew sheets, `build/` and the live guides | `site-builder`, sonnet | site |
| UX-L4 Names, nav and gloss | The four choices above; first-screen gloss on `layout/`, `roster/`, `history/` and the crew sheets; nav ids for `ap-exam`, drop `tools` | `site-builder`, opus | site |
| UX-L5 Links and build check | `build-status` link, repo paths in the guides, `/library/`, the raw `.md`, a `check_portal_build.py` rule for links to `SKIP_FILES`, archive image sizes, table scroll, viewport on stubs | `site-builder`, opus | site |

## Result (2026-11-28)

All five lanes merged: UX-L3 #1380, UX-L4 #1384, UX-L5 #1387, UX-L2 #1381, UX-L1 #1385; the round page was #1378. hart-4e deployed the site from `5c392d9f`. The rescore put the Website UX card at 7.3 (6.8 before); what is left is listed on the [card](../report-cards.md#website-ux).
