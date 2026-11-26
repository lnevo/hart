#!/usr/bin/env python3
"""build_pipeline_map.py

Build the pipeline map, a zoomable page of every source, generator and output in the repo, from the graph in
docs/pipeline-map/pipeline_map.json. The pages are views built where they are used, not committed (ADR-036).

    python3 tools/ops/build_pipeline_map.py            (make map) refresh the graph's agent-doc lane, then write both
                                                       local pages: docs/pipeline-map/index.html and the website copy
                                                       www/library/pipeline-map.html (both gitignored)
    python3 tools/ops/build_pipeline_map.py --check    build both pages in memory and write nothing; exit 1 when the
                                                       graph is broken or stale, or a page fails its checks (check.sh, CI)
    python3 tools/ops/build_pipeline_map.py --out FILE                 the repo page to FILE
    python3 tools/ops/build_pipeline_map.py --public --out FILE [--back HREF]   the website copy to FILE

The website build (www/scripts/prepare_github_pages.py) calls site_page() and writes the website copy into its output.
Every page is checked after it is drawn (check_page: no template placeholder left, the graph's every box and link in
it, the viewer script inlined) and read back after it is written. The website copy renames the gitignored mirrors
(PUBLIC_NAMES), whose real paths the site build treats as leaks, passes the site's leak check, and can carry a link
back to the page that links to it.

Two lanes are generated from the files (GENERATED): the agent-doc lane (domain "agents": boxes and links marked
"gen": "agent-docs") by tools/ops/agent_docs_map.py, and the manifest lane (each check.sh step's script box and its
links, "gen": "manifest") by tools/pipeline/map_lane.py from tools/pipeline/checks.toml. A plain run rewrites them in
the graph file, and --check fails when the committed graph differs, naming each entry that differs; a hand edit to a
generated entry is such a difference. Everything else in the graph is hand-kept. The order of the nodes is kept as
it is: the layout breaks cycles in node order, so a sorted file draws a much wider map, and the manifest lane keeps
its boxes where the file has them. Locally the file merges itself: tools/ops/merge_pipeline_map.py is its git merge
driver.

The graph file holds domains (the horizontal lanes), nodes and edges. A node's `path` must exist in the checkout
unless the node says `"local": true` (a gitignored mirror or a file made on a host). A node marked `"runner": true`
only runs other steps (tools/check.sh, build_panels.sh). An edge may carry `"side"`, one of SIDES, for a link that
carries no content on to the next step: "check" (a check or comparison reads it), "pointer" (a doc names another),
"pull" (a Store pull back into the sources), "mirror" (a folder holds a copy), "capture" (a page screenshot),
"history" (git history of a file). A hovered line's chain on the page stops at runners and does not walk side links;
both are still drawn, and a click still traces the full reach. This script checks the graph and
writes one self-contained page from tools/ops/pipeline_map_page.html; the layout (tools/ops/pipeline_map_layout.js and
tools/ops/pipeline_map_helpers.js) and
the viewer (tools/ops/pipeline_map_view.js) are inlined into it as one script, so the page can redraw any subset (some
lanes, or the chain around one file) without build tools.
"""
from __future__ import annotations

import argparse
import functools
import html
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
ROOT = paths.REPO_ROOT
GRAPH = ROOT / "docs" / "pipeline-map" / "pipeline_map.json"
SIDES = ("check", "pointer", "pull", "mirror", "capture", "history")  # an edge's "side": why it carries no content on
PAGE = ROOT / "docs" / "pipeline-map" / "index.html"
# the page around the map (placeholders __NAME__, PLACEHOLDERS) and the scripts it inlines, in this order, as one script:
# the layout (pure functions; node loads it for the unit tests), its helpers (pure; the layout's node exports include
# them), then the viewer (app(), the page's state and input)
TEMPLATE = Path(__file__).resolve().with_name("pipeline_map_page.html")
LAYOUT_JS = Path(__file__).resolve().with_name("pipeline_map_layout.js")
HELPERS_JS = Path(__file__).resolve().with_name("pipeline_map_helpers.js")
VIEW_JS = Path(__file__).resolve().with_name("pipeline_map_view.js")
SCRIPTS = (LAYOUT_JS, HELPERS_JS, VIEW_JS)
# the website copy: its path in the site (under www/ locally, under the build's output folder on a deploy) and the
# page its back link returns to
SITE_REL = "library/pipeline-map.html"
SITE_BACK = "repository-guide.html"
SITE_PAGE = ROOT / "www" / SITE_REL
BUILD = "python3 tools/ops/build_pipeline_map.py"  # (make map) both local pages

KINDS = {
    "structured": ("Structured data", "#dbeafe", "#1e40af"),
    "unstructured": ("Unstructured source", "#fef3c7", "#92400e"),
    "generator": ("Generator / script", "#dcfce7", "#166534"),
    "output": ("Generated output", "#f3e8ff", "#6b21a8"),
    "external": ("External tool / repo", "#e5e7eb", "#374151"),
    "host": ("Host / runtime", "#fee2e2", "#991b1b"),
    "human": ("Hand work", "#fce7f3", "#9d174d"),
}
STATUSES = ("live", "parked", "retired")
# Gitignored mirrors whose paths the website's leak check rejects; the public page names them like this instead.
PUBLIC_NAMES = {
    "external/sts-docker-data": "sts-docker-data (mirror)",
    "ops/car-cards": "car-cards workspace",
    "media/hart-research": "media mirror: hart-research",
}


class GraphError(Exception):
    pass


_agent_spec = importlib.util.spec_from_file_location("agent_docs_map", Path(__file__).resolve().with_name("agent_docs_map.py"))
AGENT_DOCS = importlib.util.module_from_spec(_agent_spec)
_agent_spec.loader.exec_module(AGENT_DOCS)
_lane_spec = importlib.util.spec_from_file_location("map_lane", ROOT / "tools" / "pipeline" / "map_lane.py")
MANIFEST_LANE = importlib.util.module_from_spec(_lane_spec)
_lane_spec.loader.exec_module(MANIFEST_LANE)
# each generated lane's "gen" mark -> the file that generates it
GENERATED = {AGENT_DOCS.GEN: "tools/ops/agent_docs_map.py",
             MANIFEST_LANE.GEN: "tools/pipeline/map_lane.py, from tools/pipeline/checks.toml"}
STALE_SHOWN = 12        # entries a stale-graph message names before it counts the rest


@functools.cache
def tracked_paths() -> frozenset[str]:
    """Every git-tracked file in the repo and every folder that holds one, so the check is the same on any clone."""
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True)
    paths = set()
    for f in filter(None, out.split("\0")):
        parts = f.split("/")
        paths.update("/".join(parts[:k]) for k in range(1, len(parts) + 1))
    return frozenset(paths)


def read(path: Path) -> dict:
    """The graph file as data, with its three lists; not yet checked further (validate does that)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        raise GraphError(f"cannot read the graph: {err.strerror}") from None
    except json.JSONDecodeError as err:
        raise GraphError(f"the graph is not valid JSON: {err}") from None
    if not isinstance(data, dict):
        raise GraphError("the graph must be a JSON object")
    for key in ("domains", "nodes", "edges"):
        if not isinstance(data.get(key), list):
            raise GraphError(f"the graph needs a {key!r} list")
        bad = [item for item in data[key] if not isinstance(item, dict)]
        if bad:
            raise GraphError(f"every entry of {key!r} must be an object: {bad[0]!r}")
    bad_paths = [n for n in data["nodes"] if not isinstance(n.get("path", ""), str)]
    if bad_paths:
        raise GraphError(f"a node's path must be text: {bad_paths[0]!r}")
    return data


def node_key(n: dict) -> str:
    """What names a node: its id."""
    return n["id"]


def edge_key(e: dict) -> tuple[str, str]:
    """What names an edge: its two ends (the graph holds one edge per pair)."""
    return (e["from"], e["to"])


def graph_text(data: dict) -> str:
    """The graph as the committed file holds it."""
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def regenerate(data: dict) -> dict:
    """The graph with its generated lanes (GENERATED) rebuilt from the files: the agent-doc lane first, since the
    manifest lane leaves to it the links it already draws."""
    try:
        data = AGENT_DOCS.regenerate(data)
    except AGENT_DOCS.AgentDocsMapError as err:
        raise GraphError(f"agent-doc lane: {err}") from None
    try:
        return MANIFEST_LANE.regenerate(data)
    except MANIFEST_LANE.MapLaneError as err:
        raise GraphError(f"manifest lane: {err}") from None


def _lane_of(*entries) -> str:
    gens = sorted({e["gen"] for e in entries if isinstance(e, dict) and e.get("gen")})
    return f" ({', '.join(gens)} lane)" if gens else " (hand-kept)"


def differences(old: dict, new: dict) -> list[str]:
    """Each node and edge that `new` adds, drops or changes against `old`, named with its lane, then any other change
    (order, the top-level keys). Both are graphs as read() gives them."""
    out = []
    for name, key, show in (("nodes", node_key, "node {!r}".format),
                            ("edges", edge_key, lambda k: f"edge {k[0]} -> {k[1]}")):
        before = {key(e): e for e in old.get(name, []) if isinstance(e, dict)}
        after = {key(e): e for e in new.get(name, []) if isinstance(e, dict)}
        for k in dict.fromkeys([*before, *after]):
            a, b = before.get(k), after.get(k)
            if a == b:
                continue
            if a is None:
                out.append(f"{show(k)}{_lane_of(b)}: missing from the file")
            elif b is None:
                out.append(f"{show(k)}{_lane_of(a)}: in the file, but no lane generates it")
            else:
                fields = sorted(f for f in {*a, *b} if a.get(f) != b.get(f))
                out.append(f"{show(k)}{_lane_of(a, b)}: {', '.join(fields)} differ from what is generated")
        if not out and [key(e) for e in old.get(name, [])] != [key(e) for e in new.get(name, [])]:
            out.append(f"the order of the {name} differs from what is generated")
    if not out and {k: v for k, v in old.items() if k not in ("nodes", "edges")} != \
            {k: v for k, v in new.items() if k not in ("nodes", "edges")}:
        out.append("a top-level key differs from what is generated")
    return out


def load(path: Path) -> dict:
    return validate(read(path))


def validate(data: dict, tracked: bool = True) -> dict:
    """The graph, or GraphError naming every problem. tracked=False leaves out only the check that each node's path
    is tracked in git: the merge driver (tools/ops/merge_pipeline_map.py) runs before git has written the merged
    tree, so the paths the other branch adds are not tracked yet; tools/check.sh checks them after the merge."""
    for key in ("domains", "nodes", "edges"):
        if not isinstance(data.get(key), list):
            raise GraphError(f"the graph needs a {key!r} list")
    for d in data["domains"]:
        missing = [k for k in ("id", "label", "color") if not d.get(k)]
        if missing:
            raise GraphError(f"domain {d} lacks {', '.join(missing)}")
    domains = [d["id"] for d in data["domains"]]
    if len(set(domains)) != len(domains):
        raise GraphError("a domain id is repeated")
    ids: set[str] = set()
    problems = []
    if not data.get("nodes"):
        raise GraphError("the graph has no nodes")
    paths: dict[str, str] = {}
    for n in data["nodes"]:
        if not n.get("id"):
            problems.append(f"a node has no id: {n}")
            continue
        nid = n["id"]
        if not n.get("label"):
            problems.append(f"node {nid!r} has no label")
        if nid in ids:
            problems.append(f"node {nid!r} is listed twice")
        ids.add(nid)
        if n.get("kind") not in KINDS:
            problems.append(f"node {nid!r}: kind {n.get('kind')!r} is not one of {', '.join(KINDS)}")
        if n.get("status", "live") not in STATUSES:
            problems.append(f"node {nid!r}: status {n.get('status')!r} is not one of {', '.join(STATUSES)}")
        if n.get("domain") not in domains:
            problems.append(f"node {nid!r}: domain {n.get('domain')!r} is not a listed domain")
        p = n.get("path", "")
        if p and (Path(p).is_absolute() or ".." in Path(p).parts):
            problems.append(f"node {nid!r}: path {p} is outside the repo")
        if p and p.rstrip("/") in paths:
            problems.append(f"node {nid!r}: path {p} is already node {paths[p.rstrip('/')]!r}")
        if p:
            paths[p.rstrip("/")] = nid
        if tracked and p and not n.get("local") and p.rstrip("/") not in tracked_paths():
            problems.append(f"node {nid!r}: path {p} does not exist in git (mark it \"local\": true if it is a gitignored mirror, a submodule file or made on a host)")
    seen_edges = set()
    linked: set[str] = set()
    for e in data["edges"]:
        if not e.get("from") or not e.get("to"):
            problems.append(f"an edge lacks a from or to end: {e}")
            continue
        linked.update((e["from"], e["to"]))
        for end in ("from", "to"):
            if e[end] not in ids:
                problems.append(f"edge {e['from']} -> {e['to']}: {end} end is not a node")
        key = edge_key(e)
        if key in seen_edges:
            problems.append(f"edge {e['from']} -> {e['to']} is listed twice")
        seen_edges.add(key)
        if e["from"] == e["to"]:
            problems.append(f"edge {e['from']} points at itself")
        if "side" in e and e["side"] not in SIDES:
            problems.append(f"edge {e['from']} -> {e['to']}: side {e['side']!r} is not one of {', '.join(SIDES)}")
    for nid in sorted(ids - linked):
        problems.append(f"node {nid!r} has no links; link it or remove it")
    presets = data.get("presets", [])  # the page's start-here buttons
    if not isinstance(presets, list):
        problems.append("presets must be a list")
        presets = []
    for i, pr in enumerate(presets):
        if not isinstance(pr, dict):
            problems.append(f"preset {i + 1} must be an object: {pr!r}")
            continue
        if not isinstance(pr.get("label"), str) or not pr["label"] or not isinstance(pr.get("focus"), str) or pr["focus"] not in ids:
            problems.append(f"preset {i + 1} needs a label and a focus that is a node: {pr}")
        for side in ("up", "down"):
            v = pr.get(side)
            if not (v == "all" or isinstance(v, int) and not isinstance(v, bool) and v >= 0):
                problems.append(f"preset {pr.get('label')!r}: {side} must be a step count or \"all\"")
    if problems:
        raise GraphError("\n".join(problems))
    return data


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# Website copy only: the site stylesheet and header, the map filling the space under the header, panels in site tokens.
SITE_HEAD = '\n<link rel="stylesheet" href="../css/ops.css">'
SITE_HEADER = '\n<header class="site-header" data-ops-header></header>'
SITE_SCRIPT = ('<script src="../js/nav.js"></script>'
               '<script>HARTOps.mountChrome("behind-pipeline-map").catch(function (e) { console.error(e); });</script>')
SITE_CSS = """
/* site look: the page is a column of site header and map; the panels float over the map in site tokens */
html,body{height:100%;overflow:hidden}
body{display:flex;flex-direction:column;font:14px/1.4 var(--font-body);background:var(--paper)}
#stage{position:relative;inset:auto;flex:1;min-height:0;background:var(--paper-2)}
.panel{background:var(--card);border:1px solid var(--rule);border-radius:6px;box-shadow:var(--shadow);color:var(--ink)}
#bar h1{font:700 1.35rem/1 var(--font-display);letter-spacing:.04em;color:var(--brand);margin:0 8px 0 0}
#bar input,#bar button,#bar summary{font:inherit;color:var(--ink);background:#fff;border:1px solid var(--rule);border-radius:4px}
#bar button{cursor:pointer}
#bar button:hover,.menu>summary:hover{border-color:var(--brand-2)}
#strip2{border-top-color:var(--rule);color:var(--ink-soft)}
#back,#lanelist a,#info a,#tree a{color:var(--brand-2)}
#view{color:var(--ink-soft)}
#info h2{font:700 1.3rem/1.1 var(--font-display);letter-spacing:.03em;color:var(--brand)}
#info .off{color:var(--muted)}
#legend summary{cursor:pointer}
#legend b,#info b{color:var(--ink)}
#nav .vr{fill:rgba(179,58,58,.08);stroke:var(--signal)}
#steps{background:color-mix(in srgb,var(--paper-2) 90%,transparent);border-bottom-color:var(--rule)}
#steps span{color:var(--ink-soft);font-family:var(--font-body)}
#lanetags span{background:var(--card);font-family:var(--font-body)}
svg.focus .edge.on{stroke:var(--brand-2)}
svg.focus .node.sel .box,.node.hit .box{stroke:var(--signal)}
.node .t,.node .d{font-family:var(--font-body)}
html.dark #stage{--paper:#0f172a;--paper-2:#0b1220;--card:#1e293b;--ink:#e2e8f0;--ink-soft:#cbd5e1;--rule:#334155;--muted:#94a3b8;
 --brand:#93c5fd;--brand-2:#93c5fd}
"""


def public_copy(data: dict) -> dict:
    """The graph with every mirror path in PUBLIC_NAMES renamed, in ids, paths, labels, descriptions and links."""
    def fix(value):
        if isinstance(value, str):
            for real, shown in PUBLIC_NAMES.items():
                value = value.replace(real, shown)
            return value
        if isinstance(value, list):
            return [fix(v) for v in value]
        if isinstance(value, dict):
            return {k: fix(v) for k, v in value.items()}
        return value

    return fix(data)


@functools.cache
def _site_build():
    """www/scripts/prepare_github_pages.py, loaded once, for its leak patterns and private-name check."""
    path = ROOT / "www/scripts/prepare_github_pages.py"
    for name in ("prepare_github_pages", "__main__"):
        loaded = sys.modules.get(name)
        if loaded is not None and Path(getattr(loaded, "__file__", "") or ".").resolve() == path.resolve():
            return loaded    # the site build itself is running: use it, do not load a second copy
    spec = importlib.util.spec_from_file_location("prepare_github_pages", path)
    site = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(site)
    except (OSError, ImportError) as err:
        raise GraphError(f"cannot load the website's checks from {path.relative_to(ROOT)}: {err}") from None
    return site


def check_public_page(page: str) -> None:
    """Fail on text in the finished public page that the website build would reject: its leak patterns and the
    private name (www/scripts/prepare_github_pages.py), over the graph, the template and the inlined script."""
    site = _site_build()
    leaks = sorted({m.group() for m in site.LEAK_PATTERNS.finditer(page)})
    if leaks:
        raise GraphError(f"the public page holds text the website's leak check rejects: {', '.join(leaks)}")
    if site.contains_private_name(page):
        raise GraphError("the public page holds the private name")


REPO_URL = "https://github.com/lnevo/hart"


def code_links() -> dict:
    """Where the sidebar's GitHub link points: this repository's main branch, and each submodule's own repository at its
    default branch (GitHub has no page for a submodule path inside this repository)."""
    links = {"": REPO_URL + "/blob/main/"}
    gm = ROOT / ".gitmodules"
    text = gm.read_text() if gm.exists() else ""
    for path, url in re.findall(r"^\s*path = (\S+)\s*\n\s*url = (\S+)", text, re.M):
        m = re.match(r"(?:git@github\.com:|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?$", url)
        if m:
            links[path] = f"https://github.com/{m.group(1)}/blob/HEAD/"
    return links


def render(data: dict, back: str = "", site: bool = False) -> str:
    legend = "".join(
        f'<div><span class="sw" style="background:{fill};border-color:{ink}"></span>{esc(label)}</div>'
        for label, fill, ink in KINDS.values()
    )
    page_data = {
        "nodes": [
            {k: n[k] for k in ("id", "label", "kind", "status", "domain", "desc", "path", "local", "runner") if k in n}
            for n in data["nodes"]
        ],
        "edges": [{k: e[k] for k in ("from", "to", "label", "side") if k in e} for e in data["edges"]],
        "kinds": {k: list(v) for k, v in KINDS.items()},
        "presets": data.get("presets", []),
        "domains": [{"id": d["id"], "label": d["label"], "color": d["color"]} for d in data["domains"]],
        "domainColor": {d["id"]: d["color"] for d in data["domains"]},
        "codeLinks": code_links(),
    }
    counts = f'{len(data["nodes"])} boxes, {len(data["edges"])} links'
    back_link = f'<a id="back" href="{esc(back)}" title="Back to Inside the repository">←</a>' if back else ""
    return (
        page_template().replace("__SITEHEAD__", SITE_HEAD if site else "")
        .replace("__SITECSS__", SITE_CSS if site else "")
        .replace("__SITEHEADER__", SITE_HEADER if site else "")
        .replace("__SITESCRIPT__", SITE_SCRIPT if site else "")
        .replace("__BACK__", back_link)
        .replace("__LEGEND__", legend)
        .replace("__DATE__", esc(data.get("updated", "")))
        .replace("__COUNTS__", counts)
        .replace("__DATA__", json.dumps(page_data, separators=(",", ":")).replace("<", "\\u003c"))
        .replace("__SCRIPT__", script_text())
    )


def _part(path: Path, what: str) -> str:
    """One file the page is made from (what: "page template", "viewer script"), read whole; a missing or empty file is a
    GraphError, never a page without it."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise GraphError(f"cannot read the {what} {path.name}: {err.strerror}") from None
    if not text.strip():
        raise GraphError(f"the {what} {path.name} is empty")
    return text


@functools.cache
def script_parts() -> tuple[tuple[str, str], ...]:
    """Each viewer script the page inlines (SCRIPTS), as (file name, text), in order."""
    return tuple((path.name, _part(path, "viewer script")) for path in SCRIPTS)


@functools.cache
def script_text() -> str:
    """The script the page inlines: the viewer scripts joined in order, so the layout's functions and its "use strict"
    reach the viewer."""
    return "".join(text for _, text in script_parts())


@functools.cache
def page_template() -> str:
    """The page template (TEMPLATE), checked up front: each placeholder in PLACEHOLDERS exactly once."""
    text = _part(TEMPLATE, "page template")
    wrong = [f"{p} ({text.count(p)} times)" for p in PLACEHOLDERS if text.count(p) != 1]
    if wrong:
        raise GraphError(f"the page template {TEMPLATE.name} must hold each placeholder once: {', '.join(wrong)}")
    return text


PLACEHOLDERS = ("__SITEHEAD__", "__SITECSS__", "__SITEHEADER__", "__SITESCRIPT__", "__BACK__", "__LEGEND__",
                "__DATE__", "__COUNTS__", "__DATA__", "__SCRIPT__")
_PAGE_DATA = re.compile(r"<script>const DATA = (\{.*?\});</script>", re.S)  # "<" in the data is written <


def check_page(page: str, data: dict, site: bool) -> None:
    """GraphError unless the drawn page is whole: every template placeholder filled, its data holding exactly the
    graph's boxes (by id) and links (by their two ends), the viewer script inlined, and the site header in the website
    copy. `data` is the graph the page was drawn from (the public copy for the website page)."""
    left = [p for p in PLACEHOLDERS if p in page]
    if left:
        raise GraphError(f"the page still holds template placeholders: {', '.join(left)}")
    found = _PAGE_DATA.search(page)
    if not found:
        raise GraphError("the page holds no graph data (const DATA)")
    try:
        shown = json.loads(found.group(1))
    except json.JSONDecodeError as err:
        raise GraphError(f"the page's graph data is not valid JSON: {err}") from None
    try:
        keys = {"nodes": lambda e: e["id"], "edges": lambda e: (e["from"], e["to"])}
        for key, ident in keys.items():
            got, want = [ident(e) for e in shown.get(key, ())], [ident(e) for e in data[key]]
            if len(got) != len(want) or set(got) != set(want):
                missing, extra = sorted(map(str, set(want) - set(got))), sorted(map(str, set(got) - set(want)))
                raise GraphError(f"the page holds {len(got)} {key}, the graph {len(want)}"
                                 + (f"; missing {', '.join(missing[:5])}" if missing else "")
                                 + (f"; not in the graph {', '.join(extra[:5])}" if extra else ""))
    except (KeyError, TypeError) as err:
        raise GraphError(f"the page's graph data has a malformed entry ({err!r})") from None
    missing = [name for name, text in script_parts() if text not in page]
    if missing:
        raise GraphError(f"the page does not inline {', '.join(missing)}")
    if script_text() not in page:
        raise GraphError(f"the page does not inline {', '.join(name for name, _ in script_parts())} in order, as one script")
    if site and SITE_HEADER not in page:
        raise GraphError("the website copy has no site header")


def build(data: dict, public: bool, back: str = "") -> str:
    """One page from a checked graph, itself checked: the repo page, or the website copy (public=True: mirror paths
    renamed, site look, and the website's leak and private-name checks)."""
    drawn = public_copy(data) if public else data
    page = render(drawn, back, public)
    check_page(page, drawn, public)
    if public:
        check_public_page(page)
    return page


def write_page(out: Path, page: str) -> None:
    """Write a page and read it back; GraphError when either fails."""
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        back = out.read_text(encoding="utf-8")
    except OSError as err:
        raise GraphError(f"cannot write {out}: {err.strerror or err}") from None
    if back != page:
        raise GraphError(f"{out} reads back different from the page written")


def check_untracked() -> None:
    """GraphError when git tracks a page that is built, not committed (ADR-036): a branch from before it that kept its
    copy in a modify/delete conflict, or a git add -f. The site build would stop on it at deploy time."""
    tracked = [shown(p) for p in (PAGE, SITE_PAGE) if shown(p) in tracked_paths()]
    if tracked:
        raise GraphError(f"git tracks {', '.join(tracked)}, which are built, not committed (ADR-036): "
                         f"git rm --cached {' '.join(tracked)}")


def rebuild_command(graph: Path) -> str:
    if graph.resolve() == GRAPH.resolve():
        return f"{BUILD} (make map)"
    return f"{BUILD} --graph {shlex.quote(str(graph))} --out <page>"


def current(graph: Path) -> tuple[dict, str | None]:
    """The checked graph with its generated lanes rebuilt, and why the file is stale (None when it is current)."""
    committed = read(graph)
    data = validate(regenerate(committed))
    if graph.read_text(encoding="utf-8") == graph_text(data):
        return data, None
    found = differences(committed, data) or ["the file is not in the graph's own format (JSON, indent 1)"]
    shown = "\n".join(f"  {line}" for line in found[:STALE_SHOWN])
    more = f"\n  ... and {len(found) - STALE_SHOWN} more" if len(found) > STALE_SHOWN else ""
    lanes = "; ".join(f"{gen}: {src}" for gen, src in GENERATED.items())
    return data, (f"{graph} is out of date (its lanes are generated from the files, {lanes}):\n{shown}{more}\n"
                  f"A hand edit to a generated entry is overwritten: change its source instead. Run "
                  f"{rebuild_command(graph)} and commit the graph")


def site_page(graph: Path = GRAPH) -> str:
    """The website copy for the site build (prepare_github_pages.py), as the page at SITE_REL with its back link.
    GraphError when the graph is broken or stale or the page fails a check: a deploy never publishes a map that
    does not match the committed graph."""
    data, stale = current(graph)
    if stale:
        raise GraphError(stale)
    return build(data, public=True, back=SITE_BACK)


def shown(path: Path) -> str:
    p = path.resolve()
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--check", action="store_true",
                    help="build both pages in memory and write nothing; fail when the graph or a page has a problem")
    ap.add_argument("--graph", type=Path, default=GRAPH)
    ap.add_argument("--out", type=Path, help="write one page here instead of both local pages")
    ap.add_argument("--public", action="store_true", help="the website copy (mirror paths renamed); needs --out")
    ap.add_argument("--back", default="", help="link at the top left of the page, back to the page that links to it")
    args = ap.parse_args(argv)
    if args.check and (args.out or args.public or args.back):
        ap.error("--check builds both pages in memory and writes nothing; it takes no --out, --public or --back")
    if args.public and not args.out:
        ap.error("--public writes the website copy; give it --out")
    if not args.check and not args.out and args.graph.resolve() != GRAPH.resolve():
        ap.error("another --graph writes no local page in its place; give it --out")
    try:
        data, stale = current(args.graph)
    except GraphError as err:
        print(f"{args.graph}: the graph has problems:\n{err}", file=sys.stderr)
        return 1
    # Only the plain build writes the graph, so a website build or a --check never changes a tracked source.
    if stale and (args.check or args.public):
        print(stale, file=sys.stderr)
        return 1
    try:
        if args.check:
            check_untracked()
            build(data, public=False)
            build(data, public=True, back=SITE_BACK)
            print(f"pipeline map: the graph is current and both pages build ({len(data['nodes'])} nodes, "
                  f"{len(data['edges'])} edges)")
            return 0
        if args.out:
            pages = [(args.out, build(data, args.public, args.back))]
        else:
            pages = [(PAGE, build(data, public=False, back=args.back)),
                     (SITE_PAGE, build(data, public=True, back=SITE_BACK))]
        if stale:
            args.graph.write_text(graph_text(data), encoding="utf-8")
            print(f"updated {args.graph.name}: the generated lanes (agent-doc, manifest), from the files; "
                  f"commit it")
        for out, page in pages:
            write_page(out, page)
            print(f"wrote {shown(out)}: {len(data['nodes'])} nodes, {len(data['edges'])} edges")
    except GraphError as err:
        print(f"pipeline map: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
