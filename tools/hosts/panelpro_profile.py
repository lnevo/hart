#!/usr/bin/env python3
"""The JMRI profile steps of a PanelPro wrapper run on this Mac (tools/hosts/panelpro_session.sh).

  check-profile   stop unless the profile.xml to patch is the profile JMRI will start, and print its
                  user files folder. A profile other than the live one must have its own user files.
  quiet-startup   switch off every Start Up item that runs code, except the allowlist below
  backup / seal   copy profile.xml to <profile.xml>.hart-run.bak; after patching, record the patched
                  file's hash in <profile.xml>.hart-run.sha256
  restore         put the backup back and remove it and the hash
  jmri-running    exit 0 while PanelPro, DecoderPro, DispatcherPro or CATS runs (hartlib's check), 1 while none
                  does, 2 (printing "unknown") when the check cannot say

After a wrapper was killed with SIGKILL, quit the PanelPro it left, then

    python3 tools/hosts/panelpro_profile.py restore --profile <profile.xml>

restore refuses while JMRI or CATS runs, and when profile.xml is neither the patched file the
run sealed nor the backup (something else changed it since). --force restores anyway and says
what it overwrote.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import jmri_profile, tables  # noqa: E402

LIVE_PROFILE_ID = "My_JMRI_Railroad.3ef75bfd"
BACKUP_SUFFIX = ".hart-run.bak"
SEAL_SUFFIX = ".hart-run.sha256"
USER_FILES_KEY = "jmri-implementation.user-files"

# Start Up items that stay on during a wrapper run. Everything else that runs code is switched
# off: scripts (they publish over MQTT, take STS moves, run dropped-in commands), actions (the web,
# WiThrottle and simple servers let other devices drive the layout) and route triggers.
ALLOWED_SCRIPTS = ("hide_cats_desk_windows.py",)   # hides CATS desk windows; touches no beans
ALLOWED_ACTIONS = ("apps.SystemConsoleAction", "jmri.jmrit.powerpanel.PowerPanelAction",
                   "jmri.jmrit.analogclock.AnalogClockAction")
# Items that run nothing at start: file loads (tables, panels), buttons, pauses.
INERT_CLASSES = ("PerformFileModelXml", "ScriptButtonModelXml", "StartupPauseModelXml")

SAFE_PATH = re.compile(r"[A-Za-z0-9._/@+=,:-]+")
_TAG = re.compile(r"<perform\b[^>]*>")


def live_profile_dir() -> Path:
    return Path.home() / "Library/Preferences/JMRI/My_JMRI_Railroad.jmri"


def live_user_files() -> Path:
    return Path.home() / "JMRI_UserFiles"


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m.group(1) if m else None


def _allowed(tag: str) -> bool:
    cls = _attr(tag, "class") or ""
    name = _attr(tag, "name") or ""
    if cls.rsplit(".", 1)[-1] in INERT_CLASSES:
        return True
    if cls.endswith("PerformScriptModelXml"):
        return _basename(name) in ALLOWED_SCRIPTS
    if cls.endswith("PerformActionModelXml"):
        return name in ALLOWED_ACTIONS
    return False


def _basename(name: str) -> str:
    return re.split(r"[/:\\]", name)[-1]


def quiet_startup(profile: Path, run_script: str) -> list[str]:
    """Switch off every enabled Start Up item outside the allowlist, then add run_script (enabled).

    An earlier entry for run_script is replaced, so the run's script always starts. Fails if any
    item that runs code is still enabled afterwards, other than the allowlist and run_script.
    """
    text = profile.read_text(encoding="utf-8")
    run_base = _basename(run_script)
    notes = []
    out, last = [], 0
    for m in _TAG.finditer(text):
        tag = m.group(0)
        if 'enabled="yes"' in tag and not _allowed(tag):
            out.append(text[last:m.start()] + tag.replace('enabled="yes"', 'enabled="no"'))
            last = m.end()
            notes.append(f"off: {_attr(tag, 'name')}")
    text = "".join(out) + text[last:]
    text, removed = re.subn(r'\n?[ \t]*<perform\b[^>]*\bname="(?:[^"]*[/:])?' + re.escape(run_base) + r'"[^>]*/>',
                            "", text)
    loads = [t for t in _TAG.findall(text) if "PerformFileModelXml" in t and (_attr(t, "name") or "").endswith("tables.xml")]
    if len(loads) != 1:
        raise SystemExit(f"{profile}: expected one tables load in Start Up, found {len(loads)}")
    profile.write_text(text, encoding="utf-8")
    jmri_profile.insert_after(profile, run_script, _attr(loads[0], "name") or "")   # a load named tables.xml
    text = profile.read_text(encoding="utf-8")
    still = [t for t in _TAG.findall(text)
             if 'enabled="no"' not in t and not _allowed(t) and _basename(_attr(t, "name") or "") != run_base]
    if still:
        raise SystemExit(f"{profile}: a Start Up item could not be switched off: {still[0]}")
    runs = [t for t in _TAG.findall(text) if _basename(_attr(t, "name") or "") == run_base and 'enabled="yes"' in t]
    if len(runs) != 1:
        raise SystemExit(f"{profile}: {run_base} is not in Start Up exactly once, enabled")
    notes.append(f"run: {run_script}" + (" (replaced an earlier entry)" if removed else ""))
    return notes


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup_path(profile: Path) -> Path:
    return profile.with_name(profile.name + BACKUP_SUFFIX)


def seal_path(profile: Path) -> Path:
    return profile.with_name(profile.name + SEAL_SUFFIX)


def recovery_command(profile: Path) -> str:
    return f"python3 {Path(__file__).resolve()} restore --profile {profile}"


def backup_profile(profile: Path) -> Path:
    """Copy profile to its fixed backup path; refuse if a backup from an unfinished run is there."""
    bak = backup_path(profile)
    if bak.exists() or seal_path(profile).exists():
        raise SystemExit(
            f"{bak} exists: an earlier wrapper run did not restore the profile (killed?).\n"
            f"  The profile may still hold that run's Start Up changes. Quit the PanelPro it left, then\n"
            f"  {recovery_command(profile)}"
        )
    if not profile.is_file():
        raise SystemExit(f"profile.xml not found: {profile}")
    shutil.copy2(profile, bak)
    return bak


def seal_profile(profile: Path) -> Path:
    if not backup_path(profile).is_file():
        raise SystemExit(f"no backup for {profile}; seal comes after backup and patching")
    seal = seal_path(profile)
    seal.write_text(_sha(profile) + "\n", encoding="utf-8")
    return seal


def restore_profile(profile: Path, force: bool = False) -> str:
    """Put the backup back over profile and remove the backup and the seal."""
    bak, seal = backup_path(profile), seal_path(profile)
    if not bak.is_file():
        raise SystemExit(f"no backup to restore: {bak}")
    note = ""
    sealed = seal.read_text(encoding="utf-8").strip() if seal.is_file() else None
    current = _sha(profile) if profile.is_file() else None
    unexpected = current not in (sealed, _sha(bak))
    if not force:
        try:
            running = tables.jmri_running()
        except tables.JmriCheckError as exc:
            raise SystemExit(f"{exc}; not restored (restore --force skips this check)") from exc
        if running:
            raise SystemExit("PanelPro, DecoderPro or CATS is running; quit it, then restore")
        if sealed is None:
            raise SystemExit(f"{seal} is missing (the run stopped while patching): compare {profile} "
                             f"with {bak} by hand, then restore with --force")
        if unexpected:
            raise SystemExit(f"{profile} changed since the run patched it (not the sealed file); "
                             f"compare it with {bak}, then restore with --force")
    elif unexpected:
        note = f" (overwrote changes made to {profile} after the run patched it)"
    tmp = profile.with_name(profile.name + ".hart-run.tmp")
    shutil.copy2(bak, tmp)
    os.replace(tmp, profile)
    bak.unlink()
    seal.unlink(missing_ok=True)
    return f"restored {profile} from {bak}{note}"


# ------------------------------------------------------------------ .properties


def _logical_lines(text: str):
    natural = re.split(r"\r\n|\r|\n", text)
    i = 0
    while i < len(natural):
        line = natural[i].lstrip(" \t\f")
        i += 1
        if not line or line[0] in "#!":
            continue
        while (len(line) - len(line.rstrip("\\"))) % 2 == 1:
            line = line[:-1]
            if i >= len(natural):
                break
            line += natural[i].lstrip(" \t\f")
            i += 1
        yield line


_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}


def _unescape(chars: str, where: Path) -> str:
    out, i = [], 0
    while i < len(chars):
        c = chars[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= len(chars):
            break
        c = chars[i]
        if c == "u":
            code = chars[i + 1:i + 5]
            if not re.fullmatch(r"[0-9a-fA-F]{4}", code):
                raise SystemExit(f"{where}: malformed \\u escape {chars[i - 1:i + 5]!r}")
            out.append(chr(int(code, 16)))
            i += 5
            continue
        out.append(_ESCAPES.get(c, c))   # Java drops the backslash before any other character
        i += 1
    return "".join(out)


def read_properties(path: Path) -> dict[str, str]:
    """A Java .properties file, as java.util.Properties.load reads it."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in _logical_lines(path.read_text(encoding="utf-8", errors="strict")):
        i = 0
        while i < len(line) and line[i] not in "=: \t\f":
            i += 2 if line[i] == "\\" else 1
        key = line[:i]
        while i < len(line) and line[i] in " \t\f":
            i += 1
        if i < len(line) and line[i] in "=:":
            i += 1
            while i < len(line) and line[i] in " \t\f":
                i += 1
        out[_unescape(key, path)] = _unescape(line[i:], path)
    return out


# ------------------------------------------------------------------ profile checks


def _portable_dir(value: str, profile_dir: Path) -> Path | None:
    """JMRI portable path (home:, profile:, absolute) as a folder; None for other forms."""
    if value.startswith("home:"):
        return Path.home() / value[len("home:"):]
    if value.startswith("profile:"):
        return profile_dir / value[len("profile:"):]
    if value.startswith("/"):
        return Path(value)
    return None


def profile_user_files(profile_dir: Path) -> Path:
    """The user files folder JMRI uses for this profile, as FileLocationsPreferences decides it.

    The shared value wins when it is profile:...; otherwise a node value overrides it.
    """
    shared_file = profile_dir / "profile" / "profile.properties"
    shared = read_properties(shared_file).get(USER_FILES_KEY, "profile:")
    value = shared
    if not shared.startswith("profile:"):
        nodes = {}
        for p in sorted((profile_dir / "profile").glob("*/profile.properties")):
            v = read_properties(p).get(USER_FILES_KEY)
            if v:
                nodes[p] = v
        if len(set(nodes.values())) > 1:
            raise SystemExit(f"{profile_dir}: its node folders name different user files folders "
                             f"({sorted(set(nodes.values()))}); make them agree")
        if nodes:
            value = next(iter(nodes.values()))
    found = _portable_dir(value, profile_dir)
    if found is None:
        raise SystemExit(f"{profile_dir}: user files {value!r} is a form this cannot resolve "
                         "(use home:, profile: or an absolute folder)")
    return found


def _safe(what: str, value: str) -> None:
    if not SAFE_PATH.fullmatch(value):
        raise SystemExit(f"{what} {value!r} holds a space or a shell character; StartJMRI splits it. "
                         "Use a path of letters, digits and . _ - / only")


def check_profile(profile: Path, launch: str, user_files: str | None) -> Path:
    """Check that JMRI started with -p launch reads profile; return the user files folder."""
    _safe("JMRI_PROFILE_XML", str(profile))
    _safe("JMRI_PROFILE", launch)
    if user_files:
        _safe("JMRI_USER_FILES", user_files)
    if profile.name != "profile.xml" or profile.parent.name != "profile":
        raise SystemExit(f"not a JMRI profile.xml (want <name>.jmri/profile/profile.xml): {profile}")
    profile_dir = profile.parent.parent
    live = profile_dir.resolve() == live_profile_dir().resolve()
    pid = read_properties(profile.parent / "profile.properties").get("profile.id", "")
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
    elif not live and launch == LIVE_PROFILE_ID:
        raise SystemExit(f"{profile_dir} carries the live profile's id; JMRI could start the live profile. "
                         "Leave JMRI_PROFILE unset so the run starts it by folder")
    found = profile_user_files(profile_dir)
    if not live and found.resolve() == live_user_files().resolve():
        raise SystemExit(
            f"{profile_dir} uses the live user files folder {found}. For a rehearsal set "
            f"{USER_FILES_KEY}=<scratch folder>/ in its profile/profile.properties (and any node "
            "folder's), then run again"
        )
    if user_files and Path(user_files).resolve() != found.resolve():
        raise SystemExit(f"JMRI_USER_FILES {user_files} is not the user files folder of {profile_dir} ({found})")
    return found


JMRI_UNKNOWN = 2      # jmri-running's exit when the check cannot say (pgrep missing or failing)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("check-profile", "quiet-startup", "backup", "seal", "restore",
                                       "jmri-running"))
    ap.add_argument("--profile", type=Path)
    ap.add_argument("--launch", help="check-profile: the JMRI -p value (profile id or folder)")
    ap.add_argument("--user-files", help="check-profile: the user files folder the run expects")
    ap.add_argument("--run", help="quiet-startup: the wrapper's own script, added enabled")
    ap.add_argument("--force", action="store_true", help="restore: skip the running and changed checks")
    args = ap.parse_args()
    if args.action == "jmri-running":
        state = tables.jmri_state()
        if state is tables.JmriState.UNKNOWN:
            print("unknown", file=sys.stderr)
        sys.exit({tables.JmriState.RUNNING: 0, tables.JmriState.STOPPED: 1}.get(state, JMRI_UNKNOWN))
    if args.profile is None:
        ap.error(f"{args.action} requires --profile")
    if args.action == "check-profile":
        if not args.launch:
            ap.error("check-profile requires --launch")
        print(check_profile(args.profile, args.launch, args.user_files))
    elif args.action == "quiet-startup":
        if not args.run:
            ap.error("quiet-startup requires --run")
        try:
            print("\n".join(quiet_startup(args.profile, args.run)))
        except jmri_profile.StartupPatchError as exc:     # one line, as the profile checks above
            sys.exit(f"{args.profile}: {exc}")
    elif args.action == "backup":
        print(backup_profile(args.profile))
    elif args.action == "seal":
        print(seal_profile(args.profile))
    else:
        print(restore_profile(args.profile, args.force))


if __name__ == "__main__":
    main()
