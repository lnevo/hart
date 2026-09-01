# HART Operator Portal

Crew-facing site for **Neville Island** — not the engineering consolidation desk.

Open [`index.html`](index.html) in a browser (or serve the `consolidation/` folder).

## What’s here

| Section | Content |
|---------|---------|
| **Home** | Bird’s-eye hero, story CTAs |
| **Briefing** | New-operator primer (HB-01): island history, jobs, destination colors, scale |
| **Industries** | Aristech, Stucki, Calgon, Ferrellgas, Kosmos, Shenango + interchange |
| **Photos** | Browsable gallery with captions — place, maps, car fleet, aisle, power |
| **About** | *Rails Through Time*, operational narrative, STS ops article excerpt |
| **Sessions** | Curated introduction emails from past ops invites |
| **Layout / Guides / Tools** | Schematic explorer, dispatcher how-tos, STS / Mimic / JMRI |

## Rebuild content

```bash
python3 ops-portal/scripts/build_ops_content.py
```

Pulls from `external/hart-ops`, Desktop HART pubs, car image metadata, and session invite prose. Copies a small media set into `assets/media/`; fleet/aisle photos stay linked under `external/`.

## Note

This portal is for operators and guests. Pipeline / SoR / wiring stay on the [engineering desk](../index.html).
