# HART Operator Portal

Crew-facing Neville Island site (not the engineering consolidation desk).

## Share it (GitHub Pages)

Public URL: **https://lnevo.github.io/hart/**

GitHub Actions publishes `ops-portal/` on push to `main` (and the current portal branch). Local review, Python scripts, and Desktop/HART gallery files are not uploaded. Re-run from **Actions → Deploy operator portal → Run workflow**.

Also at **http://www.hartrailroad.com/** (VestaCP on www.easte.net). Redeploy:

```bash
./consolidation/ops-portal/scripts/deploy_hartrailroad.sh
```

Deploys from your **local working tree** (any branch), so it shows changes GitHub Pages won't until they merge to `main`. Run it after every portal change; it is separate from `sync_hart_package.sh` (layout hosts).

Server notes (ssh `lnevo@www.easte.net`, passwordless sudo):

- Vesta web domain `hartrailroad.com`, alias `www.hartrailroad.com`, docroot `/home/lnevo/web/hartrailroad.com/public_html/`. Run Vesta CLI as `sudo VESTA=/usr/local/vesta /usr/local/vesta/bin/v-…`.
- Proxy template `static-revalidate` (`/usr/local/vesta/data/templates/web/nginx/php-fpm/static-revalidate.{tpl,stpl}`) = `no-php` plus `Cache-Control: no-cache`. **Do not add a `types {}` block** — it replaces nginx's MIME map and breaks CSS/JS site-wide.
- nginx `open_file_cache_valid 60s`: a deploy can take up to a minute to appear. Verify with `until curl -s http://www.hartrailroad.com/… | grep -q "<new text>"; do sleep 3; done`.
- Industry logos come from the `consolidation/external/hart-ops` submodule (`operator_logos/`); deploy from a checkout with it initialised or logos drop out (`--delete`).
- Rolling stock photos (car sides, aisle set) come from the gitignored `external/desktop-data` and `external/sts-docker-data` mirrors; `prepare_github_pages.py` resizes them into `assets/fleet/` (needs Pillow). Without the mirrors those albums drop out (GitHub Pages only shows Power).
- Historical archive images (`data/archive.json`) also live in those mirrors (`f-root/`, plus new finds in `desktop-data/archive-incoming/`); `prepare_github_pages.py` resizes them into `assets/archive/` with grid thumbnails in `assets/archive/thumbs/`, and drops items whose original is missing.
- Pages fetch JSON with `cache: "no-cache"`; keep that on new fetches so browsers don't hold stale data.
- **HTTP only.** Bare `hartrailroad.com` has no DNS A record (registrar Network Solutions). Once it points at 35.169.202.14: `v-add-letsencrypt-domain lnevo hartrailroad.com www.hartrailroad.com`.
- Live tools page links to `localhost` services, which are dead from the public site.

## Open it locally (required)

JSON pages (Briefing, About, Photos, Layout, Industries) need **HTTP**, not `file://`.

```bash
# from repo — includes review log API (POST /api/f-root-review/log)
# Login LaunchAgent (survives Cursor quit; starts at login):
./consolidation/ops-portal/scripts/install_portal_launchagent.sh
# Foreground only (dies when the terminal/Cursor session ends):
./consolidation/ops-portal/scripts/serve_portal.sh
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

The header has four links (`data/site.json` → `nav`): **Home · History & Industries · Operators · About**. Each nav entry lists the page ids (the argument to `HARTOps.mountChrome(id)`) that belong to it in `pages`; `js/nav.js` underlines the parent section and adds a small section link above the child page's title. Add a new page's id to the right section's `pages`.

- **History & Industries** (`history/index.html`): Articles (+ `library/*`), Industries, Photos, Rolling stock.
- **Operators** (`operators/index.html`): Briefing, Publications (`docs/`), Guides, Layout Explorer, Device roster, Live tools, Helix.
- Elements marked `data-local-only` are hidden on the public build (`site.public`), for localhost and workspace links.

| Page | Content |
|------|---------|
| **Home** | Bird’s-eye hero, then doors into the two sections |
| **Briefing** | HB-01 new-operator primer |
| **Industries** | Customers, commodities, logos |
| **Photos** | Captioned gallery (place, maps, fleet, aisle, power) |
| **Articles** | Pittsburgh & Ohio Valley Railway history, Voices of the P&OV, PC&C chronology, POHC-line industries, Chartiers Valley railroads, and the 1951 NYT pig-iron clipping |
| **About** | Operational narrative |
| **Layout** | Clickable LE schematic |
| **Guides / Tools** | Dispatcher how-tos and live links |
| **Archive** | Historical photos, ads, clippings, and period maps in three tabs (Curated / To review / Discard) with credits (`archive/`, data in `data/archive.json`). On `serve_portal.sh` the owner can move items between tabs and edit captions; saves go to `data/archive.json`, with a log in `sor/desktop/archive_review_log.jsonl`. Public site is read-only. |
| **Helix** | Neville Island helix construction plan (with the half-lap screw template), build status, and the STL fixture index (`helix/`, built by `scripts/build_helix_page.py`) |

Session invitation emails are **author reference** only (used to write the primer/story). They are not a portal topic.

## Rebuild content

```bash
python3 consolidation/ops-portal/scripts/build_ops_content.py
```
