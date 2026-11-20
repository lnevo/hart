"""Fill the "What we added to JMRI" page's counts and host lists from the repository.

behind/jmri-additions.html marks each number and host list that describes the
railroad's data with a region:

    <!--ja:planned-masts-->79<!--/ja-->

fill() replaces each region's contents with the value read from the checkout:

- the masts the device master plans (devices.csv, all levels), split into those with
  lamps and the hidden staging masts (virtual, IF$vsm);
- the masts signal_coordinator.py hands over (those whose heads are LCOS heads, IH plus node and signal number, the
  same rule as its _collect_beans) and their Signal Mast Logic destinations in tables.xml, against the rest;
- the plant switches panel_status.py flips (M2T/MTT turnouts with both feedback sensors, its
  _included_plant_turnouts);
- which hosts install each Jython script (sync_hart_package.sh for the Mac, the Pi and Windows apply scripts).

A region the code does not know, or a known one missing from the page, stops the build. The prose around the
regions is written by hand and checked by the repo audits (www/README.md, "Pages that describe the repo").

    python3 www/scripts/jmri_additions_page.py           # rewrite the page
    python3 www/scripts/jmri_additions_page.py --check   # exit 1 when the page is stale (tools/check.sh)

prepare_github_pages.py fills the built copy on every site build.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/hartlib/src")]
from hartlib import devices, tables as T  # noqa: E402

PAGE_REL = "behind/jmri-additions.html"
REGION = re.compile(r"<!--ja:([a-z0-9-]+)-->(.*?)<!--/ja-->", re.S)
DEVICES = "jmri/layouts/hart/data/devices.csv"
DEVICE_LEVELS = {"main and upper": ("2", "3"), "staging": ("1",)}      # the master's levels of each group of masts
COORDINATOR = "jmri/scripts/signal_coordinator.py"
TABLES = "jmri/layouts/hart/output/tables.xml"
HEAD_IN_MAST = re.compile(r"\(IH(\d+)\)")   # signal_coordinator._HEAD_IN_MAST, without the brackets
WORDS = "zero one two three four five six seven eight nine ten eleven twelve".split()

# Where each host's Jython list lives: (file, the line that opens the list). Each list runs to its closing bracket.
# The list closes with ")" on a line of its own.
HOST_LISTS = {
    "Pi": ("tools/hosts/pi/apply_hart_package_local.sh", "JYTHON=("),
    "Windows": ("tools/hosts/windows/apply_hart_package_local.ps1", "$jythonSrc = @("),
    "Mac": ("tools/hosts/sync_hart_package.sh", "JYTHON_STARTUP_SCRIPTS=("),
}
HOST_ORDER = ("Pi", "Windows", "Mac")
HOST_NAMES = {"Pi": "the Pi", "Windows": "Windows", "Mac": "the Mac"}
LIST_END = re.compile(r"^\s*\)\s*$", re.M)
SCRIPTS = ("signal_coordinator.py", "panel_status.py", "hide_cats_desk_windows.py", "jmri_cmd_watcher.py",
           "sts_car_sync.py", "mimic_relay.py")


class PageError(Exception):
    pass


def word(n: int) -> str:
    return WORDS[n] if n < len(WORDS) else str(n)


def _and(items: list[str]) -> str:
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _lcos_range(root: Path) -> tuple[int, int]:
    """The LCOS signal numbers signal_coordinator.py accepts, read from it so the two cannot differ."""
    src = (root / COORDINATOR).read_text(encoding="utf-8")
    got = {k: int(v) for k, v in re.findall(r"^_LCOS_SIGNAL_UID_(MIN|MAX)\s*=\s*(\d+)", src, re.M)}
    if set(got) != {"MIN", "MAX"}:
        raise PageError("signal_coordinator.py no longer sets _LCOS_SIGNAL_UID_MIN and _MAX; update this script")
    return got["MIN"], got["MAX"]


def is_lcos_head(packed: str, lo: int, hi: int) -> bool:
    """signal_coordinator._packed_is_lcos_signal: node*100 + signal number, the node written in octal digits."""
    n = int(packed)
    return lo <= n % 100 <= hi and set(str(n // 100)) <= set("01234567")


def host_lists(root: Path = ROOT) -> dict[str, set[str]]:
    """The Jython scripts each host's deploy copies into its profile's jython folder."""
    out = {}
    for host, (rel, opener) in HOST_LISTS.items():
        text = (root / rel).read_text(encoding="utf-8")
        start = text.find(opener)
        end = LIST_END.search(text, start + len(opener)) if start >= 0 else None
        if end is None:
            raise PageError("%s: no %r list of Jython scripts closed by a line holding only ')'" % (rel, opener))
        out[host] = set(re.findall(r"([a-z_]+\.py)", text[start + len(opener):end.start()]))
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
        planned[label] = [r for _line, r in devices.device_map_lines(levels, root / DEVICES) if r["layer"] == "mast"]
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
    }


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
