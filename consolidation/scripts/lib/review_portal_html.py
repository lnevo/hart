"""Shared HTML helpers for consolidation review pages (HART Device Map format)."""
from __future__ import annotations

import html
import json
from pathlib import Path

REVIEW_CSS = """
.review-page { max-width: 1280px; }
.review-lead { color: var(--muted); margin: 0.5rem 0 1.25rem; }
.callout {
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent2);
  background: var(--surface);
  border-radius: 8px;
  padding: 0.85rem 1rem;
  margin: 1rem 0 1.25rem;
}
.callout h3 { margin: 0 0 0.35rem; font-size: 0.95rem; color: var(--accent2); }
.callout p { margin: 0; color: var(--muted); font-size: 0.9rem; }
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.75rem;
  margin: 1rem 0 1.5rem;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem 0.85rem;
}
.stat-card .value { font-size: 1.35rem; font-weight: 700; color: var(--accent); }
.stat-card .label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
.review-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  margin: 0.75rem 0 1rem;
}
.review-toolbar select,
.review-toolbar input[type="search"] {
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 6px;
  padding: 0.4rem 0.55rem;
  font-size: 0.9rem;
}
.review-toolbar select { min-width: 220px; }
.review-toolbar input[type="search"] { flex: 1; min-width: 16rem; }
.table-wrap {
  overflow: auto;
  max-height: 900px;
  border: 1px solid var(--border);
  border-radius: 8px;
}
table.review-table {
  margin: 0;
  font-size: 0.82rem;
}
table.review-table thead th {
  position: sticky;
  top: 0;
  background: var(--surface2);
  z-index: 1;
}
table.review-table tbody tr:nth-child(even) { background: var(--surface); }
table.review-table td, table.review-table th { vertical-align: top; }
table.review-table code { font-size: 0.85em; }
tr.has-notes td.notes-col { background: rgba(240, 180, 41, 0.12); }
.subhead { color: var(--muted); font-size: 0.95rem; margin: 0.25rem 0 0.75rem; }
"""

NAV_REVIEW = """
<div class="nav-section"><h4>Review</h4>
  <a href="device-map.html"{dm_active}><strong>Device Map (D2)</strong></a>
  <a href="industry-matrix.html"{im_active}>Industry matrix</a>
  <a href="../sor-central.html">Central SoR</a>
  <a href="../cutover/names-d2.html">Names D2 cutover</a>
  <a href="../pipelines/16-industries.html">Pipeline 16</a>
</div>
"""


def review_nav(active: str) -> str:
    return NAV_REVIEW.format(
        dm_active=' class="active"' if active == "device-map" else "",
        im_active=' class="active"' if active == "industry" else "",
    )


def page(title: str, active: str, body: str, css_href: str = "../style.css") -> str:
    nav = review_nav(active)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="{css_href}">
  <style>{REVIEW_CSS}</style>
</head>
<body>
  <nav class="sidebar">
    <a class="brand" href="../index.html">HART Consolidation</a>
    {nav}
  </nav>
  <main class="content review-page">
    {body}
  </main>
</body>
</html>
"""


def callout(title: str, text: str) -> str:
    return f"""<div class="callout"><h3>{html.escape(title)}</h3><p>{html.escape(text)}</p></div>"""


def stat_grid(items: list[tuple[str, str]]) -> str:
    cards = "".join(
        f'<div class="stat-card"><div class="value">{html.escape(v)}</div>'
        f'<div class="label">{html.escape(l)}</div></div>'
        for v, l in items
    )
    return f'<div class="stat-grid">{cards}</div>'


def json_script(data: object, var_name: str = "DATA") -> str:
    payload = json.dumps(data, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")
    return f'<script id="{var_name.lower()}-json" type="application/json">{payload}</script>'


def filter_script(
    *,
    table_id: str = "device-table",
    kind_attr: str = "data-kind",
    search_attrs: tuple[str, ...] = ("data-search",),
    kind_select_id: str = "kind-filter",
    search_id: str = "q",
    count_id: str = "row-count",
    matches_kind_js: str | None = None,
) -> str:
    attrs = ", ".join(f"tr.getAttribute('{a}') || ''" for a in search_attrs)
    kind_match = matches_kind_js or f"""
      if (kind === 'all') return true;
      if (kind === 'Occupancy') return k.startsWith('Occupancy');
      if (kind === 'Feedback') return k.startsWith('Feedback');
      return k === kind;
    """
    return f"""
<script>
(function() {{
  const tbody = document.querySelector('#{table_id} tbody');
  const rows = [...tbody.querySelectorAll('tr')];
  const kindSel = document.getElementById('{kind_select_id}');
  const q = document.getElementById('{search_id}');
  const countEl = document.getElementById('{count_id}');
  function matchesKind(k, kind) {{
    {kind_match}
  }}
  function apply() {{
    const kind = kindSel.value;
    const term = (q.value || '').toLowerCase();
    let shown = 0;
    rows.forEach(tr => {{
      const k = tr.getAttribute('{kind_attr}') || '';
      const hay = ({attrs}).join(' ').toLowerCase();
      const ok = matchesKind(k, kind) && (!term || hay.includes(term));
      tr.style.display = ok ? '' : 'none';
      if (ok) shown++;
    }});
    if (countEl) countEl.textContent = shown + ' of ' + rows.length + ' shown';
  }}
  kindSel.addEventListener('change', apply);
  q.addEventListener('input', apply);
  apply();
}})();
</script>
"""
