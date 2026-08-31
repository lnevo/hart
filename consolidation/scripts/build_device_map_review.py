#!/usr/bin/env python3
"""Build HART Device Map review HTML — same format as hart-device-map canvas."""
from __future__ import annotations

import html
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from lib.load_hart_devices import (  # noqa: E402
    GRAMMAR_ROWS,
    KIND_OPTIONS,
    count_kind,
    load_devices,
    save_snapshot,
)
from lib.review_portal_html import (  # noqa: E402
    callout,
    filter_script,
    page,
    stat_grid,
)

OUT = Path(__file__).resolve().parents[1] / "html/review/device-map.html"


def render_table(devices: list[dict]) -> str:
    head = (
        "<th>Unpacked</th><th>DCC</th><th>MQTT</th><th>Kind</th>"
        "<th>systemName</th><th>userName</th><th>comment</th>"
    )
    body_rows = []
    for d in devices:
        search = " ".join(
            str(d.get(k, "") or "")
            for k in ("unpacked", "dcc", "mqtt", "kind", "systemName", "userName", "comment")
        ).lower()
        body_rows.append(
            f"<tr data-kind='{html.escape(d['kind'])}' "
            f"data-search='{html.escape(search)}'>"
            f"<td>{html.escape(d.get('unpacked') or '—')}</td>"
            f"<td>{html.escape(d.get('dcc') or '—')}</td>"
            f"<td>{html.escape(d.get('mqtt') or '—')}</td>"
            f"<td>{html.escape(d['kind'])}</td>"
            f"<td><code>{html.escape(d['systemName'])}</code></td>"
            f"<td>{html.escape(d['userName'])}</td>"
            f"<td>{html.escape(d.get('comment') or '—')}</td>"
            f"</tr>"
        )
    return f"""<div class="table-wrap">
<table class="review-table" id="device-table">
  <thead><tr>{head}</tr></thead>
  <tbody>{''.join(body_rows)}</tbody>
</table></div>"""


def grammar_table() -> str:
    rows = []
    for cells in GRAMMAR_ROWS:
        tds = []
        for i, c in enumerate(cells):
            if i == 4:
                tds.append(f"<td><code>{html.escape(c)}</code></td>")
            else:
                tds.append(f"<td>{html.escape(c)}</td>")
        rows.append(f"<tr>{''.join(tds)}</tr>")
    return f"""<table class="review-table">
<thead><tr>
  <th>Kind</th><th>Unpacked</th><th>DCC</th><th>MQTT</th>
  <th>systemName</th><th>userName</th><th>comment</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>"""


def main() -> int:
    try:
        devices, source = load_devices()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    save_snapshot(devices)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    stats = [
        (str(sum(1 for d in devices if d["kind"] == "Turnout")), "Turnouts"),
        (str(sum(1 for d in devices if d["kind"] == "LCC turnout")), "LCC turnouts"),
        (str(count_kind(devices, "Occupancy")), "Occupancy"),
        (str(sum(1 for d in devices if d["kind"] == "OS block")), "OS blocks"),
        (str(sum(1 for d in devices if d["kind"] == "Block")), "Track blocks"),
        (str(count_kind(devices, "Feedback")), "Feedback"),
        (str(count_kind(devices, "Signal head")), "Heads"),
        (str(count_kind(devices, "Signal mast")), "Masts"),
        (str(count_kind(devices, "Virtual mast")), "Virtual masts"),
    ]

    kind_opts = "".join(
        f'<option value="{html.escape(v)}">{html.escape(l)}</option>'
        for v, l in KIND_OPTIONS
    )

    body = f"""
<h1>HART device map — proposed JMRI names</h1>
<p class="review-lead">
  Live beans from <code>hart-device-map.canvas.tsx</code> ({len(devices)} rows). D2 legacy notes:
  <a href="../sor/names/d2_legacy_match.csv">d2_legacy_match.csv</a> ·
  open <code>hart-device-map-d2-legacy.canvas.tsx</code> beside chat. {ts}.
</p>
{callout(
    "Address grammar",
    "MQTT turnout: Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2. LCC turnout: same minus DCC. "
    "Occupancy: Node: 4 Block: 1. Feedback: Node: 4 Sensor: 3 | IN: 1 Ports: 1. Signal head: "
    "Node: 4 Signal: 6 | OU: 3 Ports: 1,2,3 (spill uses | between OU groups). Mast and OS/track-block "
    "comments stay the control-point name (plus protected switch on masts).",
)}
{stat_grid(stats)}
<h2>Grammar</h2>
{grammar_table()}
<h2>All devices</h2>
<p class="subhead" id="row-count">{len(devices)} of {len(devices)} shown</p>
<div class="review-toolbar">
  <select id="kind-filter">{kind_opts}</select>
  <input type="search" id="q" placeholder="Filter unpacked, DCC, MQTT, name…" />
</div>
{render_table(devices)}
{filter_script()}
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page("HART device map — D2 review", "device-map", body), encoding="utf-8")
    print(f"Wrote {OUT} ({len(devices)} devices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
