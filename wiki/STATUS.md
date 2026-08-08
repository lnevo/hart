# Live status — HART Digicon

Updated: 2026-08-08 — remote/cloud ready + Gate 1 primary

## Repo / remote

- GitHub: https://github.com/lnevo/hart  
- Local workspace folder: `Panel` (same git root)  
- Agent branch pattern: `agent/<id>/<topic>` — see [`AGENTS_GIT.md`](AGENTS_GIT.md)  
- Cloud Agents: link `lnevo/hart` at [Cloud Agents dashboard](https://cursor.com/dashboard/cloud-agents)

## Now

- Primary launch: `cats/panels/HART.xml` — **Gate 1** (Designer geometry + CTC rules)  
- Rebuild Gate 1: `python3 cats/scripts/wire_designer_ctc_rules.py --mqtt`  
- LE Digicon generator (WIP / may blank): `python3 cats/scripts/build_hart_digicon_from_le.py`  
- Authoritative Designer draw: `cats/panels/HART_designer_raw.xml`  
- How-to: [`cats/docs/DESIGNER_GATE1_HOWTO.md`](../cats/docs/DESIGNER_GATE1_HOWTO.md)

## Manual launch (local Mac only)

```bash
CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART.xml
```

Do **not** use `CATS_LAUNCH_VIA=app`. Keep-alive LaunchAgent stays disabled.
