# JMRI USS CTC panel — build history

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

Stop-motion outputs (`CTC_Panel_Evolution.gif`, `.mp4`, `CTC_Evolution_crops/`) are
generated locally and gitignored. Regenerate:

```bash
python3 jmri/layouts/hart/ctc/history/make_ctc_evolution_video.py
```
