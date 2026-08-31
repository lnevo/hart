#!/usr/bin/env python3
"""Generate HTML browse site from consolidation markdown."""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CON = ROOT / "consolidation"
HTML = CON / "html"


def md_to_html(text: str) -> str:
    """Minimal markdown → HTML (headings, code blocks, lists, links, tables)."""
    lines = text.splitlines()
    out: list[str] = []
    in_code = False
    in_table = False
    list_mode: str | None = None

    def close_list() -> None:
        nonlocal list_mode
        if list_mode:
            out.append(f"</{list_mode}>")
            list_mode = None

    for line in lines:
        if line.strip().startswith("```"):
            close_list()
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            out.append(html.escape(line))
            continue

        if "|" in line and line.strip().startswith("|"):
            close_list()
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.match(r"^[-:]+$", c.replace(" ", "")) for c in cells):
                continue
            row = "".join(f"<td>{html.escape(c)}</td>" for c in cells)
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append(f"<tr>{row}</tr>")
            continue
        elif in_table:
            out.append("</table>")
            in_table = False

        if line.startswith("# "):
            close_list()
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            close_list()
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            close_list()
            out.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("> "):
            close_list()
            out.append(f"<blockquote>{inline_md(line[2:])}</blockquote>")
        elif re.match(r"^[-*] ", line):
            if list_mode != "ul":
                close_list()
                out.append("<ul>")
                list_mode = "ul"
            out.append(f"<li>{inline_md(line[2:])}</li>")
        elif re.match(r"^\d+\. ", line):
            if list_mode != "ol":
                close_list()
                out.append("<ol>")
                list_mode = "ol"
            out.append(f"<li>{inline_md(re.sub(r'^\\d+\\. ', '', line))}</li>")
        elif not line.strip():
            close_list()
            out.append("")
        else:
            close_list()
            out.append(f"<p>{inline_md(line)}</p>")

    close_list()
    if in_code:
        out.append("</code></pre>")
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def inline_md(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


PAGE_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — HART Consolidation</title>
  <link rel="stylesheet" href="{css}">
</head>
<body>
  <nav class="sidebar">
    <a class="brand" href="{home}">HART Consolidation</a>
    {nav}
  </nav>
  <main class="content">
    {body}
  </main>
</body>
</html>
"""

CSS = """
:root {
  --bg: #0f1419;
  --surface: #1a2332;
  --surface2: #243044;
  --text: #e8edf4;
  --muted: #8b9cb3;
  --accent: #c9a227;
  --accent2: #4a9eff;
  --border: #2d3a4f;
  --ok: #3dd68c;
  --warn: #f0b429;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 280px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 1.25rem;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}
.brand {
  display: block;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--accent);
  text-decoration: none;
  margin-bottom: 1.5rem;
  letter-spacing: 0.02em;
}
.nav-section { margin-bottom: 1.25rem; }
.nav-section h4 {
  margin: 0 0 0.5rem;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}
.nav-section a {
  display: block;
  color: var(--text);
  text-decoration: none;
  padding: 0.35rem 0.5rem;
  border-radius: 6px;
  font-size: 0.9rem;
}
.nav-section a:hover { background: var(--surface2); color: var(--accent2); }
.content {
  flex: 1;
  padding: 2rem 2.5rem;
  max-width: 960px;
}
h1 { color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }
h2 { color: var(--accent2); margin-top: 2rem; }
h3 { color: var(--muted); }
a { color: var(--accent2); }
code, pre {
  background: var(--surface2);
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.88em;
}
code { padding: 0.15rem 0.4rem; }
pre { padding: 1rem; overflow-x: auto; }
pre code { padding: 0; background: none; }
table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }
td, th { border: 1px solid var(--border); padding: 0.5rem 0.75rem; text-align: left; }
tr:nth-child(even) { background: var(--surface); }
blockquote {
  border-left: 3px solid var(--accent);
  margin: 1rem 0;
  padding: 0.5rem 1rem;
  background: var(--surface);
  color: var(--muted);
}
.hero {
  background: linear-gradient(135deg, var(--surface) 0%, var(--surface2) 100%);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 2rem;
  margin-bottom: 2rem;
}
.hero h1 { border: none; margin-top: 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 1rem; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem;
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s, transform 0.15s;
}
.card:hover { border-color: var(--accent); transform: translateY(-2px); }
.card h3 { margin: 0 0 0.5rem; color: var(--accent2); font-size: 1rem; }
.card p { margin: 0; font-size: 0.85rem; color: var(--muted); }
.badge {
  display: inline-block;
  font-size: 0.7rem;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  background: var(--surface2);
  color: var(--muted);
  margin-right: 0.35rem;
}
.badge.live { background: #1a3d2e; color: var(--ok); }
.badge.frozen { background: #3d3a1a; color: var(--warn); }
.badge.deferred { background: var(--surface2); }
"""


NAV = """
<div class="nav-section"><h4>Overview</h4>
  <a href="index.html">Home</a>
  <a href="objective.html">Objective</a>
  <a href="decisions.html">Decisions recorded</a>
  <a href="next-round.html">Next round</a>
  <a href="live-sources.html">Live sources</a>
  <a href="manifest.html">Manifest</a>
</div>
<div class="nav-section"><h4>Desks &amp; panel</h4>
  <a href="pipelines/01-jmri-anyrail.html">JMRI / AnyRail</a>
  <a href="pipelines/02-public-names.html">Public names</a>
  <a href="pipelines/05-cats-masters.html">CATS Masters</a>
  <a href="projects/cats-integration.html">CATS integration</a>
  <a href="pipelines/06-uss-ctc.html">USS CTC</a>
  <a href="pipelines/07-dispatcher.html">Dispatcher System</a>
</div>
<div class="nav-section"><h4>Signals &amp; MQTT</h4>
  <a href="pipelines/03-digicon-beans.html">Digicon beans</a>
  <a href="pipelines/04-native-sml.html">Native SML + NX</a>
  <a href="pipelines/09-lcos-firmware.html">LCOS firmware</a>
  <a href="cross-repo/lcos-tier-b.html">LCOS Tier B spec</a>
  <a href="pipelines/mimic.html">MQTT mimic QA</a>
</div>
<div class="nav-section"><h4>Ops &amp; wiring</h4>
  <a href="pipelines/08-wiring.html">Wiring docs</a>
  <a href="pipelines/12-car-cards.html">Car cards</a>
  <a href="pipelines/14-sts.html">STS</a>
  <a href="pipelines/15-publications.html">Publications</a>
  <a href="pipelines/16-industries.html">Industries</a>
</div>
<div class="nav-section"><h4>Review</h4>
  <a href="audits/index.html">Audits</a>
  <a href="archive/index.html">Archive taxonomy</a>
  <a href="repos.html">Repos &amp; submodules</a>
  <a href="decisions/index.html">ADR index</a>
  <a href="validators/tier-b-smokes.html">Tier B smokes</a>
</div>
"""


def write_page(rel: str, title: str, body_html: str, css_depth: str = "style.css") -> None:
    path = HTML / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    home = "../" * (rel.count("/")) + "index.html" if rel != "index.html" else "index.html"
    css = "../" * (rel.count("/")) + css_depth if rel != "index.html" else css_depth
    nav_home = "../" * (rel.count("/")) + "index.html" if rel != "index.html" else "index.html"
    nav = NAV.replace('href="index.html"', f'href="{nav_home}"')
    nav = nav.replace('href="objective.html"', f'href="{"../" * rel.count("/")}objective.html"')
    for name in ("decisions", "live-sources", "manifest", "audits", "cross-repo", "pipelines", "projects", "archive", "validators", "decisions/adr"):
        prefix = "../" * rel.count("/")
        nav = nav.replace(f'href="{name}', f'href="{prefix}{name}')
    page = PAGE_SHELL.format(title=html.escape(title), css=css, home=home, nav=nav, body=body_html)
    path.write_text(page, encoding="utf-8")


def main() -> None:
    HTML.mkdir(parents=True, exist_ok=True)
    (HTML / "style.css").write_text(CSS, encoding="utf-8")

    # Home
    home_body = """
<div class="hero">
  <h1>HART Railroad — Consolidation Portal</h1>
  <p>Parallel review workspace. Live operational sources are <strong>read-only</strong>.
  All drafts, validators, and proposed SoRs live under <code>hart/consolidation/</code>.</p>
  <p><a href="decisions.html"><strong>→ Review decisions pending approval</strong></a></p>
</div>
<div class="cards">
  <a class="card" href="pipelines/05-cats-masters.html"><h3>CATS CTC / ABS</h3><p>Master4 hold panels, Digicon desk</p></a>
  <a class="card" href="pipelines/07-dispatcher.html"><h3>JMRI Dispatcher</h3><p>Graph, traininfo, facing overlay</p></a>
  <a class="card" href="pipelines/mimic.html"><h3>MQTT mimic</h3><p>LCOS QA, signalhead publisher</p></a>
  <a class="card" href="pipelines/14-sts.html"><h3>STS</h3><p>Sessions, switch lists, seed</p></a>
  <a class="card" href="pipelines/08-wiring.html"><h3>Wiring</h3><p>LCOS inventory v85, schematics</p></a>
  <a class="card" href="pipelines/09-lcos-firmware.html"><h3>LCOS bridge</h3><p>Nano firmware + serial_to_mqtt</p></a>
  <a class="card" href="live-sources.html"><h3>Live sources map</h3><p>Paths you must not edit</p></a>
  <a class="card" href="audits/index.html"><h3>Audits</h3><p>Validator reports & reviews</p></a>
  <a class="card" href="archive/index.html"><h3>Archive taxonomy</h3><p>Desktop/HART classes A–F</p></a>
  <a class="card" href="repos.html"><h3>Repos</h3><p>Meta-repo & submodule recipe</p></a>
</div>
"""
    write_page("index.html", "Home", home_body)

    # Markdown pages
    md_pages = [
        ("objective.html", "Objective", CON / "OBJECTIVE.md"),
        ("decisions.html", "Decisions recorded", CON / "DECISIONS_RECORDED.md"),
        ("next-round.html", "Next round", CON / "NEXT_ROUND.md"),
        ("live-sources.html", "Live sources", CON / "LIVE_SOURCES.md"),
        ("manifest.html", "Manifest", CON / "manifest.yaml"),
        ("audits/index.html", "Audits", CON / "audits/README.md"),
        ("cross-repo/lcos-tier-b.html", "LCOS Tier B", CON / "cross-repo/lcos/TIER_B.md"),
        ("projects/cats-integration.html", "CATS integration", CON / "wiki/projects/cats-integration.md"),
        ("archive/index.html", "Archive taxonomy", CON / "wiki/archive/INDEX.md"),
        ("repos.html", "Repos & submodules", CON / "wiki/REPOS.md"),
        ("decisions/index.html", "ADR index", CON / "wiki/decisions/README.md"),
        ("validators/tier-b-smokes.html", "Tier B smokes", CON / "validators/TIER_B_MANUAL_SMOKES.md"),
        ("cross-repo/hart-ops-readme.html", "hart-ops (draft)", CON / "cross-repo/hart-ops/README.md"),
    ]

    for rel, title, md_path in md_pages:
        if md_path.suffix == ".yaml":
            text = md_path.read_text(encoding="utf-8")
            body = f"<pre><code>{html.escape(text)}</code></pre>"
        else:
            body = md_to_html(md_path.read_text(encoding="utf-8"))
        write_page(rel, title, body)

    # ADRs
    for adr in (CON / "wiki/decisions").glob("*.md"):
        rel = f"decisions/{adr.stem}.html"
        write_page(rel, adr.stem, md_to_html(adr.read_text(encoding="utf-8")))

    # Pipelines
    mapping = {
        "jmri-anyrail.md": "pipelines/01-jmri-anyrail.html",
        "public-names.md": "pipelines/02-public-names.html",
        "digicon-signal-beans.md": "pipelines/03-digicon-beans.html",
        "native-sml.md": "pipelines/04-native-sml.html",
        "cats-masters.md": "pipelines/05-cats-masters.html",
        "uss-ctc.md": "pipelines/06-uss-ctc.html",
        "dispatcher-system.md": "pipelines/07-dispatcher.html",
        "wiring-docs.md": "pipelines/08-wiring.html",
        "lcos-firmware.md": "pipelines/09-lcos-firmware.html",
        "speed-matching.md": "pipelines/11-speed-matching.html",
        "car-cards.md": "pipelines/12-car-cards.html",
        "waybills.md": "pipelines/13-waybills.html",
        "sts.md": "pipelines/14-sts.html",
        "ops-publications.md": "pipelines/15-publications.html",
        "industry-routing.md": "pipelines/16-industries.html",
    }
    for md_name, html_rel in mapping.items():
        md_path = CON / "wiki/pipelines" / md_name
        if md_path.is_file():
            title = md_name.replace("-", " ").replace(".md", "")
            write_page(html_rel, title, md_to_html(md_path.read_text(encoding="utf-8")))

    # Mimic page (custom)
    mimic = CON / "wiki/pipelines/mqtt-mimic.md"
    if mimic.is_file():
        write_page("pipelines/mimic.html", "MQTT mimic", md_to_html(mimic.read_text(encoding="utf-8")))

    # Copy index to consolidation root for easy open
    (CON / "index.html").write_text((HTML / "index.html").read_text(encoding="utf-8").replace('href="style.css"', 'href="html/style.css"').replace('href="objective.html"', 'href="html/objective.html"').replace('href="decisions.html"', 'href="html/decisions.html"').replace('href="pipelines/', 'href="html/pipelines/').replace('href="live-sources.html"', 'href="html/live-sources.html"').replace('href="audits/', 'href="html/audits/').replace('href="manifest.html"', 'href="html/manifest.html"'), encoding="utf-8")

    print(f"Site written to {HTML}")


if __name__ == "__main__":
    main()
