"""Fill the repository guide's lists and counts from the repository itself.

library/repository-guide.html marks each list and number that describes the
repository's shape with a region:

    <!--rg:folder-count-->ten<!--/rg-->

fill() replaces each region's contents with the value read from the checkout
(git's tracked folders, .gitmodules, the hartlib package), so
the page cannot drift from the repository. The descriptions are kept here, one
per folder, submodule and module; a folder, submodule or module with no
description, or a description for one that is gone, stops the build. The prose
around the regions is still written by hand and checked by the repo audits
(www/README.md, "Pages that describe the repo").

    python3 www/scripts/repo_guide_page.py           # rewrite the page
    python3 www/scripts/repo_guide_page.py --check   # exit 1 when the page is stale (tools/check.sh)

prepare_github_pages.py fills the built copy on every site build.
"""
from __future__ import annotations

import argparse
import configparser
import html
import re
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[2]
PAGE_REL = "library/repository-guide.html"
REGION = re.compile(r"<!--rg:([a-z0-9-]+)-->(.*?)<!--/rg-->", re.S)
WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
         "sixteen seventeen eighteen nineteen twenty").split()

# Top-level folders, in page order. Tracked folders come from git; an untracked one is marked False and need not
# exist in a clone. Dot folders (tool settings) are left out.
FOLDERS = {
    "jmri": (True, "The layout's JMRI files: the tables file, the Operations Pro files, the layout data, and the "
                   "scripts that build and check them. Also the icons and web pages JMRI uses."),
    "cats": (True, "The CATS dispatcher desks only: the CTC and ABS desks built from the schematic, their scripts, "
                   "and the reference panels they were modelled on."),
    "ops": (True, "Operations: the car repository and its tools (<code>ops/hart-ops/</code>), station maps, "
                  "car-card intake batches, and runbooks for the parts that run outside JMRI."),
    "docs": (True, "Every document written for the railroad: wiring, CTC, benchwork, JMRI notes and the crew "
                   "publications. <code>docs/INDEX.md</code> lists them, newest first."),
    "www": (True, "The source of this website and the scripts that build and publish it."),
    "tools": (True, "Repository-wide tools: the checks, the shared library, the AnyRail plan reader, the schematic "
                    "and panel builders, host and deploy scripts, MQTT helpers and the LCOS mimic."),
    "external": (True, "The {n} submodules, and the STS data folder."),
    "wiki": (True, "Decision records, the live status of the railroad, and one page per pipeline."),
    "media": (False, "Photos, video and research material. Kept on the Mac, not in git."),
    "archive": (True, "Retired files, kept for reference, grouped into <code>code/</code>, <code>data/</code> and "
                       "<code>history/</code>. Nothing in it runs."),
}

# Folders under jmri/layouts/hart/, in page order. Keys are joined with ", " when they share a row.
LAYOUT_TREE = {
    ("output",): "<code>tables.xml</code>, the one tables file, with all three panels in it",
    ("data",): "The device master, switch files, block lengths, control points, the schematic's inputs, "
               "and HART's settings for the STS-to-JMRI refresh",
    ("operations",): "The {ops} Operations Pro files",
    ("roster",): "The DecoderPro roster: roster.xml and one entry file per loco, which the deploy installs on every host",
    ("scripts",): "{scripts} scripts: most build, repair and check the tables on the Mac, and some run inside JMRI",
    ("ctc", "dispatcher"): "The USS CTC machine's icons and guide; the Dispatcher System's options and train files. "
                           "Parked since the helix-join release (November 2026)",
    ("parked",): "The Entry/Exit, Dispatcher System and USS CTC data kept out of the active tables while those "
                 "features are parked",
    ("anyrail",): "The AnyRail export the first panels were built from, kept for reference. The schematic now reads "
                  "the plan itself (see <a href=\"#owners\">Where each fact lives</a>)",
}

# Submodules by folder under external/: what it is, how it connects.
SUBMODULES = {
    "lcos-bridge": ("Firmware for the Arduino that listens to the LCOS radio nodes, and the bridge that turns their "
                    "messages into MQTT", "The bridge runs on the Windows PC and publishes to the broker on the Pi"),
    "sts-docker": ("The STS traffic simulator packaged to run in Docker",
                   "The Pi runs its release build as the live STS; the Mac runs a copy for testing"),
    "sts-plugins": ("Addons for STS: the track scale, coke orders, the JMRI refresh and HART's own settings",
                    "Built into the STS image"),
    "sts-helpers": ("Seeding, warm starts and switch lists for STS", "Run on the Mac, fed from the car repository"),
    "model-railroad-skills": ("Skills and plugins for AI coding agents: JMRI panels, signals, MQTT, CATS, STS, "
                              "Operations Pro, car cards and the schematic drawing",
                              "Installed into the AI tools; the schematic plugin draws the panels and desks"),
    "jmri-cs105-roster-sync": ("Copies the JMRI roster into the TCS CS-105 command station",
                               "Run from <code>tools/ops/</code> after a roster change"),
}

# hartlib modules. The four main parts have their own paragraphs on the page; every other module is named in the
# sentence before them with a short phrase. railroad_facts, railroad_invariants and device_rows are parts of railroad,
# and store_items and store_plan of store_split.
HARTLIB_MAIN = ("paths", "tables", "hosts", "railroad")
HARTLIB_PARTS = {"railroad_facts": "railroad", "railroad_invariants": "railroad", "device_rows": "railroad",
                 "store_items": "store_split", "store_plan": "store_split",
                 "tables_sections": "tables_build", "tables_normal": "tables_build", "jmri_bean": "tables_build",
                 "startup_logixng": "tables_build", "tables_sml": "tables_build", "tables_roundtrip": "tables_build"}
HARTLIB_OTHER = {
    "names": "the DCC group of a JMRI comment",
    "devices": "the device master, its dictionary and its checks",
    "device_ids": "each device's ID, taken from the track plan rather than its name",
    "device_changes": "what a build changes in the device master: new, gone and renamed devices",
    "track_names": "the owner's track names, kept by ID, and how they reach the schematic drawing",
    "tables_build": "the template and the other parts the generated tables.xml is built from",
    "store_split": "the split of a pulled PanelPro Store back into the template and the device master",
    "cats": "the CATS desk conventions",
    "parked": "the parked features",
    "jmri_profile": "the edits to a JMRI profile: startup actions, window sizes and preferences",
    "level_devices": "the main and upper levels' device names",
    "level_masts": "their control-point masts",
    "map_revision": "the station maps' revision",
    "layer_files": "the schematic's layer files, a section per sheet",
    "wiring": "the physical wiring source (wiring.csv)",
    "block_numbering": "the main and upper blocks' JMRI numbers, from block_numbering.csv",
    "hand_lists":"the owner's hand lists: block overrides, main lines and the parked USS board",
    "hand_tables":"the railroad names in the data masters and the list of tables in code that hold railroad data",
    "drawing_keys": "which device each piece of the drawing is, keyed by device ID",
    "film_pace": "the pace of the panel and schematic films",
    "files": "an atomic file write and the list of tracked files",
    "operations": "the Operations Pro rosters' cars, engines and trains",
    "coordinator": "the signal coordinator script and the modules it loads",
    "places": "the stations and control points by id, as the devices and masts name them",
    "occupancy_bindings": "the CATS desks' occupancy bindings, each block by its ID",
    "block_lengths": "each block's plan length and measured length, and the operating length the Dispatcher takes",
    "errors": "the error classes every hartlib reader raises",
    "levels": "the layout's levels (1, 2, 3) and their one parser",
    "store_keys": "the typed keys that pair a Store's items with the template's",
    "device_row_checks": "the device master's row checks",
    "switch_rows": "the switch list's rows, read and checked",
}


class PageError(Exception):
    pass


class Facts(TypedDict):
    """What facts() reads from the checkout for the page: counts of submodules, layout scripts and Operations files."""
    subs: int
    scripts: int
    ops: int


def _git(*args: str, root: Path) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def _index(root: Path) -> list[str]:
    """Every path in git's index: what the next commit holds, so check.sh before a commit sees what CI will."""
    return [p for p in _git("ls-files", "-z", root=root).split("\0") if p]


def _dirs(files: list[str], under: str) -> set[str]:
    """The folders directly under `under` ("" for the top) that hold an indexed file."""
    depth = under.count("/")
    return {p.split("/")[depth] for p in files if p.startswith(under) and p.count("/") > depth}


def _and(items: list[str]) -> str:
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def word(n: int) -> str:
    return WORDS[n] if n < len(WORDS) else str(n)


def facts(root: Path = ROOT) -> Facts:
    """Read every fact the page shows, stopping on any folder, submodule or module the descriptions do not cover."""
    files = _index(root)
    tracked = {d for d in _dirs(files, "") if not d.startswith(".")}
    listed = {k for k, (in_git, _) in FOLDERS.items() if in_git}
    if tracked != listed:
        raise PageError("top-level folders differ from FOLDERS in repo_guide_page.py: not described %s, gone %s"
                        % (sorted(tracked - listed) or "none", sorted(listed - tracked) or "none"))

    gm = configparser.ConfigParser()
    gm.read_string(_git("show", ":.gitmodules", root=root))
    subs = [gm[s]["path"] for s in gm.sections()]
    outside = [p for p in subs if not p.startswith("external/")]
    if outside:
        raise PageError("submodules outside external/: %s; the page says all live there" % outside)
    names = {p.split("/", 1)[1] for p in subs}
    if names != set(SUBMODULES):
        raise PageError("submodules differ from SUBMODULES in repo_guide_page.py: not described %s, gone %s"
                        % (sorted(names - set(SUBMODULES)) or "none", sorted(set(SUBMODULES) - names) or "none"))

    tree = _dirs(files, "jmri/layouts/hart/")
    tree_listed = {d for key in LAYOUT_TREE for d in key}
    if tree != tree_listed:
        raise PageError("jmri/layouts/hart/ folders differ from LAYOUT_TREE in repo_guide_page.py: not described %s, "
                        "gone %s" % (sorted(tree - tree_listed) or "none", sorted(tree_listed - tree) or "none"))
    scripts = [p for p in files if p.startswith("jmri/layouts/hart/scripts/")
               and p.count("/") == 4]   # files directly in scripts/, not its tests or speedmatch folders
    ops = [p for p in files if p.startswith("jmri/layouts/hart/operations/") and p.endswith(".xml")]

    lib = "tools/hartlib/src/hartlib/"
    mods = {p[len(lib):-3] for p in files if p.startswith(lib) and p.endswith(".py") and p.count("/") == 4} - {"__init__"}
    covered = set(HARTLIB_MAIN) | set(HARTLIB_PARTS) | set(HARTLIB_OTHER)
    if mods != covered:
        raise PageError("hartlib modules differ from repo_guide_page.py: not described %s, gone %s"
                        % (sorted(mods - covered) or "none", sorted(covered - mods) or "none"))

    return Facts(subs=len(names), scripts=len(scripts), ops=len(ops))


def regions(f: Facts) -> dict[str, str]:
    """The contents of each region, by key."""
    sub_n = f["subs"]
    folder_rows = "\n".join(
        '                <tr><td><code>%s/</code></td><td>%s</td></tr>' % (k, d.replace("{n}", word(sub_n)))
        for k, (_, d) in FOLDERS.items())
    tree_rows = "\n".join(
        '                <tr><td>%s</td><td>%s</td></tr>'
        % (", ".join("<code>%s/</code>" % d for d in key), d_.replace("{ops}", word(f["ops"])).replace("{scripts}", str(f["scripts"])))
        for key, d_ in LAYOUT_TREE.items())
    sub_rows = "\n".join(
        '                <tr><td><code>%s/</code></td><td>%s</td><td>%s</td></tr>' % (k, what, how)
        for k, (what, how) in SUBMODULES.items())
    other = list(HARTLIB_OTHER.values())
    return {
        "folder-count": word(len(FOLDERS)),
        "folders": "\n" + folder_rows + "\n              ",
        "layout-tree": "\n" + tree_rows + "\n              ",
        "ops-count": word(f["ops"]),
        "submodule-count": word(sub_n),
        "submodule-count-cap": word(sub_n).capitalize(),
        "submodules": "\n" + sub_rows + "\n              ",
        "hartlib-main-count": word(len(HARTLIB_MAIN)),
        "hartlib-other": _and(other),
    }


def fill(page: str, f: Facts) -> str:
    vals = regions(f)
    seen: set[str] = set()

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in vals:
            raise PageError("unknown region rg:%s in %s" % (key, PAGE_REL))
        seen.add(key)
        return "<!--rg:%s-->%s<!--/rg-->" % (key, vals[key])

    out = REGION.sub(sub, page)
    missing = set(vals) - seen
    if missing:
        raise PageError("regions missing from %s: %s" % (PAGE_REL, ", ".join(sorted(missing))))
    return out


def write(www: Path, root: Path = ROOT) -> bool:
    """Fill the page under www; True when it changed."""
    path = Path(www) / PAGE_REL
    old = path.read_text(encoding="utf-8")
    new = fill(old, facts(root))
    if new != old:
        path.write_text(new, encoding="utf-8")
    return new != old


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill www/%s's lists and counts from the checkout." % PAGE_REL)
    parser.add_argument("--check", action="store_true", help="exit 1 when the page is stale; write nothing")
    args = parser.parse_args(argv)      # an unknown argument is a usage error (exit 2), never a write run
    www = ROOT / "www"
    try:
        if args.check:
            old = (www / PAGE_REL).read_text(encoding="utf-8")
            if fill(old, facts()) != old:
                print("www/%s is stale; run python3 www/scripts/repo_guide_page.py" % PAGE_REL, file=sys.stderr)
                return 1
            print("repository-guide.html is current")
            return 0
        print(("wrote" if write(www) else "unchanged:") + " www/" + PAGE_REL)
        return 0
    except PageError as e:
        print("repo_guide_page: %s" % html.unescape(str(e)), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print("repo_guide_page: git %s failed: %s" % (" ".join(e.cmd[3:]), (e.stderr or "").strip()), file=sys.stderr)
        return 1
    except OSError as e:
        print("repo_guide_page: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
