#!/usr/bin/env python3
"""Who is working on what: one screen to read at the start of a session, so two agents do not work on top of each other.

    python3 tools/ops/orient.py              the full view (make orient): claims, worktrees in progress, the operating
                                             flag, open PRs, files changed in two places or more (orient_overlap.py),
                                             what each layout host last got, and what a host holds that is waiting
                                             to come into the repo
    python3 tools/ops/orient.py --short      claims, worktrees in progress and one Overlap line, no network (the
                                             session-start hook)
    python3 tools/ops/orient.py claim PAGE   write this worktree's Claimed line under PAGE's Status line
    python3 tools/ops/orient.py unclaim PAGE [--branch B]   remove it (this branch's, or B's)

A claim is one line directly under the `Status:` line of a page in wiki/projects/ (more claims follow each other):

    Claimed: <branch>, <absolute worktree path>, since YYYY-MM-DD HH:MM

An agent writes it in its own worktree when it starts work on that project and removes it in the commit that ends
the work, so main never carries one. Claims are read from every worktree's copy of wiki/projects/ (committed or
not), so another session sees one as soon as it is written. A claim whose worktree is gone, or holds another branch,
is shown as stale; a malformed or misplaced Claimed line, or a claim on a page that is not active, is shown as a
problem. Code fences and HTML comments are not read.

A worktree is in progress when its commit has commits not on origin/main, or a running Claude Code session holds
its lock (tools/agent/worktrees.py reads the lock). The full view fetches origin/main first (a failed fetch says so
and the counts use the local ref); --short never fetches. A clone without origin/main (a fresh or CI one) says so
in one line and lists every worktree but the main checkout, with commits ahead unknown. A part that cannot be read (gh, a host, the flag) prints
one line saying so; only a failure to read the worktrees themselves stops the run (exit 2).

"Waiting to ingest" (full view only) is one line per source, each naming the command that brings it in. It asks the
checks the pulls and the deploy gate already make, read-only: tools/hosts/deploy/pi_unpulled.sh (the gate's Pi check:
a Store, Operations Pro files, the DecoderPro roster) and tools/ops/pull_tables.sh --status (the Mac's Store). The
live STS is not checked:
its database keeps no change marker, so only a dump (make sts-pull) shows a change; the line gives the last dump's
time. A Pi that does not answer is one line per source ("Pi unreachable, not checked").
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from orient_overlap import full_lines, overlap_report, parse_prs, short_line
from orient_pages import BRANCH, Claim, parse_page  # this folder is on sys.path when the script runs; the tests add it

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = Path("wiki/projects")
BASE = "origin/main"
GIT_TIMEOUT = 20
FETCH_TIMEOUT = 20
NET_TIMEOUT = 40  # gh, the deploy stamps and the ingest checks (their ssh ConnectTimeout is 10 s per host)
SHORT_LIMIT = 10  # lines per section in --short, then "and N more"
if TYPE_CHECKING:
    from tools.agent.worktrees import Worktree


class OrientError(Exception):
    """A failure that stops the run: the worktrees cannot be read, or a claim cannot be written."""


@dataclass
class Tree:
    path: str
    branch: str | None
    head: str
    lock: str  # "", "session running", "session ended", or "locked: <reason>" for a lock with no session pid
    ahead: int | None = 0  # None when origin/main is not in the repo, so the count is unknown
    last: datetime | None = None


@dataclass
class DeployNote:
    """A line of a host's deploy status; paths counts the path lines listed under it when it ends in ":"."""
    text: str
    paths: int = 0


# ---------------------------------------------------------------- git

def git(*args: str, cwd: str | Path | None = None, timeout: int = GIT_TIMEOUT) -> str:
    """git's output (in cwd, default the repo); an OrientError naming the command when it fails or hangs."""
    cwd = cwd or ROOT
    cmd = ["git", "-C", str(cwd), *args]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as err:
        raise OrientError(f"git {' '.join(args)} took over {timeout} s (in {cwd})") from err
    except OSError as err:
        raise OrientError(f"git {' '.join(args)} could not run in {cwd}: {err}") from err
    if done.returncode != 0:
        raise OrientError(f"git {' '.join(args)} failed in {cwd}: {done.stderr.strip() or f'exit {done.returncode}'}")
    return done.stdout.strip()


def load_worktrees_module() -> ModuleType:
    path = ROOT / "tools/agent/worktrees.py"
    if not path.is_file():
        raise OrientError(f"{path} is missing; orient reads worktree locks with it")
    spec = importlib.util.spec_from_file_location("hart_agent_worktrees", path)
    if spec is None or spec.loader is None:
        raise OrientError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclass looks the module up by name
    spec.loader.exec_module(module)
    return module


def lock_state(wt: ModuleType, tree: Worktree) -> str:
    if not tree.locked:
        return ""
    if not wt.LOCK_PID.search(tree.lock_reason):
        return f"locked: {tree.lock_reason or 'no reason given'}"
    return "session ended" if wt.lock_session_gone(tree.lock_reason) else "session running"


def read_trees(wt: ModuleType) -> list[Tree]:
    """Every worktree with its lock state, commits ahead of origin/main and last commit time."""
    try:
        raw = wt.worktrees(ROOT)
    except wt.GitCommandError as err:
        raise OrientError(str(err)) from err
    if not raw:  # a repo always has its main checkout
        raise OrientError("git worktree list printed no worktree")
    known = base_exists()
    trees = [Tree(t.path, t.branch, t.head, lock_state(wt, t)) for t in raw]
    heads = sorted({t.head for t in trees if t.head and t.head.strip("0")})  # all zeros: no commit yet
    times = {}
    for line in git("log", "--no-walk=unsorted", "--format=%H %ct", *heads).splitlines():
        sha, stamp = line.split()
        times[sha] = datetime.fromtimestamp(int(stamp))
    ahead = {sha: int(git("rev-list", "--count", f"{BASE}..{sha}")) for sha in heads} if known else {}
    for t in trees:
        if t.head and t.head.strip("0") and t.head not in times:
            raise OrientError(f"git log gave no time for {t.head} ({t.path})")
        t.ahead, t.last = (ahead.get(t.head, 0) if known else None), times.get(t.head)
    return trees


def base_exists() -> bool:
    """Whether origin/main is in the repo. A fresh or CI clone may lack it: that is a stated case (commits ahead
    unknown), not an error; any other git failure is."""
    cmd = ["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", f"{BASE}^{{commit}}"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise OrientError(f"git rev-parse {BASE} took over {GIT_TIMEOUT} s") from None
    except OSError as err:
        raise OrientError(f"cannot run git: {err}") from err
    if done.returncode == 0:
        return True
    if done.returncode == 1 and not done.stderr.strip():
        return False
    raise OrientError(f"git rev-parse {BASE} failed in {ROOT}: {done.stderr.strip() or f'exit {done.returncode}'}")


BASE_MISSING = f"{BASE} not found; commits ahead unknown, so every worktree but the main checkout is listed"


def in_progress(trees: list[Tree]) -> list[Tree]:
    """Worktrees with commits not on origin/main or a running session's lock; when the count is unknown (no
    origin/main), every worktree but the main checkout, since none can be ruled out."""
    if any(t.ahead is None for t in trees):
        busy = trees[1:]
    else:
        busy = [t for t in trees if (t.ahead is not None and t.ahead > 0) or t.lock == "session running"]
    return sorted(busy, key=lambda t: t.last or datetime.min, reverse=True)


# ---------------------------------------------------------------- claims

def same_path(a: str, b: str) -> bool:
    return os.path.realpath(os.path.normpath(a)) == os.path.realpath(os.path.normpath(b))


def read_claims(trees: list[Tree], wt: ModuleType) -> tuple[list[tuple[Claim, str]], list[str]]:
    """Every claim in any worktree's wiki/projects/, each once, with its state against the worktree list; and the
    problem lines. A worktree folder that is gone is a problem unless git no longer lists it (the session-start
    sweep may remove one while orient reads); one without wiki/projects/ has nothing to read."""
    claims: dict[tuple, Claim] = {}
    sources: dict[tuple, list[str]] = {}
    problems: dict[tuple, list[str]] = {}
    listed: set[str] | None = None
    for t in trees:
        if not os.path.isdir(t.path):
            if listed is None:
                try:
                    listed = {os.path.realpath(w.path) for w in wt.worktrees(ROOT)}
                except wt.GitCommandError as err:
                    raise OrientError(str(err)) from err
            if os.path.realpath(t.path) in listed:
                problems.setdefault(("", t.path), []).append(
                    f"worktree {t.path} is missing on disk (git worktree prune)")
            continue
        folder = Path(t.path) / PROJECTS
        if not folder.is_dir():
            continue
        for page_path in sorted(folder.glob("*.md")):
            try:
                text = page_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as err:
                problems.setdefault((page_path.name, str(err)), []).append(f"{page_path}: cannot read ({err})")
                continue
            page = parse_page(page_path.name, text)
            for c in page.claims:
                key = (c.page, c.branch, os.path.normpath(c.path), c.since)
                claims.setdefault(key, c)
                sources.setdefault(key, []).append(t.path)
            raw = text.splitlines()
            for no, msg in page.problems:
                line = raw[no - 1] if 0 < no <= len(raw) else ""
                problems.setdefault((page_path.name, no, msg, line), []).append(
                    f"{PROJECTS / page_path.name}:{no} in {short_path(t.path)}: {msg}")
    out = []
    for key, c in sorted(claims.items(), key=lambda kv: (kv[1].page, kv[1].since)):
        out.append((c, claim_state(c, trees, sources[key])))
    lines = [p[0] + (f" (and {len(p) - 1} more copies)" if len(p) > 1 else "") for p in problems.values()]
    return out, lines


def claim_state(c: Claim, trees: list[Tree], found_in: list[str]) -> str:
    """The claim's worktree lock state, or STALE with why and the worktree copies that hold the line."""
    tree = next((t for t in trees if same_path(t.path, c.path)), None)
    if tree is not None and tree.branch == c.branch:
        return tree.lock or "worktree present"
    why = "no worktree at that path" if tree is None else f"that worktree is on {tree.branch or 'a detached HEAD'}"
    where = short_path(found_in[0]) + (f" and {len(found_in) - 1} more" if len(found_in) > 1 else "")
    return f"STALE: {why}; remove the line in {where}"


def short_path(path: str) -> str:
    """A path under the main checkout relative to it ("the main checkout" for itself); any other path as it is."""
    try:
        rel = str(Path(path).relative_to(ROOT_MAIN))
        return "the main checkout" if rel == "." else rel
    except ValueError:
        return path


ROOT_MAIN = ROOT  # the main checkout, set in main() once the worktree list is read


# ---------------------------------------------------------------- the network parts (full view only)

def run(cmd: list[str], timeout: int) -> tuple[int | None, str, str]:
    """(exit code, stdout, stderr) of cmd run in the repo; exit code None when it could not start or timed out, with
    the reason in stderr."""
    try:
        done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "", f"timed out after {timeout} s"
    except OSError as err:
        return None, "", str(err)
    return done.returncode, done.stdout, done.stderr


def first_line(text: str) -> str:
    return next((l.strip() for l in text.splitlines() if l.strip()), "no message")


def fetch_base() -> str:
    code, _, err = run(["git", "fetch", "--quiet", "origin", "main"], FETCH_TIMEOUT)
    if code == 0:
        return f"{BASE} fetched"
    return f"{BASE} NOT fetched ({first_line(err)}); counts use the local ref"


def operating() -> str:
    code, out, err = run([str(ROOT / "tools/hosts/operating.sh"), "status"], 10)
    if code in (0, 1):
        return first_line(out) if code == 0 else "not operating"
    return f"cannot read the operating flag ({first_line(err or out)})"


PR_LIMIT = 200


def open_prs() -> list[dict] | str:
    code, out, err = run(["gh", "pr", "list", "--state", "open", "--limit", str(PR_LIMIT),
                          "--json", "number,title,headRefName,isDraft,updatedAt,files"], NET_TIMEOUT)
    if code != 0:
        return f"gh pr list failed ({first_line(err or out)})"
    try:
        prs = json.loads(out or "[]")
    except ValueError:
        return "gh pr list printed something that is not JSON"
    if not isinstance(prs, list) or any(not isinstance(p, dict) or "number" not in p for p in prs):
        return "gh pr list printed an unexpected shape"
    return prs


def deploy_summary() -> list[str]:
    """One line per host from tools/hosts/deploy_status.sh --pi --win, plus its NOTE, WARNING and comparison lines."""
    code, out, err = run([str(ROOT / "tools/hosts/deploy_status.sh"), "--pi", "--win"], NET_TIMEOUT)
    if code is None:
        return [f"deploy status unavailable ({err})"]
    return summarize_deploy(out, code, err)


def summarize_deploy(out: str, code: int, err: str) -> list[str]:
    """Per host: a head line (commit, date, source) and its other lines; a list of paths after a line ending in ":"
    becomes a count on that line."""
    blocks: list[tuple[str, dict[str, str], list[DeployNote]]] = []
    for raw in out.splitlines():
        if raw.startswith("== "):
            blocks.append((raw[3:].strip(), {}, []))
        elif not blocks or not raw.strip():
            continue
        elif raw.startswith("    "):
            notes = blocks[-1][2]
            if notes and notes[-1].text.endswith(":"):
                notes[-1].paths += 1
            else:
                notes.append(DeployNote(raw.strip()))
        elif re.match(r"^  [a-z_0-9]+=", raw):
            key, _, value = raw.strip().partition("=")
            blocks[-1][1][key] = value
        else:
            blocks[-1][2].append(DeployNote(raw.strip()))
    lines = []
    for host, fields, notes in blocks:
        commit = fields.get("commit")
        lines.append(f"{host}: {commit[:8]} at {fields.get('date', '?')} ({fields.get('source', '?')})" if commit
                     else f"{host}:")
        for note in notes:
            text, count = note.text, note.paths
            if count:
                text = f"{text[:-1]} {count} path{'s' if count > 1 else ''} (make deploy-status lists them)"
            lines.append("  " + text)
    if not lines:
        return [f"deploy status printed nothing (exit {code}: {first_line(err)})"]
    if code not in (0, 1):  # 1 is a host without a stamp, already in its own line
        lines.append(f"deploy_status.sh exit {code}: {first_line(err)}")
    return lines


def site_deploy_lines() -> list[str]:
    """The website's last deploy from the main checkout's .deploy-manifest.json (ADR-040): commit, branch, time, and
    whether origin/main has commits under www/ that the site lacks."""
    path = ROOT_MAIN / ".deploy-manifest.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8")).get("deploy")
    except FileNotFoundError:
        return ["website: no deploy record"]
    except (OSError, ValueError) as exc:
        return [f"website: cannot read {path.name} ({exc})"]
    if not isinstance(record, dict) or not record.get("commit"):
        return ["website: the last deploy kept counts only (before ADR-040)"]
    commit = str(record["commit"])
    where = short_path(str(record.get("worktree", "?")))
    dirty = ", uncommitted changes" if record.get("dirty") else ""
    lines = [f"website: {commit[:8]} at {record.get('finished', '?')} ({record.get('branch', '?')}, {where}{dirty})"]
    code, out, err = run(["git", "rev-list", "--count", f"{commit}..{BASE}", "--", "www"], GIT_TIMEOUT)
    if code != 0:
        return lines + [f"  cannot compare the deployed commit with {BASE} ({first_line(err)})"]
    if out.strip() not in ("", "0"):
        lines.append(f"  {BASE} has {out.strip()} commit(s) under www/ that the site lacks")
    code, _, err = run(["git", "merge-base", "--is-ancestor", commit, BASE], GIT_TIMEOUT)
    if code == 1:
        lines.append(f"  NOTE: the deployed commit is not on {BASE}")
    elif code != 0:
        lines.append(f"  cannot tell whether the deployed commit is on {BASE} ({first_line(err)})")
    return lines


# ---------------------------------------------------------------- waiting to ingest (full view only)

PI_UNPULLED = "tools/hosts/deploy/pi_unpulled.sh"
MAC_TABLES = "tools/ops/pull_tables.sh"
SSH_DOWN = 255  # ssh's own status when the host did not answer (or refused the key)


def pi_unpulled() -> tuple[int | None, str, str]:
    return run([str(ROOT / PI_UNPULLED)], NET_TIMEOUT)


def mac_tables() -> tuple[int | None, str, str]:
    return run([str(ROOT / MAC_TABLES), "--status"], NET_TIMEOUT)


def not_checked(result: tuple[int | None, str, str], host: str) -> str | None:
    """Why a check gave no answer ("Pi unreachable, not checked (...)"), or None when it answered."""
    code, out, err = result
    if code == 0:
        return None
    if code is None:
        return f"{host} check {err}, not checked"
    if code == SSH_DOWN:
        return f"{host} unreachable, not checked ({first_line(err)})"
    return f"cannot check (exit {code}: {first_line(err or out)})"


# What the Pi and Mac checks compare a host with: the Store splits, the generated tables.xml, the Operations files and
# the DecoderPro roster master.
INGEST_REFS = ("jmri/layouts/hart/data/store_splits.csv", "jmri/layouts/hart/output/tables.xml",
               "jmri/layouts/hart/operations", "jmri/layouts/hart/roster")


def ingest_base_note() -> str | None:
    """A note when this checkout's copies of INGEST_REFS differ from origin/main's: the checks compare a host with
    this checkout, so a split or an Operations pull merged since would still show as waiting."""
    code, out, err = run(["git", "diff", "--quiet", BASE, "--", *INGEST_REFS], GIT_TIMEOUT)
    if code == 0:
        return None
    if code == 1:
        return (f"NOTE: compared with this checkout, whose Store splits, tables.xml or Operations files differ from "
                f"{BASE}; merge it in for exact answers")
    return f"NOTE: compared with this checkout; cannot tell whether it matches {BASE} ({first_line(err)})"


def ingest_lines(pi: tuple[int | None, str, str], mac: tuple[int | None, str, str]) -> list[str]:
    """One line per source: what a host holds that the repo lacks, and the command that brings it in."""
    lines = []
    why = not_checked(pi, "Pi")
    words = set(pi[1].split()) if why is None else set()
    if why is None and words - {"ops", "tables", "roster"}:
        why = f"cannot read the check's answer {pi[1].strip()!r}"
    lines.append("JMRI tables, Pi: " + (why or ("a PanelPro Store not yet split in (pulled or not)" if "tables" in words
                                                 else "nothing waiting")) + " (make tables-pull-pi)")
    code, out, err = mac
    answer = out.strip()
    if code == 0 and answer in ("waiting", "nothing", "absent"):
        state = {"waiting": "a PanelPro Store not yet split in (pulled or not)", "nothing": "nothing waiting",
                 "absent": "nothing waiting (no ~/JMRI_UserFiles/tables.xml)"}[answer]
    else:
        state = not_checked(mac, "Mac") or f"cannot read the check's answer {answer!r}"
    lines.append(f"JMRI tables, Mac: {state} (make tables-pull)")
    lines.append("Operations Pro, Pi: " + (why or ("the Pi's session changed the Operations files since the last "
                                                    "deploy or pull" if "ops" in words else "nothing waiting"))
                 + " (make ops-pull)")
    lines.append(f"STS, Pi: not checked: the live database keeps no change marker, only a dump shows a change; "
                 f"{last_sts_pull()} (make sts-pull)")
    lines.append("DecoderPro roster, Pi: " + (why or ("DecoderPro changed the roster since the last deploy (a "
                                                       "programming session or a new loco)" if "roster" in words
                                                       else "nothing waiting")) + " (make roster-pull)")
    return lines


STS_DUMP = re.compile(r"^sts_db3_(\d{8}-\d{6})\.sql\.gz$")


def last_sts_pull() -> str:
    """When make sts-pull last kept a dump of the live database (tools/hosts/pi_sts_pull_backups.sh writes
    sts_db3_<time>.sql.gz into STS_PI_COPY/db, else the main checkout's external/sts-docker-data/pi/db)."""
    folder = Path(os.environ.get("STS_PI_COPY") or ROOT_MAIN / "external/sts-docker-data/pi") / "db"
    try:
        stamps = [m.group(1) for m in (STS_DUMP.match(p.name) for p in folder.iterdir()) if m]
    except FileNotFoundError:
        return "no dump pulled to this Mac yet"
    except OSError as err:
        return f"cannot read {folder} ({err})"
    if not stamps:
        return "no dump pulled to this Mac yet"
    times = []
    for stamp in stamps:
        try:
            times.append(datetime.strptime(stamp, "%Y%m%d-%H%M%S"))
        except ValueError:  # a hand-named file with digits that are no date
            continue
    return f"last dump {max(times):%Y-%m-%d %H:%M}" if times else "no dump pulled to this Mac yet"


# ---------------------------------------------------------------- output

def tree_line(t: Tree, prs: dict[str, int], here: str) -> str:
    bits = [t.branch or "(detached)", "commits ahead unknown" if t.ahead is None else f"{t.ahead} ahead", f"last commit {t.last:%Y-%m-%d %H:%M}" if t.last else "no commit"]
    if t.lock:
        bits.append(t.lock if t.lock.startswith("locked") else f"locked, {t.lock}")
    if t.branch in prs:
        bits.append(f"PR #{prs[t.branch]}")
    bits.append(short_path(t.path) + (" (this session)" if same_path(t.path, here) else ""))
    return "  " + ", ".join(bits)


def claim_line(c: Claim, state: str) -> str:
    return f"  {c.page}: {c.branch}, {short_path(c.path)}, since {c.since} [{state}]"


def capped(lines: list[str], limit: int | None) -> list[str]:
    if limit is None or len(lines) <= limit:
        return lines
    return lines[:limit] + [f"  and {len(lines) - limit} more: make orient"]


def report(short: bool, here: str) -> list[str]:
    """The report's lines. The local parts come first, so a failure to read the worktrees stops the run before any
    network call starts; the full view then asks gh, the hosts and the flag side by side."""
    global ROOT_MAIN
    wt = load_worktrees_module()
    fetched = None if short else fetch_base()
    trees = read_trees(wt)
    ROOT_MAIN = Path(trees[0].path)
    claims, problems = read_claims(trees, wt)
    busy = in_progress(trees)
    prs: list[dict] | str = []
    deploys: list[str] = []
    flag = ""
    ingest: list[str] = []
    if not short:
        with ThreadPoolExecutor(max_workers=6) as pool:
            prs_job, deploys_job, flag_job = pool.submit(open_prs), pool.submit(deploy_summary), pool.submit(operating)
            pi_job, mac_job = pool.submit(pi_unpulled), pool.submit(mac_tables)
            prs, deploys, flag = prs_job.result(), deploys_job.result(), flag_job.result()
            pi, mac = pi_job.result(), mac_job.result()
        ingest = ingest_lines(pi, mac)
        note = ingest_base_note()
        ingest += [note] if note else []
    limit = SHORT_LIMIT if short else None
    out = [] if short else [f"Orient {datetime.now():%Y-%m-%d %H:%M} ({fetched})", f"Operating flag: {flag}"]
    if any(t.ahead is None for t in trees):
        out.append(BASE_MISSING)
    out.append(f"Claims ({len(claims)})" + (":" if claims else ": none"))
    out += capped([claim_line(c, state) for c, state in claims], limit)
    if problems:
        out.append(f"Claim problems ({len(problems)}):")
        out += capped(["  " + p for p in problems], limit)
    by_branch = {p["headRefName"]: p["number"] for p in prs} if isinstance(prs, list) else {}
    rule = (f"{BASE} not found, so all but the main checkout" if any(t.ahead is None for t in trees)
            else f"commits not on {BASE}, or locked by a running session")
    out.append(f"Worktrees in progress ({len(busy)}; {rule})" + (":" if busy else ": none"))
    out += capped([tree_line(t, by_branch, here) for t in busy], limit)
    pr_files = parse_prs(prs)
    overlap = overlap_report(ROOT_MAIN, trees, pr_files)
    if short:
        out += short_line(overlap)
        return out
    if isinstance(prs, str):
        out.append(f"Open PRs: {prs}")
    else:
        more = f", the first {PR_LIMIT} only" if len(prs) >= PR_LIMIT else ""
        out.append(f"Open PRs ({len(prs)}{more})" + (":" if prs else ": none"))
        out += [f"  #{p['number']}{' (draft)' if p.get('isDraft') else ''} {p.get('headRefName', '?')}: "
                f"{p.get('title', '')}" for p in prs]
    out += full_lines(overlap, "no open PRs read" if isinstance(prs, str) else f"{len(prs)} open PRs")
    out.append("Last deploys (compared with this checkout):")
    out += ["  " + line for line in deploys]
    out += ["  " + line for line in site_deploy_lines()]
    out.append("Waiting to ingest (what a host holds that the repo lacks):")
    out += ["  " + line for line in ingest]
    return out


# ---------------------------------------------------------------- claim / unclaim

def toplevel(cwd: str) -> Path:
    return Path(git("rev-parse", "--show-toplevel", cwd=cwd))


def resolve_page(arg: str, top: Path, cwd: str) -> Path:
    """PAGE as a path (from cwd) or a name in wiki/projects/; it must be a page in this worktree's wiki/projects/."""
    if not arg.strip():
        raise OrientError("name a page in wiki/projects/")
    folder = (top / PROJECTS).resolve()
    if "/" in arg or os.sep in arg:
        path = (Path(cwd) / arg).resolve()
    else:
        path = (folder / (arg if arg.endswith(".md") else f"{arg}.md")).resolve()
    if path.parent != folder or path.suffix != ".md":
        raise OrientError(f"{arg} is not a page in {top / PROJECTS}")
    if not path.is_file():
        raise OrientError(f"{path} does not exist")
    return path


def current_branch(top: Path) -> str:
    branch = git("branch", "--show-current", cwd=top)
    if not branch:
        raise OrientError("this worktree has a detached HEAD; claim from a branch")
    if branch == "main":
        raise OrientError("claims name a task branch, not main; work in a worktree (make wt)")
    if not BRANCH.match(branch):
        raise OrientError(f"branch {branch!r} cannot be written in a Claimed line")
    return branch


def claim(page_path: Path, branch: str, top: Path, now: datetime) -> str:
    text = page_path.read_text(encoding="utf-8")
    page = parse_page(page_path.name, text)
    if page.status_line is None:
        raise OrientError(f"{page_path} has no Status line to claim under")
    if page.status != "active":
        raise OrientError(f"{page_path} is {page.status}, not active; only active projects are claimed")
    if page.problems:
        raise OrientError(f"{page_path}:{page.problems[0][0]}: {page.problems[0][1]}; fix it first")
    if "," in str(top):
        raise OrientError(f"worktree path {top} holds a comma, which a Claimed line cannot carry")
    mine = [c for c in page.claims if c.branch == branch and same_path(c.path, str(top))]
    if mine:
        return f"{page_path.name} is already claimed by {branch} (line {mine[0].line})"
    lines = text.splitlines(keepends=True)
    at = page.status_line + len(page.claims)  # after the Status line and the claims under it (0-based index)
    entry = f"Claimed: {branch}, {top}, since {now:%Y-%m-%d %H:%M}\n"
    if at > 0 and not lines[at - 1].endswith("\n"):
        lines[at - 1] += "\n"
    lines.insert(at, entry)
    new = "".join(lines)
    after = parse_page(page_path.name, new)
    if after.problems or len(after.claims) != len(page.claims) + 1 or \
            not any(c.branch == branch and same_path(c.path, str(top)) for c in after.claims):
        raise OrientError(f"writing the claim would not leave one valid claim for {branch} in {page_path}; nothing written")
    page_path.write_text(new, encoding="utf-8")
    return f"claimed {page_path.name}: {entry.strip()}"


def unclaim(page_path: Path, branch: str) -> str:
    text = page_path.read_text(encoding="utf-8")
    page = parse_page(page_path.name, text)
    drop = {c.line for c in page.claims if c.branch == branch}
    if not drop:
        raise OrientError(f"{page_path.name} has no claim by {branch}")
    lines = text.splitlines(keepends=True)
    new = "".join(l for no, l in enumerate(lines, 1) if no not in drop)
    after = parse_page(page_path.name, new)
    if any(c.branch == branch for c in after.claims) or len(after.claims) != len(page.claims) - len(drop):
        raise OrientError(f"removing the claim did not leave the other claims in {page_path} intact; nothing written")
    page_path.write_text(new, encoding="utf-8")
    return f"unclaimed {page_path.name} ({len(drop)} line{'s' if len(drop) > 1 else ''} by {branch})"


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--short", action="store_true", help="claims, worktrees in progress and overlap only, no network")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("claim", help="write this worktree's Claimed line under PAGE's Status line")
    c.add_argument("page")
    u = sub.add_parser("unclaim", help="remove a Claimed line from PAGE")
    u.add_argument("page")
    u.add_argument("--branch", help="whose claim to remove (default: this worktree's branch)")
    args = ap.parse_args(argv)
    cwd = os.getcwd()
    try:
        if args.cmd in ("claim", "unclaim"):
            if args.short:
                raise OrientError("--short is for the report, not for claim or unclaim")
            top = toplevel(cwd)
            page = resolve_page(args.page, top, cwd)
            if args.cmd == "claim":
                print(claim(page, current_branch(top), top, datetime.now()))
            else:
                branch = args.branch or current_branch(top)
                if not BRANCH.match(branch):
                    raise OrientError(f"invalid branch {branch!r}")
                print(unclaim(page, branch))
            return 0
        print("\n".join(report(args.short, cwd)))
        return 0
    except OrientError as err:
        print(f"orient: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
