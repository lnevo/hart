# ADR — Portal hosting (deferred, D9 approved)

**Status:** Approved 2026-08-31

## Now

- Browse portal: [`consolidation/index.html`](../../index.html) + `html/`
- Rebuild: `python3 consolidation/scripts/build_site.py`
- Local file open or `file://` — no server required

## Later (low priority)

Serve consolidation portal from **Pi** alongside existing web UIs:

| Service | Typical URL |
|---------|-------------|
| STS | `http://<pi>:8980/sts/` |
| MQTT mimic | `http://<pi>:8765/` (or configured port) |
| JMRI web | PanelPro / web server as configured |
| Consolidation portal | TBD — static files under e.g. `/var/www/hart/consolidation/` |

## Non-goals (this phase)

- No nginx/apache changes on Pi until ops consolidation track reopens
- No auth layer on static consolidation HTML
