#!/usr/bin/env python3
"""Insert or remove a JMRI profile Start Up script perform tag.

Preserves the attribute order of the neighbouring PerformScript tag.

The PanelPro wrappers (tools/hosts/panelpro_session.sh) also use it to back up and
restore the profile around a run, to switch off the Start Up scripts that publish
or act on the layout, and to check that the profile they patch is the one JMRI
starts. A wrapper killed with SIGKILL cannot restore the profile; recover with

    python3 cats/scripts/patch_jmri_startup.py restore --profile <profile.xml>

which copies back <profile.xml>.hart-run.bak (BACKUP_SUFFIX) and removes it.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path

# Start Up scripts a PanelPro wrapper run must not start: they publish over MQTT
# (panel_status, signal_coordinator, mimic_relay), take STS car moves into
# Operations Pro (sts_car_sync), or run whatever is dropped in /tmp (jmri_cmd_watcher).
PUBLISHING_STARTUP_SCRIPTS = (
    "panel_status.py",
    "signal_coordinator.py",
    "sts_car_sync.py",
    "jmri_cmd_watcher.py",
    "mimic_relay.py",
)
BACKUP_SUFFIX = ".hart-run.bak"


def _perform_for(sample: str, script_path: str) -> str:
    if "xmlns=" in sample:
        return (
            '        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" '
            f'enabled="yes" name="{script_path}" type="ScriptFile"/>'
        )
    return (
        f'        <perform name="{script_path}" type="ScriptFile" enabled="yes" '
        'class="jmri.util.startup.configurexml.PerformScriptModelXml"/>'
    )


def _script_basename(path: str) -> str:
    return Path(path).name


def insert_after(profile: Path, script_path: str, after: str) -> str:
    txt = profile.read_text(encoding="utf-8")
    needle = _script_basename(script_path)
    if needle in txt:
        return "already"
    idx = txt.find(after)
    if idx < 0:
        raise SystemExit(f"{profile}: no Start Up entry containing {after!r}")
    end = txt.find("/>", idx)
    if end < 0:
        raise SystemExit(f"{profile}: malformed perform tag at {after!r}")
    end += 2
    sample = txt[txt.rfind("<perform", 0, idx) : end]
    insert = "\n" + _perform_for(sample, script_path)
    profile.write_text(txt[:end] + insert + txt[end:], encoding="utf-8")
    return "inserted"


def remove_script(profile: Path, script_path: str) -> str:
    txt = profile.read_text(encoding="utf-8")
    needle = _script_basename(script_path)
    if needle not in txt:
        return "absent"
    new, n = re.subn(
        rf"\n?[ \t]*<perform\b[^>]*{re.escape(needle)}[^>]*/>",
        "",
        txt,
        count=1,
    )
    if n != 1:
        raise SystemExit(f"{profile}: could not remove {needle}")
    profile.write_text(new, encoding="utf-8")
    return "removed"


def retarget_to_preference_jython(profile: Path, scripts: list[str]) -> list[str]:
    """Rewrite PerformScript name= to preference:jython/<basename>.

    Leaves ScriptButton / XmlFile / Action tags alone. Idempotent when the
    name is already preference:jython/.
    Also renames known retired basenames (e.g. sync_yard_ladder_buttons →
    panel_status) before retargeting.
    """
    txt = profile.read_text(encoding="utf-8")
    orig = txt
    notes: list[str] = []
    wanted = {_script_basename(s) for s in scripts}

    # Retired → current startup script basenames (must run after package rename).
    renames = {
        "sync_yard_ladder_buttons.py": "panel_status.py",
        "sync_turnout_buttons.py": "panel_status.py",
        "sync_layout_button.py": "panel_status.py",
        "mqtt_signalhead_publisher.py": "signal_coordinator.py",
    }
    for old, new in renames.items():
        if old in txt and new in wanted:
            txt2, n = re.subn(
                rf'(name="[^"]*){re.escape(old)}(")',
                rf"\1{new}\2",
                txt,
            )
            if n:
                notes.append(f"{old} -> {new} ({n} Start Up entr{'y' if n == 1 else 'ies'})")
                txt = txt2

    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "PerformScriptModelXml" not in tag:
            return tag
        name_m = re.search(r'\bname="([^"]*)"', tag)
        if name_m is None:
            return tag
        old = name_m.group(1)
        base = _script_basename(old)
        if base not in wanted:
            return tag
        target = f"preference:jython/{base}"
        if old == target:
            return tag
        notes.append(f"{old} -> {target}")
        return tag[: name_m.start()] + f'name="{target}"' + tag[name_m.end() :]

    txt = re.sub(r"<perform\b[^>]*/>", repl, txt)
    if txt != orig:
        profile.write_text(txt, encoding="utf-8")
    return notes


def load_tables_from(profile: Path, path: str) -> str:
    """Point the Start Up tables load at path (for example preference:tables.xml)."""
    text = profile.read_text(encoding="utf-8")
    new, count = re.subn(
        r'(<perform\b[^>]*PerformFileModelXml[^>]*\bname=")[^"]*tables\.xml(")',
        lambda m: m.group(1) + path + m.group(2),
        text,
    )
    if count != 1:
        raise SystemExit(f"expected one tables load in {profile}, found {count}")
    if new == text:
        return "already"
    profile.write_text(new, encoding="utf-8")
    return "changed"


def _perform_tags(text: str, basename: str) -> list[re.Match[str]]:
    """Start tags of every <perform> whose name= ends in basename."""
    pat = re.compile(r'<perform\b(?=[^>]*\bname="(?:[^"]*[/:])?' + re.escape(basename) + r'")[^>]*>')
    return list(pat.finditer(text))


def disable_publishing(profile: Path, scripts: tuple[str, ...] = PUBLISHING_STARTUP_SCRIPTS) -> list[str]:
    """Set enabled="no" on every Start Up entry for scripts; returns one note per script.

    Fails if an entry is still enabled afterwards (an attribute form this does not know).
    """
    text = profile.read_text(encoding="utf-8")
    notes = []
    for name in scripts:
        tags = _perform_tags(text, name)
        if not tags:
            notes.append(f"not in Start Up (ok): {name}")
            continue
        changed = 0
        for m in reversed(tags):
            tag = m.group(0)
            new = tag.replace('enabled="yes"', 'enabled="no"')
            if new != tag:
                changed += 1
                text = text[: m.start()] + new + text[m.end():]
        notes.append(f"disabled {changed} of {len(tags)}: {name}")
    for name in scripts:
        still = [m.group(0) for m in _perform_tags(text, name) if 'enabled="no"' not in m.group(0)]
        if still:
            raise SystemExit(f"{profile}: Start Up entry for {name} is still enabled: {still[0]}")
    profile.write_text(text, encoding="utf-8")
    return notes


def backup_path(profile: Path) -> Path:
    return profile.with_name(profile.name + BACKUP_SUFFIX)


def backup_profile(profile: Path) -> Path:
    """Copy profile to its fixed backup path; refuse if a backup from an unfinished run is there."""
    bak = backup_path(profile)
    if bak.exists():
        raise SystemExit(
            f"{bak} exists: an earlier wrapper run did not restore the profile (killed?).\n"
            f"  The profile may still hold that run's Start Up changes. Restore it with\n"
            f"  python3 {Path(__file__).resolve()} restore --profile {profile}\n"
            f"  or delete {bak} if the profile is known to be right."
        )
    if not profile.is_file():
        raise SystemExit(f"profile.xml not found: {profile}")
    shutil.copy2(profile, bak)
    return bak


def restore_profile(profile: Path) -> str:
    """Put the backup back over profile and remove the backup."""
    bak = backup_path(profile)
    if not bak.is_file():
        raise SystemExit(f"no backup to restore: {bak}")
    tmp = profile.with_name(profile.name + ".hart-run.tmp")
    shutil.copy2(bak, tmp)
    os.replace(tmp, profile)
    bak.unlink()
    return f"restored {profile} from {bak}"


def _read_properties(path: Path) -> dict[str, str]:
    """Java .properties, enough for JMRI profile files (\\-escapes, = or : separators)."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.lstrip()
        if not line or line[0] in "#!":
            continue
        key, value, i, esc = [], None, 0, False
        buf = key
        while i < len(line):
            c = line[i]
            if esc:
                buf.append(c)
                esc = False
            elif c == "\\":
                esc = True
            elif value is None and c in "=:":
                value = []
                buf = value
            else:
                buf.append(c)
            i += 1
        out["".join(key).strip()] = "".join(value or []).strip()
    return out


def _portable_dir(value: str, profile_dir: Path) -> Path | None:
    """JMRI portable path (home:, profile:, absolute) as a folder; None for other forms."""
    if value.startswith("home:"):
        return Path.home() / value[len("home:"):]
    if value.startswith("profile:"):
        return profile_dir / value[len("profile:"):]
    if value.startswith("/"):
        return Path(value)
    return None


def profile_user_files(profile_dir: Path) -> Path | None:
    """The user files folder JMRI would use for this profile, as FileLocationsPreferences does.

    The shared value wins when it is profile:...; otherwise a node value overrides it. None
    when it cannot be told (several nodes that disagree, or a form this does not resolve).
    """
    key = "jmri-implementation.user-files"
    shared = _read_properties(profile_dir / "profile" / "profile.properties").get(key, "profile:")
    value = shared
    if not shared.startswith("profile:"):
        nodes = {
            v for v in (
                _read_properties(p).get(key)
                for p in (profile_dir / "profile").glob("*/profile.properties")
            ) if v
        }
        if len(nodes) > 1:
            return None
        if nodes:
            value = nodes.pop()
    return _portable_dir(value, profile_dir)


def check_profile(profile: Path, launch: str, user_files: str | None) -> Path:
    """Check that JMRI started with -p launch reads profile; return the user files folder."""
    if profile.name != "profile.xml" or profile.parent.name != "profile":
        raise SystemExit(f"not a JMRI profile.xml (want <name>.jmri/profile/profile.xml): {profile}")
    profile_dir = profile.parent.parent
    props = _read_properties(profile.parent / "profile.properties")
    pid = props.get("profile.id", "")
    if launch.startswith("/"):
        target = Path(launch)
        if not target.is_dir() and Path(launch + ".jmri").is_dir():
            target = Path(launch + ".jmri")
        if target.resolve() != profile_dir.resolve():
            raise SystemExit(
                f"JMRI_PROFILE {launch} is not the profile of JMRI_PROFILE_XML {profile}: "
                "the run would patch one profile and start another"
            )
    elif not pid:
        raise SystemExit(f"{profile.parent / 'profile.properties'} has no profile.id to check JMRI_PROFILE {launch} against")
    elif pid != launch:
        raise SystemExit(
            f"JMRI_PROFILE {launch} is not the profile of JMRI_PROFILE_XML {profile} (its id is {pid}): "
            "the run would patch one profile and start another"
        )
    found = profile_user_files(profile_dir)
    if user_files:
        given = Path(user_files)
        if found is not None and given.resolve() != found.resolve():
            raise SystemExit(f"JMRI_USER_FILES {given} is not the user files folder of {profile_dir} ({found})")
        return given
    if found is None:
        raise SystemExit(f"cannot tell the user files folder of {profile_dir}; set JMRI_USER_FILES")
    return found


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("insert", "remove", "retarget-jython", "load-tables",
                                       "disable-publishing", "backup", "restore", "check-profile"))
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument("--launch", help="check-profile: the JMRI -p value (profile id or folder)")
    ap.add_argument("--user-files", help="check-profile: the user files folder the run expects")
    ap.add_argument(
        "--script",
        action="append",
        default=[],
        help="Script path or basename (repeatable for retarget-jython)",
    )
    ap.add_argument("--after", help="Existing perform filename to insert after (insert only)")
    ap.add_argument("--tables", help="Tables path for load-tables")
    args = ap.parse_args()
    if args.action == "disable-publishing":
        print("\n".join(disable_publishing(args.profile)))
        return
    if args.action == "backup":
        print(backup_profile(args.profile))
        return
    if args.action == "restore":
        print(restore_profile(args.profile))
        return
    if args.action == "check-profile":
        if not args.launch:
            raise SystemExit("check-profile requires --launch")
        print(check_profile(args.profile, args.launch, args.user_files))
        return
    if args.action == "load-tables":
        if not args.tables:
            raise SystemExit("load-tables requires --tables")
        print(load_tables_from(args.profile, args.tables))
        return
    if not args.script:
        raise SystemExit("--script is required")
    if args.action == "insert":
        if not args.after:
            raise SystemExit("insert requires --after")
        print(insert_after(args.profile, args.script[0], args.after))
    elif args.action == "remove":
        print(remove_script(args.profile, args.script[0]))
    else:
        notes = retarget_to_preference_jython(args.profile, args.script)
        print("\n".join(notes) if notes else "already")


if __name__ == "__main__":
    main()
