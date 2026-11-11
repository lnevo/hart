# Panel build history (USS CTC, CATS, Layout Editor)

Chronological screenshots captured while building the **Panel** USS machine
(`jmri/layouts/hart/ctc/GUIObjects.xml`, 15 columns). Used for the stop-motion
evolution video and [`HOW_WE_BUILT_CTC.md`](../HOW_WE_BUILT_CTC.md).

| Order | File | Stage |
|------:|------|-------|
| 1 | `66e68918-4180-46f9-938b-cc55f4fa56a2.png` | Pilot — Brick + Plane (3 columns) |
| 2 | `Screenshot 2026-08-19 at 5.44.55 PM.png` | Wireframe track + lever machine |
| 3 | `Screenshot 2026-08-19 at 8.37.11 PM.png` | Station labels |
| 4 | `Screenshot 2026-08-19 at 8.44.31 PM.png` | Main West / South Yard routing |
| 5 | `Screenshot 2026-08-19 at 9.36.05 PM.png` | Engine Terminal + yard ladders |
| 6 | `Screenshot 2026-08-19 at 9.48.51 PM.png` | West Yard W-1 / W-2 stubs |
| 7 | `Screenshot 2026-08-19 at 10.06.35 PM.png` | Full plant geometry |
| 8 | `Screenshot 2026-08-19 at 10.41.20 PM.png` | Engine House + McKees stubs |
| 9 | `Screenshot 2026-08-19 at 11.33.05 PM.png` | Title banner + live lever art |
| 10 | `Screenshot 2026-08-19 at 11.35.49 PM.png` | Connected — occupancy + aspects |
| 11 | `Screenshot 2026-08-20 at 1.34.22 AM.png` | HART RAILROAD — NEVILLE ISLAND |
| 12 | `Screenshot 2026-08-20 at 7.42.19 AM.png` | Running: lamps lit on the levers |
| 13 | `Screenshot 2026-08-23 at 8.52.10 PM.png` | Redrawn by the generator; ? until JMRI reports |
| 14 | `Screenshot 2026-08-27 at 5.22.14 PM.png` | Straight mains, OS track names, 20 columns |
| 15 | `Screenshot 2026-09-28 at 4.37.37 PM.png` | Public names: Track S-1, Track EH-1, Track K-1 |
| 16 | `uss_ctc_20261111_panelpro.png` | Princess mains redrawn from the CATS desk; every signal icon in view |

Frame 16 was painted by PanelPro on the Pi through `jmri_cmd_watcher` (the USS panel was hidden there, so the levers read ?). Frames 12 to 16 show a wider machine, so `make_ctc_evolution_video.py` crops them with fixed boxes (`EXPLICIT_CROPS`) instead of the fixed-width alignment.

Stop-motion outputs (`CTC_Panel_Evolution.gif`, `.mp4`, `CTC_Evolution_crops/`) are
generated locally and gitignored; the copies the site uses live in `www/assets/behind/panel-evolution/`. Regenerate:

```bash
python3 jmri/layouts/hart/ctc/history/make_ctc_evolution_video.py
```

The CATS panel film comes from dated screenshots in `media/screenshots/` (gitignored,
8 to 9 Aug 2026); `make_cats_evolution_video.py` crops each to the panel and builds
`CATS_Panel_Evolution.mp4`. Override the source folder with `HART_SCREENSHOTS`.

The CATS film gained `cats_dispatcher_20260826_123325.png` (routes lined in green), copied from the Desktop into `media/screenshots/` on 2026-11-09.

The Layout Editor panel film uses the four `le_panel_*.png` captures in this folder (20 May, 7 June, 20 August and 31 August 2026, copied from the Desktop on 2026-11-09). `make_le_evolution_video.py` builds `LE_Panel_Evolution.mp4` and `le-poster.jpg`. The site copies of all three films and their posters live in `www/assets/behind/panel-evolution/`.
