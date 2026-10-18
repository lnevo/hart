# HART Operator Portal

Crew-facing Neville Island site (not the engineering consolidation desk).

## Share it

Public URL: **https://www.hartrailroad.com/** (VestaCP on www.easte.net), the only public copy. The GitHub Pages site (lnevo.github.io/hart) and its Actions workflow were removed 2026-10-17. Redeploy:

```bash
./consolidation/ops-portal/scripts/deploy_hartrailroad.sh            # --force: deploy despite a count drop
```

Deploys from your **local working tree** (any branch, work in progress included). Run it after every portal change; it is separate from `sync_hart_package.sh` (layout hosts).

**Build rules** (`scripts/prepare_github_pages.py [DEST] [--site-url URL]`; the name predates the move off Pages):

- Only **git-tracked** files are published, with their working-tree content. A new page or image stays off the site until it is `git add`ed (committing is not needed).
- To keep a tracked file off the site, add it to `SKIP_FILES` (one file), `SKIP_DIRS` (a folder), or `SKIP_GLOBS` (a pattern) at the top of the script. `scripts/`, `review/`, `tools/`, `reference/`, `README.md`, `docs/*.md`, the F-root review data, and invitation drafts are already skipped.
- Elements marked `data-local-only` are **removed** from the built HTML (and also hidden by `js/nav.js` when `site.public`), so use it for localhost and workspace links. `site.json` `tools` (localhost service URLs) is dropped, and any data field still pointing into `../external/` is removed.
- **Leak check:** the build fails, listing file and line, if the output still contains `localhost`, `127.0.0.1`, `/Users/`, or `consolidation/external` (or `../external/` in data). Fix the source text or skip the file.
- Gallery and rolling-stock items get a ~640 px grid thumbnail (`assets/gallery/thumbs/`, `assets/fleet/thumbs/`, field `thumb`) and the full image's `width`/`height` when Pillow is installed.
- The 404 page uses site-root links (`/css/ops.css`, `/`), since the site is served at the domain root. `SITE_URL` (share tags) can be overridden with `--site-url` or `HART_SITE_URL`.

**Deploy safety** (`deploy_hartrailroad.sh`):

- Refuses to run when `consolidation/external/hart-ops` is missing or not initialised (logos would drop out, and `rsync --delete` would remove them live). Warns, without stopping, when the submodule is not at the recorded commit (`+` in `git submodule status`) or the portal has uncommitted changes.
- Runs `scripts/check_portal_build.py --dist` on the build: every internal `href`/`src` in the HTML and every link/asset field in `data/*.json` must resolve to a built file. Run it alone (`python3 consolidation/ops-portal/scripts/check_portal_build.py`) to build into a temp folder and check.
- Prints a manifest (file count, archive items, industry logos, gallery and fleet items) and compares it with the last deploy's, kept in the gitignored `consolidation/.deploy-manifest.json`. A count down more than 10% stops the deploy unless `--force` is passed. The manifest is saved only after a successful rsync.

Server notes (ssh `lnevo@www.easte.net` for admin work):

- Deploys use an rsync-only key (`~/.ssh/hart_deploy`, `Host hart-deploy` in `~/.ssh/config`) whose forced `rrsync` command is rooted at the docroot, so it cannot open a shell. It needs a real rsync on the Mac (`brew install rsync`; macOS `/usr/bin/rsync` is openrsync, which the server's rrsync rejects). `HART_WEB_HOST=www.easte.net` falls back to a normal login.
- The Vesta panel (port 8083) is restricted with allow/deny lines in `/usr/local/vesta/nginx/conf/nginx.conf`, and phpMyAdmin in `/etc/nginx/conf.d/phpmyadmin.inc`; webmail's include was removed. A Vesta or `vesta-nginx` update can overwrite these files, so check them after any update (backups in `/root/nginx-backup-20261017/`).

- Vesta web domain `hartrailroad.com`, alias `www.hartrailroad.com`, docroot `/home/lnevo/web/hartrailroad.com/public_html/`. Run Vesta CLI as `sudo VESTA=/usr/local/vesta /usr/local/vesta/bin/v-…`.
- Proxy template `static-revalidate` (`/usr/local/vesta/data/templates/web/nginx/php-fpm/static-revalidate.{tpl,stpl}`) = `no-php` plus `Cache-Control: no-cache`, HTTP→HTTPS redirect (ACME challenges exempt), and security headers (HSTS, nosniff, Referrer-Policy, `frame-ancestors 'self'`, and a report-only CSP). Only hartrailroad.com uses it. nginx drops outer `add_header`s inside a location that sets its own, so the headers are repeated per location. **Do not add a `types {}` block** — it replaces nginx's MIME map and breaks CSS/JS site-wide.
- nginx `open_file_cache_valid 60s`: a deploy can take up to a minute to appear. Verify with `until curl -s http://www.hartrailroad.com/… | grep -q "<new text>"; do sleep 3; done`.
- Industry logos come from the `consolidation/external/hart-ops` submodule (`operator_logos/`); deploy from a checkout with it initialised or logos drop out (`--delete`).
- Rolling stock photos (car sides, aisle set) come from the gitignored `external/desktop-data` and `external/sts-docker-data` mirrors; `prepare_github_pages.py` resizes them into `assets/fleet/` (needs Pillow). Without the mirrors (or Pillow) those albums drop out and only Power shows.
- Historical archive images (`data/archive.json`) also live in those mirrors (`f-root/`, plus new finds in `desktop-data/archive-incoming/`); `prepare_github_pages.py` resizes them into `assets/archive/` with grid thumbnails in `assets/archive/thumbs/`, and drops items whose original is missing.
- Favicon and share previews: `prepare_github_pages.py` adds the favicon links and Open Graph tags (title from each page's `<title>`, image `assets/icons/share-card.jpg`) to every HTML page at build time, so source pages don't carry them. Icons come from `assets/media/hart-logo.png`. After changing them, re-scrape in Facebook's Sharing Debugger (developers.facebook.com/tools/debug).
- Pages fetch JSON with `cache: "no-cache"`; keep that on new fetches so browsers don't hold stale data.
- **HTTPS** via Vesta Let's Encrypt (`v-add-letsencrypt-domain lnevo hartrailroad.com www.hartrailroad.com`, issued 2026-10-16). Both names resolve to 35.169.202.14 (registrar Network Solutions); the admin cron `v-update-letsencrypt-ssl` renews it. Plain HTTP redirects to HTTPS (since 2026-10-17).
- Live tools links to `localhost` services exist only on the local portal; the build strips them (`data-local-only`, `site.json` `tools`).

## Open it locally (required)

JSON pages (Briefing, About, Historic photos, Layout, Industries) need **HTTP**, not `file://`.

```bash
# from repo — includes review log API (POST /api/f-root-review/log); edits must come from a local page (JSON body, local Origin)
# Login LaunchAgent (survives Cursor quit; starts at login):
./consolidation/ops-portal/scripts/install_portal_launchagent.sh
# Foreground only (dies when the terminal/Cursor session ends):
./consolidation/ops-portal/scripts/serve_portal.sh [PORT]
# → http://127.0.0.1:8760/ops-portal/
# F-root review → http://127.0.0.1:8760/ops-portal/review/f-root/
```

Plain `python3 -m http.server` works for read-only pages but **cannot save** review decisions.

**F-root review curation** (previews + optional GPT summaries):

```bash
python3 consolidation/ops-portal/scripts/curate_f_root_review.py --previews
python3 consolidation/ops-portal/scripts/curate_f_root_review.py --gpt   # OPENAI_API_KEY in .env.local
```

## Sections

The header has six links (`data/site.json` → `nav`): **Home · The Prototype · Operations · Behind the Scenes · The Build · About**. Each nav entry lists the page ids (the argument to `HARTOps.mountChrome(id)`) that belong to it in `pages`; `js/nav.js` underlines the parent section and adds a small section link above the child page's title. Add a new page's id to the right section's `pages`.

- **The Prototype** (`history/index.html`): Articles (+ `library/*`), Industries, Historic photos (`archive/`), Rolling stock.
- **Operations** (`operators/index.html`), newcomers first: **Your first session** (Primer `briefing/`, Glossary `operators/glossary/`, the layout room `operators/room/`, car cards & waybills `operators/cards/`, plus a line to Industries and Rolling stock), then **Regular crews**: **Session paperwork** (`crew/`: crew sheets, YM-01, DS-01, station maps, TT-23, colors, EQ-01, industry spot sheets), **Dispatcher's desk** (Guides, Layout Explorer, Live tools) and a pointer to Publications (`docs/`, the print/download shelf).
- The "Your first night" box on the Operations hub (`operators/index.html`) is static HTML; the Primer's copy comes from `firstNight` in `data/briefing.json`. Keep the two in step.
- Pages that load JSON show "Loading…" and, on failure, `HARTOps.renderError(el, {what, links, err})` (visitor text plus a Reload button; the serve-over-HTTP hint only on localhost). If `site.json` itself fails, `mountChrome` draws a brand-only header instead of a blank page.
- Escape with `HARTOps.esc` and build paths with `HARTOps.base()` (both from `js/nav.js`); don't add local copies. Every page loads `nav.js` before its other scripts, so scripts can read `HARTOps` when they load.
- **Behind the Scenes** (`behind/index.html`): how the layout works. Control & signals (`behind/signals.html`, pointer to Guides), Electronics & the bridge (`behind/bridge.html`, Device roster `roster/`, wiring photos on The Build, Digicon reference `guides/digicon-system.html` local-only), Car forwarding (STS article `library/sts-operations-article.html`), Locomotives (STRR speed-match SOP PDF).
- **The Build** (`build/index.html`): the helix (`helix/`, build status, plan PDF) and the `plans` + `build` albums of `data/gallery.json` via `js/gallery.js` (`albums: [...]` scopes a page to some albums; `heading: false` keeps the page's own title).
- Elements marked `data-local-only` are removed from the public build (see Build rules), for localhost and workspace links.

| Page | Content |
|------|---------|
| **Home** | Bird’s-eye hero, doors into The Prototype and Operations, and two smaller doors into Behind the Scenes and The Build |
| **Briefing** | HB-01 New Operator Primer (Revision B), the single canonical page; `docs/html/Neville_Island_New_Operator_Primer.html` redirects here |
| **Glossary** | `operators/glossary/`: plain-language meanings of railroad words, job codes, publication numbers, and the software names (static HTML) |
| **Session paperwork** | `crew/`: crew sheets (`crew/d749/`, `nvl/`, `ck1/`), YM-01 (`crew/yardmaster/`), DS-01 (`crew/dispatcher/`), station maps (`crew/maps/<area>/`), TT-23, destination colors, EQ-01, industry spot sheets. All rendered by `js/crew.js` from `data/crew.json`, which is hand-copied from `external/hart-ops/publications/rebuild_*.py` and the published docx (those stay canonical). Each sheet prints as a 5×8 in card; maps print 8×5 landscape |
| **Layout room** | `operators/room/`: Session night and Panels & screens albums from `data/gallery.json` (Track plan development and Build & wiring show on `build/`) (album id `layout` = Session night, which the archive's "Layout photos" button writes to) |
| **Car cards & waybills** | `operators/cards/`: sample car card and CC/WB waybills (PNG crops in `assets/cards/`, crops of Word PDF exports of `external/hart-ops` card_pipeline output and `docs/print/waybills/HART_Session4_Waybill_Labels_Page.docx`) and a first-session how-to |
| **Industries** | Customers, commodities, logos, from `data/industries.json`; each industry's `spot` is its anchor on the crew spot sheets and `stripes` its destination color ids (`data/crew.json` `colors`) for the stripe under the logo |
| **Old Photos URL** | `photos/` redirects to `operators/room/` |
| **Articles** | Pittsburgh & Ohio Valley Railway history, Voices of the P&OV, PC&C chronology, POHC-line industries, Chartiers Valley railroads, the 1951 NYT pig-iron clipping, and two Coraopolis Record opinion pieces (2016–17) |
| **About** | Operational narrative |
| **Layout** | Clickable LE schematic |
| **Guides / Tools** | Dispatcher how-tos and live links |
| **Historic photos** | Historical photos, ads, clippings, and period maps in three tabs (Curated / To review / Discard) with credits (`archive/`, data in `data/archive.json`). On `serve_portal.sh` the owner can move items between tabs and edit captions; saves go to `data/archive.json`, with a log in `sor/desktop/archive_review_log.jsonl`. Public site is read-only. |
| **Helix** | Neville Island helix construction plan (with the half-lap screw template), build status, and the STL fixture index (`helix/`, built by `scripts/build_helix_page.py`, which copies from `~/Downloads/stl` and would overwrite `helix/scripts/` with the copies there). The fixture scripts in `helix/scripts/` write to `helix/stl/` by default (`--out DIR` to change); they need numpy, scipy, trimesh, shapely and matplotlib |

Session invitation emails are **author reference** only (used to write the primer/story). They are not a portal topic.

## Rebuild content (legacy)

`scripts/legacy/build_ops_content.py` and `scripts/legacy/refresh_galleries_and_library.py` predate the hand-edited `briefing.json`, `gallery.json`, `industries.json`, and `publications.json`; a forced run overwrites those files with older content. Both are dry runs by default (they list what they would write); `--force` writes. Check the diff before committing.

```bash
python3 consolidation/ops-portal/scripts/legacy/build_ops_content.py [--f-root DIR]           # or HART_F_ROOT; default external/desktop-data/f-root
python3 consolidation/ops-portal/scripts/legacy/refresh_galleries_and_library.py [--desktop-data DIR]   # or HART_DESKTOP_DATA
```
