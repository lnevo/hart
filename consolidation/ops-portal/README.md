# HART Operator Portal

Crew-facing Neville Island site (not the engineering consolidation desk).

## Open it (required)

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
| **About** | Rails Through Time + operational narrative |
| **Layout** | Clickable LE schematic |
| **Guides / Tools** | Dispatcher how-tos and live links |

Session invitation emails are **author reference** only (used to write the primer/story). They are not a portal topic.

## Rebuild content

```bash
python3 consolidation/ops-portal/scripts/build_ops_content.py
```
