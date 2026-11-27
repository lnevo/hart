"""Fill the "What we added to JMRI" page's counts and host lists from the repository.

behind/jmri-additions.html marks each number and host list that describes the
railroad's data with a region:

    <!--ja:planned-masts-->79<!--/ja-->

fill() replaces each region's contents with the value read from the checkout:

- the masts the device master plans (the device master, all levels), split into those with
  lamps and the hidden staging masts (virtual, IF$vsm);
- the masts signal_coordinator.py hands over (those whose heads are LCOS heads, IH plus node and signal number, the
  same rule as its _collect_beans, now in sml_beans.py) and their Signal Mast Logic destinations in tables.xml, against the rest;
- the plant switches panel_status.py flips (M2T/MTT turnouts with both feedback sensors, its
  _included_plant_turnouts);
- which hosts install each Jython script (tools/hosts/pi/jython_scripts.txt for the Pi and the Mac, the Windows
  apply script).

A region the code does not know, or a known one missing from the page, stops the build. The prose around the
regions is written by hand and checked by the repo audits (www/README.md, "Pages that describe the repo").

    python3 www/scripts/jmri_additions_page.py           # rewrite the page
    python3 www/scripts/jmri_additions_page.py --check   # exit 1 when the page is stale (tools/check.sh)

prepare_github_pages.py fills the built copy on every site build.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import re
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import coordinator, devices, paths, tables as T  # noqa: E402

ROOT = paths.REPO_ROOT

PAGE_REL = "behind/jmri-additions.html"
REGION = re.compile(r"<!--ja:([a-z0-9-]+)-->(.*?)<!--/ja-->", re.S)
DATA = "jmri/layouts/hart/data"          # the master is under it (devices.master_path)
DEVICE_LEVELS = {"main and upper": ("2", "3"), "staging": ("1",)}      # the master's levels of each group of masts
COORDINATOR = "jmri/scripts/signal_coordinator.py"
PANEL_STATUS = "jmri/layouts/hart/scripts/panel_status.py"
TABLES = "jmri/layouts/hart/output/tables.xml"
SPLIT_SCRIPTS = (COORDINATOR, PANEL_STATUS)   # the Jython scripts whose code is split into parts beside them
HEAD_IN_MAST = re.compile(r"\(IH(\d+)\)")   # signal_coordinator._HEAD_IN_MAST, without the brackets
WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()

# Every host installs the jython of one list (tools/hosts/pi/jython_scripts.txt, read by jython_list.sh; Windows reads
# it with tools/hosts/windows/jython_list.ps1): the rows of these roles are each host's scripts; the sibling and part
# rows are parts of the split scripts.
JYTHON_LIST = "tools/hosts/pi/jython_scripts.txt"
JYTHON_READER = "tools/hosts/pi/jython_list.sh"
LIST_ROLES = {"Pi": ("startup", "macpi", "pi"), "Windows": ("startup",), "Mac": ("startup", "macpi")}
HOST_ORDER = ("Pi", "Windows", "Mac")
HOST_NAMES = {"Pi": "the Pi", "Windows": "Windows", "Mac": "the Mac"}
SCRIPTS = ("signal_coordinator.py", "panel_status.py", "hide_cats_desk_windows.py", "hide_band_panels.py",
           "jmri_cmd_watcher.py",
           "sts_car_sync.py", "mimic_relay.py")


class PageError(Exception):
    pass


def word(n: int) -> str:
    return WORDS[n] if n < len(WORDS) else str(n)


def _and(items: list[str]) -> str:
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# The loader both split scripts import their modules with (jmri/scripts/jython_siblings.py): shipped beside them.
SIBLING_LOADER = "jython_siblings.py"


def _siblings(root: Path) -> set[str]:
    """The .py files of the modules signal_coordinator.py loads and of the parts panel_status.py runs
    (hartlib.coordinator), and the loader they share: shipped as parts of those scripts."""
    try:
        return {f"{m}.py" for script in SPLIT_SCRIPTS
                for m in coordinator.sibling_modules(root / script)} | {SIBLING_LOADER}
    except coordinator.CoordinatorError as e:
        raise PageError(str(e)) from e


def _lcos_range(root: Path) -> tuple[int, int]:
    """The LCOS signal numbers signal_coordinator.py accepts, read from it and its modules so the two cannot differ."""
    try:
        src = coordinator.source(root / COORDINATOR)
    except coordinator.CoordinatorError as e:
        raise PageError(str(e)) from e
    got = {k: int(v) for k, v in re.findall(r"^_LCOS_SIGNAL_UID_(MIN|MAX)\s*=\s*(\d+)", src, re.M)}
    if set(got) != {"MIN", "MAX"}:
        raise PageError("signal_coordinator.py no longer sets _LCOS_SIGNAL_UID_MIN and _MAX; update this script")
    return got["MIN"], got["MAX"]


def is_lcos_head(packed: str, lo: int, hi: int) -> bool:
    """signal_coordinator._packed_is_lcos_signal: node*100 + signal number, the node written in octal digits."""
    n = int(packed)
    return lo <= n % 100 <= hi and set(str(n // 100)) <= set("01234567")


def jython_rows(root: Path = ROOT) -> list[tuple[str, str]]:
    """The (role, path) rows of JYTHON_LIST as its reader, jython_list.sh, prints them; PageError with the reader's
    message when it refuses the list."""
    try:
        done = subprocess.run(["bash", "-c", 'source "$1" && jython_list "$2"', "jython_list",
                               str(root / JYTHON_READER), str(root / JYTHON_LIST)],
                              capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PageError("cannot run %s: %s" % (JYTHON_READER, e)) from e
    if done.returncode != 0:
        raise PageError("%s: %s" % (JYTHON_LIST, done.stderr.strip() or "jython_list.sh failed"))
    return [(role, path) for role, path in (line.split(" ", 1) for line in done.stdout.splitlines())]


def host_lists(root: Path = ROOT) -> dict[str, set[str]]:
    """The Jython scripts each host's deploy copies into its profile's jython folder. The modules
    signal_coordinator.py loads and the parts panel_status.py runs are parts of them, not scripts of their own,
    so they are left out."""
    parts = _siblings(root)
    rows = jython_rows(root)
    out = {host: {Path(path).name for role, path in rows if role in roles} - parts
           for host, roles in LIST_ROLES.items()}
    unknown = set().union(*out.values()) - set(SCRIPTS)
    if unknown:
        raise PageError("hosts install Jython scripts the page does not list: %s" % sorted(unknown))
    return out


def facts(root: Path = ROOT) -> dict:
    """Every number the page shows; a missing column or an unreadable file stops with a PageError."""
    try:
        return _facts(root)
    except KeyError as e:
        raise PageError("a column the page needs is missing: %s" % e) from e
    except ET.ParseError as e:
        raise PageError("%s does not parse: %s" % (TABLES, e)) from e


def _facts(root: Path) -> dict:
    planned = {}
    for label, levels in DEVICE_LEVELS.items():
        planned[label] = [r for _line, r in devices.device_map_lines(levels, devices.master_path(root / DATA)) if r["layer"] == "mast"]
    masts = [m for rows in planned.values() for m in rows]
    hidden = [m for m in masts if m["role"] == "hidden"]

    lo, hi = _lcos_range(root)
    tab = T.read(root / TABLES)
    field, field_masts = set(), 0
    for el in tab.iter():
        if isinstance(el.tag, str) and el.tag.endswith("signalmast") and el.find("systemName") is not None:
            sys_name = T.system_name(el)
            if any(is_lcos_head(p, lo, hi) for p in HEAD_IN_MAST.findall(sys_name)):
                field.add(sys_name)
                field_masts += 1
                if T.user_name(el):
                    field.add(T.user_name(el))
    sources = tab.findall(".//signalmastlogics/signalmastlogic")
    if not sources:
        raise PageError("tables.xml has no Signal Mast Logic")
    wired_src = [s for s in sources if (s.findtext("sourceSignalMast") or "") in field]
    dests = lambda group: sum(len(s.findall("destinationMast")) for s in group)  # noqa: E731

    plant = {T.system_name(t) for t in tab.findall("./turnouts/turnout")   # the turnout table, as JMRI's manager
             if T.system_name(t).startswith(("M2T", "MTT")) and t.get("sensor1") and t.get("sensor2")}
    return {
        "planned": len(masts),
        "planned-mu": len(planned["main and upper"]),
        "planned-staging": len(planned["staging"]),
        "lit": len(masts) - len(hidden),
        "hidden": len(hidden),
        "wired": field_masts,
        "wired-dests": dests(wired_src),
        "other": len(sources) - len(wired_src),
        "other-dests": dests(sources) - dests(wired_src),
        "plant": len(plant),
        "hosts": host_lists(root),
        "parts": _parts(root),
    }


def _parts(root: Path) -> dict[str, tuple[str, ...]]:
    """Each split script's parts, in load order, keyed by the script's file name."""
    try:
        return {Path(script).name: coordinator.sibling_modules(root / script) for script in SPLIT_SCRIPTS}
    except coordinator.CoordinatorError as e:
        raise PageError(str(e)) from e


def _parts_sentence(parts: tuple[str, ...]) -> str:
    files = _and(["<code>%s.py</code>" % m for m in parts])
    n = word(len(parts)).capitalize()
    if len(parts) == 1:
        return "One module beside it holds the rest of its code and is deployed with it: %s." % files
    return "%s modules beside it hold the rest of its code and are deployed with it: %s." % (n, files)


def _hosts_cell(script: str, hosts: dict) -> str:
    on = [h for h in HOST_ORDER if script in hosts[h]]
    if not on:
        raise PageError("%s is on the page but no host installs it" % script)
    if len(on) == len(HOST_ORDER):
        return "every host (" + _and([HOST_NAMES[h] for h in HOST_ORDER]) + ")"
    return _and([HOST_NAMES[h] for h in on]) + (" only" if len(on) == 1 else "")


def regions(f: dict) -> dict:
    vals = {
        "planned-masts": str(f["planned"]),
        "planned-mu": str(f["planned-mu"]),
        "planned-staging": str(f["planned-staging"]),
        "planned-lit": str(f["lit"]),
        "planned-hidden": word(f["hidden"]),
        "wired-masts": word(f["wired"]),
        "wired-masts-noun": "mast" if f["wired"] == 1 else "masts",
        "wired-dests": word(f["wired-dests"]),
        "other-sources": str(f["other"]),
        "other-dests": str(f["other-dests"]),
        "plant-turnouts": str(f["plant"]),
        "script-count": word(len(SCRIPTS)),
        "script-count-cap": word(len(SCRIPTS)).capitalize(),
    }
    for s in SCRIPTS:
        vals["hosts-" + s[:-3].replace("_", "-")] = _hosts_cell(s, f["hosts"])
    for s, parts in f["parts"].items():
        vals["parts-" + s[:-3].replace("_", "-")] = _parts_sentence(parts)
    return vals


def fill(page: str, f: dict) -> str:
    vals = regions(f)
    seen = set()

    def sub(m):
        key = m.group(1)
        if key not in vals:
            raise PageError("unknown region ja:%s in %s" % (key, PAGE_REL))
        seen.add(key)
        return "<!--ja:%s-->%s<!--/ja-->" % (key, vals[key])

    out = REGION.sub(sub, page)
    missing = set(vals) - seen
    if missing:
        raise PageError("regions missing from %s: %s" % (PAGE_REL, ", ".join(sorted(missing))))
    return out


def write(www: Path, root: Path = ROOT) -> bool:
    path = Path(www) / PAGE_REL
    old = path.read_text(encoding="utf-8")
    new = fill(old, facts(root))
    if new != old:
        path.write_text(new, encoding="utf-8")
    return new != old


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    www = ROOT / "www"
    try:
        if "--check" in argv:
            old = (www / PAGE_REL).read_text(encoding="utf-8")
            if fill(old, facts()) != old:
                print("www/%s is stale; run python3 www/scripts/jmri_additions_page.py" % PAGE_REL)
                return 1
            print("jmri-additions.html is current")
            return 0
        print(("wrote" if write(www) else "unchanged:") + " www/" + PAGE_REL)
        return 0
    except (PageError, OSError, ValueError) as e:
        print("jmri_additions_page: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
