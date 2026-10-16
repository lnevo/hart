# HART Operator Portal

Crew-facing Neville Island site (not the engineering consolidation desk).

## Share it (GitHub Pages)

Public URL: **https://lnevo.github.io/hart/**

GitHub Actions publishes `ops-portal/` on push to `main` (and the current portal branch). Local review, Python scripts, and Desktop/HART gallery files are not uploaded. Re-run from **Actions → Deploy operator portal → Run workflow**.

Also at **http://www.hartrailroad.com/** (VestaCP on www.easte.net). Redeploy:

```bash
./consolidation/ops-portal/scripts/deploy_hartrailroad.sh
```

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

| Page | Content |
|------|---------|
| **Home** | Bird’s-eye hero into HART |
| **Briefing** | HB-01 new-operator primer |
| **Industries** | Customers, commodities, logos |
| **Photos** | Captioned gallery (place, maps, fleet, aisle, power) |
| **Articles** | Pittsburgh & Ohio Valley Railway history, Voices of the P&OV, PC&C chronology, POHC-line industries, Chartiers Valley railroads, and the 1951 NYT pig-iron clipping |
| **About** | Operational narrative |
| **Layout** | Clickable LE schematic |
| **Guides / Tools** | Dispatcher how-tos and live links |
| **Helix** | Neville Island helix construction plan (with the half-lap screw template), build status, and the STL fixture index (`helix/`, built by `scripts/build_helix_page.py`) |

Session invitation emails are **author reference** only (used to write the primer/story). They are not a portal topic.

## Rebuild content

```bash
python3 consolidation/ops-portal/scripts/build_ops_content.py
```
