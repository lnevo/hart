#!/usr/bin/env python3
"""agent_docs_map.py

The agent-doc lane of the pipeline map, read from the files at build time so it cannot drift: a box for each
agent-facing doc (AGENTS.md, the wiki entry pages, every .claude skill, subagent and command, the Cursor mirrors) and
the links between them. tools/ops/build_pipeline_map.py calls regenerate() and writes the result into
docs/pipeline-map/pipeline_map.json; its --check fails when the committed graph differs.

    python3 tools/ops/agent_docs_map.py     print the boxes and links it would generate

The set: DOCS and FOLDERS (each with its description), every file matching GLOBS (described by its front matter),
and HAND_KEPT, boxes another pipeline owns (a generated doc, the map itself) that keep their hand-kept entry in the
graph. A folder box stands for every file in it.

The links, each marked "gen": "agent-docs" in the graph:
- "points to": doc A names doc B, by a Markdown link (read from A's folder) or a backticked repo path, as parsed by
  references() in tools/audit/check_agent_docs.py, the parser the agent-docs check uses. A backticked name of one of
  this repo's subagents (`panel-tracer`) or commands (`/done`) points at its file. A target inside a folder box
  points at the folder. Only links between boxes of the set are drawn: a doc names dozens of scripts and data files,
  and those chains are the rest of the map.
- "check": each box with a file that check_agent_docs.py reads links to that script, so the map shows what checks
  each doc. The other guards keep their hand-kept links (build_docs_index.py writes docs/INDEX.md, status_counts.py
  the Counts line of wiki/STATUS.md; pipeline_map_coverage.py checks that every file matching GLOBS is a box).
"""
from __future__ import annotations

import fnmatch
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_agent_docs", ROOT / "tools/audit/check_agent_docs.py")
DOCS_CHECK = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DOCS_CHECK)

GEN = "agent-docs"
DOMAIN = "agents"
CHECKER = "tools/audit/check_agent_docs.py"
START = "AGENTS.md"     # where every agent starts reading; the links are drawn in reading order from here
DOCS = {
    "AGENTS.md": ("AGENTS.md", "The agent instructions every session reads first: commands, definition of done, "
                               "subagents and the do-not list."),
    "wiki/home.md": ("wiki/home.md", "Wiki entry page: where decisions, status, pipelines and projects live."),
    "wiki/AGENTS_GIT.md": ("wiki/AGENTS_GIT.md", "Branches, worktrees and merges for agents, and where each "
                                                 "agent's instructions live."),
    "wiki/STATUS_LOG.md": ("wiki/STATUS_LOG.md", "History moved out of wiki/STATUS.md."),
    "wiki/not-pending.md": ("wiki/not-pending.md", "Items the owner said never to list as pending; the whats-left "
                                                   "skill drops them."),
}
FOLDERS = {
    "wiki/decisions": ("wiki/decisions/ (ADRs)", "The architecture decision records and their README index."),
    "wiki/pipelines": ("wiki/pipelines/", "One page per pipeline and their README index."),
    "wiki/projects": ("wiki/projects/", "Project pages and hand-offs."),
    ".cursor": (".cursor/ (Cursor mirrors)", "Cursor's copies of the Claude rules: commands, the close-out rule "
                                             "and the main-branch guard."),
}
# pattern (git glob: * stays inside one folder) -> label prefix
GLOBS = {
    ".claude/skills/*/SKILL.md": "skill: ",
    ".claude/agents/*.md": "agent: ",
    ".claude/commands/*.md": "/",
    "*/AGENTS.md": "",
    "*/*/AGENTS.md": "",    # with the line above, every AGENTS.md check_agent_docs.py reads (its */AGENTS.md crosses /)
}
HAND_KEPT = ("wiki/STATUS.md", "docs/INDEX.md", "docs/pipeline-map/pipeline_map.json", "tools/ops/pipeline_query.py")
READ_SUFFIXES = (".md", ".mdc")    # the files whose links are read; the others are only link targets
FRONT_KEY = re.compile(r"^(?P<key>[A-Za-z_]+):(?P<value>.*)$")


class AgentDocsMapError(Exception):
    pass


def _ls(*pathspecs: str) -> list[str]:
    try:
        return DOCS_CHECK._git("ls-files", "-z", *pathspecs)
    except DOCS_CHECK.AgentDocsError as err:
        raise AgentDocsMapError(str(err)) from None


def glob_files(others: bool = False) -> list[str]:
    """The files matching GLOBS: tracked ones, or with others=True the new ones git does not ignore."""
    extra = ("--others", "--exclude-standard") if others else ()
    return sorted(set(_ls(*extra, *(f":(glob){g}" for g in GLOBS))))


def matches(path: str, pattern: str) -> bool:
    """Whether a repo path matches a GLOBS pattern, folder by folder (a * never crosses a /)."""
    parts, want = path.split("/"), pattern.split("/")
    return len(parts) == len(want) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(parts, want))


def _prefix(path: str) -> str:
    return next(label for g, label in GLOBS.items() if matches(path, g))


def _unquote(path: str, value: str) -> str:
    """A YAML scalar's text: a quoted one without its pair of quotes ('' inside single quotes is one quote; a double
    quoted one is read with its escapes), a plain one as written."""
    if len(value) < 2 or value[0] != value[-1] or value[0] not in "\"'":
        if value[0] in "\"'":
            raise AgentDocsMapError(f"{path}: the front matter description opens a quote it does not close")
        return value
    if value[0] == "'":
        return value[1:-1].replace("''", "'")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        raise AgentDocsMapError(f"{path}: the front matter description has an escape the map cannot read") from None


def front_description(path: str, text: str) -> str:
    """The one-line `description:` in the file's front matter (between --- lines at the top)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in (s.strip() for s in lines[1:]):
        raise AgentDocsMapError(f"{path} has no front matter (--- lines at the top); the map takes its description "
                                f"from there")
    head = lines[1:1 + [s.strip() for s in lines[1:]].index("---")]
    for i, line in enumerate(head):
        m = FRONT_KEY.match(line)
        if m and m["key"] == "description":
            value = m["value"].strip()
            if not value or value in (">", "|", ">-", "|-") or (i + 1 < len(head) and head[i + 1][:1].isspace()):
                raise AgentDocsMapError(f"{path}: the map reads a one-line front matter description; this one is "
                                        f"empty or runs over several lines")
            return _unquote(path, value)
    raise AgentDocsMapError(f"{path}: front matter has no description; add one")


def doc_nodes(tracked: frozenset[str], read) -> list[dict]:
    """The generated boxes, by path. `read` gives a repo file's text."""
    nodes = []
    for path, (label, desc) in {**DOCS, **FOLDERS}.items():
        is_folder = path in FOLDERS
        if not (any(f.startswith(path + "/") for f in tracked) if is_folder else path in tracked):
            raise AgentDocsMapError(f"{path} is in {'FOLDERS' if is_folder else 'DOCS'} of tools/ops/agent_docs_map.py "
                                    f"but is no tracked {'folder' if is_folder else 'file'}; fix or remove it")
        nodes.append({"id": path, "label": label, "kind": "unstructured", "status": "live", "domain": DOMAIN,
                      "desc": desc, "path": path, "gen": GEN})
    for path in sorted(p for p in tracked if any(matches(p, g) for g in GLOBS)):
        if path in DOCS or any(path.startswith(f + "/") for f in FOLDERS):
            continue
        stem = PurePosixPath(path).parent.name if path.endswith("/SKILL.md") else PurePosixPath(path).stem
        label = f"{_prefix(path)}{stem}" if _prefix(path) else path
        desc = front_description(path, read(path)) if _prefix(path) else "Agent instructions for this folder."
        nodes.append({"id": path, "label": label, "kind": "unstructured", "status": "live", "domain": DOMAIN,
                      "desc": desc, "path": path, "gen": GEN})
    return sorted(nodes, key=lambda n: n["path"])


def _owner(target: str | None, paths: dict[str, str], folders: tuple[str, ...]) -> str | None:
    """The box a repo path belongs to: the box with that path, else the folder box it is in."""
    if target is None:
        return None
    if target in paths:
        return paths[target]
    return next((paths[f] for f in folders if target.startswith(f + "/")), None)


def reading_order(pairs: set[tuple[str, str]], start: str) -> list[tuple[str, str]]:
    """The links that lead away from `start`: each box gets its step count from start (shortest chain of links), and a
    link is kept only when it goes to a box further from start than its own. That drops the links back up (most docs
    name AGENTS.md) and across one step, so the lane reads as a tree-like order with no cycles. A box start cannot
    reach keeps all its links, since dropping them could leave it unlinked."""
    out: dict[str, list[str]] = {}
    for a, b in pairs:
        out.setdefault(a, []).append(b)
    level = {start: 0}
    frontier = [start]
    while frontier:
        nxt = []
        for v in frontier:
            for w in sorted(out.get(v, ())):
                if w not in level:
                    level[w] = level[v] + 1
                    nxt.append(w)
        frontier = nxt
    return sorted((a, b) for a, b in pairs if a not in level or (b in level and level[b] > level[a]))


def doc_edges(set_nodes: dict[str, str], tracked: frozenset[str], read, checked: list[str],
              checker: str) -> list[dict]:
    """The generated links. set_nodes maps each box path of the set to its id; `checked` is what check_agent_docs
    reads and `checker` is its box."""
    folders = tuple(p for p in set_nodes if p in FOLDERS)
    names = {}
    for path in set_nodes:
        if matches(path, ".claude/agents/*.md"):
            names[PurePosixPath(path).stem] = path
        elif matches(path, ".claude/commands/*.md"):
            names["/" + PurePosixPath(path).stem] = path
    found: set[tuple[str, str]] = set()
    for path, nid in set_nodes.items():
        files = [path] if path not in FOLDERS else sorted(f for f in tracked if f.startswith(path + "/"))
        for f in files:
            if not f.endswith(READ_SUFFIXES):
                continue
            for ref in DOCS_CHECK.references(f, read(f)):
                to = _owner(ref.target, set_nodes, folders)
                if to is None and ref.kind == "code" and ref.raw in names:
                    to = set_nodes[names[ref.raw]]
                if to is not None and to != nid:
                    found.add((nid, to))
    edges = {pair: "points to" for pair in reading_order(found, set_nodes[START])}
    owners = {_owner(f, set_nodes, folders) for f in checked} - {None}
    for owner in owners:
        edges[(owner, checker)] = "check"
    if not owners:
        raise AgentDocsMapError(f"{CHECKER} reads none of the agent docs; check its PATTERNS")
    return [{"from": a, "to": b, "label": label, "gen": GEN} for (a, b), label in sorted(edges.items())]


def _read_file(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except OSError as err:
        raise AgentDocsMapError(f"{rel} is in git but cannot be read ({err.strerror}); restore it or git rm it") from None
    except UnicodeDecodeError:
        raise AgentDocsMapError(f"{rel} is not UTF-8 text") from None


def regenerate(data: dict, tracked: frozenset[str] | None = None, read=None,
               checked: list[str] | None = None) -> dict:
    """The graph with its generated agent-doc boxes and links replaced by fresh ones from the files."""
    tracked = tracked if tracked is not None else frozenset(_ls())
    read = read or _read_file
    checked = checked if checked is not None else DOCS_CHECK.agent_files()
    if DOMAIN not in {d.get("id") for d in data["domains"]}:
        raise AgentDocsMapError(f"the graph has no {DOMAIN!r} domain for the agent docs; add it to its domains")
    hand_nodes = [n for n in data["nodes"] if n.get("gen") != GEN]
    hand_edges = [e for e in data["edges"] if e.get("gen") != GEN]
    gen_nodes = doc_nodes(tracked, read)
    hand_paths = {n["path"].rstrip("/"): n["id"] for n in hand_nodes if n.get("path")}
    clash = sorted(n["path"] for n in gen_nodes if n["path"] in hand_paths)
    if clash:
        raise AgentDocsMapError(f"{', '.join(clash)}: generated by tools/ops/agent_docs_map.py, so remove the "
                                f"hand-kept box from the graph (or move the path to HAND_KEPT)")
    missing = [p for p in (*HAND_KEPT, CHECKER) if p not in hand_paths]
    if missing:
        raise AgentDocsMapError(f"the graph has no hand-kept box for {', '.join(missing)}, which the agent-doc "
                                f"lane links to; add it or drop it from HAND_KEPT in tools/ops/agent_docs_map.py")
    set_nodes = {n["path"]: n["id"] for n in gen_nodes} | {p: hand_paths[p] for p in HAND_KEPT}
    gen_edges = doc_edges(set_nodes, tracked, read, checked, hand_paths[CHECKER])
    hand_keys = {(e.get("from"), e.get("to")) for e in hand_edges}
    dupes = sorted(f"{e['from']} -> {e['to']}" for e in gen_edges if (e["from"], e["to"]) in hand_keys)
    if dupes:
        raise AgentDocsMapError(f"hand-kept links that the agent-doc lane now generates: {'; '.join(dupes)}; "
                                f"remove them from the graph")
    return {**data, "nodes": hand_nodes + gen_nodes, "edges": hand_edges + gen_edges}


def main() -> int:
    graph = json.loads((ROOT / "docs/pipeline-map/pipeline_map.json").read_text())
    try:
        fresh = regenerate(graph)
    except AgentDocsMapError as err:
        print(f"agent docs map: {err}", file=sys.stderr)
        return 1
    for n in fresh["nodes"]:
        if n.get("gen") == GEN:
            print(f"box  {n['id']}")
    for e in fresh["edges"]:
        if e.get("gen") == GEN:
            print(f"link {e['from']} -> {e['to']} ({e['label']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
