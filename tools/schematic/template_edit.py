#!/usr/bin/env python3
"""Edit what PanelPro owns in tables.xml, in the template (data/tables_template.xml), then rebuild tables.xml.

    python3 tools/schematic/template_edit.py list [memory|sensor|clock|setting|logixng]
    python3 tools/schematic/template_edit.py memory add IMNAME --user-name "Name" [--comment "Text"]
    python3 tools/schematic/template_edit.py memory set IMNAME [--user-name "Name"] [--comment "Text"]
    python3 tools/schematic/template_edit.py memory remove IMNAME
    python3 tools/schematic/template_edit.py clock set rate=2.0 startrunning=no ...
    python3 tools/schematic/template_edit.py setting set blockrouting=no logicdelay=500 blockspeed=Normal

For a one-line memory, clock or manager setting, use this instead of PanelPro, Store, make tables-pull and
split_store.py (ADR-029). Each edit is checked, written through hartlib.tables (the bytes JMRI writes), and followed by
build_tables.py and build_tables.py --check. --dry-run shows the change and writes nothing; --no-build skips the
rebuild. A memory's value is not kept: a Store drops it (hartlib.tables_normal.ENVELOPE_DROPS), so a value is set in
JMRI at run time. Items outside what the template holds (turnouts, masts, blocks, the panel) come from the device master.
Exit 0 done, 1 refused or the rebuild failed (the template is put back), 2 usage.
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hartlib" / "src"))
from hartlib import paths, tables, tables_sections  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402

MEMORIES = ("memories", "jmri.managers.configurexml.DefaultMemoryManagerXml")
SENSORS = tables_sections.INTERNAL_SENSORS
TIMEBASE = ("timebase", "jmri.jmrit.simpleclock.configurexml.SimpleTimebaseXml")
LAYOUT_BLOCKS = ("layoutblocks", "jmri.jmrit.display.layoutEditor.configurexml.LayoutBlockManagerXml")
LOGICS = ("signalmastlogics", "jmri.managers.configurexml.DefaultSignalMastLogicManagerXml")
BLOCKS = ("blocks", "jmri.configurexml.BlockManagerXml")
MEMORY_NAME = re.compile(r"IM\S+")
YES_NO = ("yes", "no")
CLOCK_FLAGS = ("run", "master", "sync", "correct", "display", "startstopped", "startrunning", "startsettime",
               "showbutton", "startsetrate")
CLOCK_RATES = ("rate", "startrate")
CLOCK_OPTIONS = ("0", "1", "2", "4")    # jmri.Timebase NONE, NIXIE_CLOCK, ANALOG_CLOCK, LCD_CLOCK
# The speed names of JMRI 5.16 xml/signals/signalSpeeds.xml (aspectSpeeds); a block's or turnout manager's default
# speed also takes a number, and a turnout manager's takes "Block" (AbstractTurnoutManager.setDefaultClosedSpeed).
# "Global" is a per-turnout speed, not a manager default.
SPEEDS = ("Cab", "Maximum", "Normal", "Sixty", "Fifty", "Limited", "Medium", "Slow", "Restricted", "RestrictedSlow",
          "Stop")
# Where a memory is read besides tables.xml (mimic_relay.py, sts_car_sync.py ...).
USER_PLACES = ("jmri/layouts/hart/scripts", "jmri/scripts")
EXIT_NO_PLUGIN = 3
CHILD_ORDER = ("systemName", "userName", "comment")


class EditError(ValueError):
    """The edit is refused; nothing is written."""


def section(root: ET.Element, key: tuple[str, str]) -> ET.Element:
    for el in tables.elements(root):
        if tb.section_key(el) == key:
            return el
    raise EditError(f"the template has no <{key[0]}> section")


def _user_names(root: ET.Element) -> set[str]:
    """Every user name in the template (memories, sensor, LogixNG parts), so a new one clashes with none."""
    return {t.text for t in root.iter("userName") if t.text}


def _child(parent: ET.Element, tag: str, where: str) -> ET.Element:
    el = parent.find(tag)
    if el is None:
        raise EditError(f"the template's {where} has no <{tag}>")
    return el


def _speed(key: str, value: str, extra: tuple[str, ...] = ()) -> str:
    if value in SPEEDS or value in extra:
        return value
    try:
        if math.isfinite(float(value)) and float(value) >= 0:
            return value
    except ValueError:
        pass
    raise EditError(f"{key} is a number or one of {', '.join(SPEEDS + extra)}, not {value!r}")


def _memory(root: ET.Element, name: str) -> ET.Element:
    held = list(tables.elements(section(root, MEMORIES)))
    for m in held:
        if tables.system_name(m) == name:
            return m
    raise EditError(f"no memory {name!r} in the template (held: {', '.join(tables.system_name(m) for m in held)})")


def _set_child(item: ET.Element, tag: str, text: str) -> None:
    """Set the child `tag`, adding it in JMRI's order (systemName, userName, comment) when it is not there."""
    old = item.find(tag)
    if old is not None:
        old.text = text
        return
    new = ET.Element(tag)
    new.text = text
    before = CHILD_ORDER[:CHILD_ORDER.index(tag)]
    item.insert(len([c for c in item if c.tag in before]), new)


def _check_text(what: str, text: str | None) -> str:
    if not text or text != text.strip() or "\n" in text:
        raise EditError(f"{what} must be non-empty text without leading or trailing space or line breaks")
    return text


def memory_add(root, name, user_name, comment) -> str:
    if not MEMORY_NAME.fullmatch(name):
        raise EditError(f"{name!r} is not a memory system name (IM then the name, no spaces)")
    box = section(root, MEMORIES)
    if any(tables.system_name(m) == name for m in tables.elements(box)):
        raise EditError(f"memory {name} already exists")
    user_name = _check_text("--user-name", user_name)
    if user_name in _user_names(root):
        raise EditError(f"user name {user_name!r} is already used")
    if comment is not None:
        _check_text("--comment", comment)
    item = ET.SubElement(box, "memory")
    _set_child(item, "systemName", name)
    _set_child(item, "userName", user_name)
    if comment is not None:
        _set_child(item, "comment", comment)
    return f"add memory {name} user name {user_name!r}" + (f" comment {comment!r}" if comment else "")


def memory_set(root, name, user_name, comment) -> str:
    item = _memory(root, name)
    if user_name is None and comment is None:
        raise EditError("memory set needs --user-name or --comment")
    parts = []
    if user_name is not None:
        _check_text("--user-name", user_name)
        if user_name != tables.user_name(item) and user_name in _user_names(root):
            raise EditError(f"user name {user_name!r} is already used")
    if comment is not None:
        _check_text("--comment", comment)
    if user_name is not None:
        parts.append(f"user name {tables.user_name(item)!r} -> {user_name!r}")
        _set_child(item, "userName", user_name)
    if comment is not None:
        parts.append(f"comment {tables.text(item, 'comment')!r} -> {comment!r}")
        _set_child(item, "comment", comment)
    return f"set memory {name}: " + "; ".join(parts)


def _used_elsewhere(names: set[str], name: str) -> str | None:
    """Where the memory is used outside the template: a script under USER_PLACES, or another tables.xml item."""
    # the system name as a word; the user name only when quoted (a plain word such as "First" is also prose)
    users = names - {name}
    pattern = re.compile("|".join([rf"(?<!\w){re.escape(name)}(?!\w)"]
                                  + [rf"[\"']{re.escape(u)}[\"']" for u in users]).encode())
    for place in USER_PLACES:
        folder = paths.REPO_ROOT / place
        for f in sorted(folder.rglob("*")) if folder.is_dir() else []:
            if f.is_file() and f.suffix in (".py", ".json", ".xml", ".csv", ".txt", ".md", ".sh"):
                data = f.read_bytes()
                if pattern.search(data):
                    return paths.rel(f)
    try:
        built = tables.read(paths.REPO_TABLES_XML)
    except (OSError, ET.ParseError):
        return None
    for sec in tables.elements(built):
        for el in sec.iter():
            if el.tag == "memory" and tables.system_name(el) == name:
                continue
            if (el.text or "").strip() in names or any(v in names for v in el.attrib.values()):
                return f"{paths.rel(paths.REPO_TABLES_XML)} (<{el.tag}> in <{sec.tag}>)"
    return None


def memory_remove(root, name, check_outside: bool = True) -> str:
    item = _memory(root, name)
    user = tables.user_name(item)
    names = {name, user} - {""}
    own = set(item.iter())
    for sec in tables.elements(root):
        for el in sec.iter():
            if el in own or not isinstance(el.tag, str):
                continue
            if (el.text or "").strip() in names or any(v in names for v in el.attrib.values()):
                raise EditError(f"memory {name} is used by <{el.tag}> in <{sec.tag}>; remove that first")
    where = _used_elsewhere(names, name) if check_outside else None
    if where:
        raise EditError(f"memory {name} is used in {where}; remove that first")
    tables.remove_child(section(root, MEMORIES), item)
    return f"remove memory {name} ({user!r})"


def clock_set(root, pairs: dict[str, str]) -> str:
    clock = section(root, TIMEBASE)
    done = []
    for key, value in pairs.items():
        if key not in clock.attrib or key == "class":
            held = [k for k in clock.attrib if k != "class"]
            raise EditError(f"the clock has no setting {key!r} (held: {', '.join(held)})")
        if key in CLOCK_FLAGS and value not in YES_NO:
            raise EditError(f"{key} is yes or no, not {value!r}")
        if key in CLOCK_RATES:     # JMRI writes a Java double: "2" is "2.0"
            try:
                number = float(value)
            except ValueError as exc:
                raise EditError(f"{key} is a number, not {value!r}") from exc
            if not math.isfinite(number) or number <= 0:
                raise EditError(f"{key} must be a number above zero, not {value!r}")
            value = repr(number)
        elif key == "startclockoption":
            if value not in CLOCK_OPTIONS:
                raise EditError(f"startclockoption is one of {', '.join(CLOCK_OPTIONS)} (none, nixie, analog, lcd)")
        done.append(f"{key} {clock.get(key)} -> {value}")
        clock.set(key, value)
    return "clock " + "; ".join(done)


def setting_set(root, pairs: dict[str, str]) -> str:
    done = []
    for key, value in pairs.items():
        if key == "blockrouting":
            el = section(root, LAYOUT_BLOCKS)
            if value not in YES_NO:
                raise EditError(f"blockrouting is yes or no, not {value!r}")
            done.append(f"blockrouting {el.get('blockrouting')} -> {value}")
            el.set("blockrouting", value)
        elif key == "logicdelay":
            el = _child(section(root, LOGICS), "logicDelay", "Signal Mast Logic section")
            if not re.fullmatch(r"[0-9]+", value):
                raise EditError(f"logicdelay is whole milliseconds, not {value!r}")
            value = str(int(value))
            done.append(f"logicDelay {el.text} -> {value}")
            el.text = value
        elif key in ("blockspeed", "closedspeed", "thrownspeed"):
            value = _speed(key, value, () if key == "blockspeed" else ("Block",))
            if key == "blockspeed":
                els = [_child(section(root, BLOCKS), "defaultspeed", "blocks section")]
            else:
                tag = f"default{key[:-5]}speed"
                els = [_child(s, tag, "turnouts section") for s in tables.elements(root) if s.tag == "turnouts"]
                if not els:
                    raise EditError("the template has no <turnouts> section")
            done.append(f"{key} {els[0].text} -> {value}")
            for el in els:
                el.text = value
        else:
            raise EditError(f"unknown setting {key!r}; one of blockrouting, logicdelay, blockspeed, closedspeed, "
                            "thrownspeed")
    return "setting " + "; ".join(done)


def listing(root, kind: str | None) -> list[str]:
    out = []
    if kind in (None, "memory"):
        for m in tables.elements(section(root, MEMORIES)):
            out.append(f"memory  {tables.system_name(m)}  {tables.user_name(m)!r}  {tables.text(m, 'comment')}")
    if kind in (None, "sensor"):
        for s in tables.elements(section(root, SENSORS)):
            if s.tag == "sensor":
                out.append(f"sensor  {tables.system_name(s)}  {tables.user_name(s)!r}  {tables.text(s, 'comment')}")
    if kind in (None, "clock"):
        out.append("clock   " + " ".join(f"{k}={v}" for k, v in section(root, TIMEBASE).attrib.items() if k != "class"))
    if kind in (None, "setting"):
        for sec in tables.elements(root):
            if sec.tag == "turnouts":
                out.append(f"setting {sec.get('class').rsplit('.', 1)[-1]}: "
                           f"closedspeed={sec.findtext('defaultclosedspeed')} "
                           f"thrownspeed={sec.findtext('defaultthrownspeed')}")
        out.append(f"setting blockrouting={section(root, LAYOUT_BLOCKS).get('blockrouting')}")
        out.append(f"setting logicdelay={section(root, LOGICS).findtext('logicDelay')}")
        out.append(f"setting blockspeed={section(root, BLOCKS).findtext('defaultspeed')}")
    if kind in (None, "logixng"):
        for el in root.iter("LogixNG"):
            if el.find("systemName") is not None:
                out.append(f"logixng {tables.system_name(el)}  {tables.user_name(el)!r}  enabled={el.get('enabled')}")
        for el in root.iter("ConditionalNG"):
            out.append(f"conditionalng {tables.system_name(el)}  {tables.user_name(el)!r}")
    return out


def pairs_of(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        key, eq, value = item.partition("=")
        if not eq or not key or key in out:
            raise EditError(f"{item!r}: give each setting once as name=value")
        out[key] = value
    return out


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--template", type=Path, default=tb.TEMPLATE, help=argparse.SUPPRESS)
    ap.add_argument("--dry-run", action="store_true", help="show the change and write nothing")
    ap.add_argument("--no-build", action="store_true", help="write the template but do not rebuild tables.xml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("kind", nargs="?", choices=["memory", "sensor", "clock", "setting", "logixng"])
    mem = sub.add_parser("memory").add_subparsers(dest="action", required=True)
    for action in ("add", "set", "remove"):
        p = mem.add_parser(action)
        p.add_argument("name")
        if action != "remove":
            p.add_argument("--user-name")
            p.add_argument("--comment")
    for cmd in ("clock", "setting"):
        p = sub.add_parser(cmd).add_subparsers(dest="action", required=True).add_parser("set")
        p.add_argument("pairs", nargs="+", metavar="name=value")
    return ap


def edit(args) -> str | None:
    """Apply `args` to the template; the one-line summary, or None for list. EditError or TablesBuildError refuse."""
    doc = tb.read_template(args.template)
    root = doc.root
    if args.cmd == "list":
        print("\n".join(listing(root, args.kind)))
        return None
    if args.cmd == "memory":
        if args.action == "add":
            summary = memory_add(root, args.name, args.user_name, args.comment)
        elif args.action == "set":
            summary = memory_set(root, args.name, args.user_name, args.comment)
        else:
            summary = memory_remove(root, args.name)
    elif args.cmd == "clock":
        summary = clock_set(root, pairs_of(args.pairs))
    else:
        summary = setting_set(root, pairs_of(args.pairs))
    tables_sections.jmri_sort(root)
    ET.indent(root, space="  ")
    if args.dry_run:
        return "dry run, nothing written: " + summary
    if not doc.save(args.template):
        return "no change: " + summary
    return summary


def rebuild() -> int:
    here = Path(__file__).resolve().parent
    for extra in ([], ["--check"]):
        code = subprocess.run([sys.executable, str(here / "build_tables.py"), *extra]).returncode
        if code:
            return code
    return 0


def rebuild_or_restore(template: Path, before: bytes) -> int:
    """Rebuild tables.xml from the edited template; on failure put back the template (`before`) and tables.xml."""
    built = paths.REPO_TABLES_XML
    built_before = built.read_bytes() if built.exists() else None
    code = rebuild()
    if not code:
        return 0
    template.write_bytes(before)
    if built_before is not None:
        built.write_bytes(built_before)
    why = ("the schematic-maps plugin is missing or off its pin (git submodule update --init "
           "external/model-railroad-skills, or rerun with --no-build)" if code == EXIT_NO_PLUGIN
           else "the rebuild failed")
    print(f"template_edit.py: {why}; the template and tables.xml are put back", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        before = args.template.read_bytes()
        summary = edit(args)
    except (EditError, tb.TablesBuildError, OSError) as exc:
        print(f"template_edit.py: {exc}", file=sys.stderr)
        return 1
    if summary is None:
        return 0
    print(f"{args.template.name}: {summary}")
    if (args.dry_run or args.no_build or args.template.resolve() != tb.TEMPLATE.resolve()
            or summary.startswith("no change")):
        return 0
    return rebuild_or_restore(args.template, before)


if __name__ == "__main__":
    sys.exit(main())
