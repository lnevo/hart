# HART Operator Portal

Crew-facing Neville Island site (not the engineering consolidation desk).

## Share it (GitHub Pages)

Public URL: **https://lnevo.github.io/hart/**

GitHub Actions publishes `ops-portal/` on push to `main` (and the current portal branch). Local review, Python scripts, and Desktop/HART gallery files are not uploaded. Re-run from **Actions → Deploy operator portal → Run workflow**.

## Open it locally (required)

JSON pages (Briefing, About, Photos, Layout, Industries) need **HTTP**, not `file://`.

```bash
# from repo
./consolidation/ops-portal/scripts/serve_portal.sh
# → http://127.0.0.1:8760/ops-portal/
```

Or:

```bash
python3 -m http.server 8760 --directory consolidation
open http://127.0.0.1:8760/ops-portal/
```

## Sections

| Page | Content |
|------|---------|
| **Home** | Bird’s-eye hero into HART |
| **Briefing** | HB-01 new-operator primer |
| **Industries** | Customers, commodities, logos |
| **Photos** | Captioned gallery (place, maps, fleet, aisle, power) |
| **Articles** | PC&C chronology, POHC-line industries, Chartiers Valley railroads, and the 1951 NYT pig-iron clipping |
| **About** | Operational narrative |
| **Layout** | Clickable LE schematic |
| **Guides / Tools** | Dispatcher how-tos and live links |

Session invitation emails are **author reference** only (used to write the primer/story). They are not a portal topic.

## Rebuild content

```bash
python3 consolidation/ops-portal/scripts/build_ops_content.py
```
