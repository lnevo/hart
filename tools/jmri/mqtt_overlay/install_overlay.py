#!/usr/bin/env python3
"""Install or remove the MQTT race overlay for every JMRI app this user starts (ADR-034).

Copies hart-mqtt-race-fix.jar into the JMRI settings folder (the one holding jmri.conf:
~/Library/Preferences/JMRI on macOS, ~/.jmri on Linux, %USERPROFILE%\\JMRI on Windows) and puts
``--cp:p=<that jar>`` in jmri.conf's default_options, so JMRI's launcher loads the patched
MqttAdapter ahead of jmri.jar. Every other option in jmri.conf is kept as it was.

It only installs over the JMRI build the jar was compiled from (HART-JMRI-Base in its manifest).
On any other build it takes the overlay out again and says so, so a JMRI upgrade runs stock.

Usage: install_overlay.py --jar JAR --settings-dir DIR --jmri-home DIR [--remove]
Standard library only: it runs on the Mac, the Pi and Windows.
"""
from __future__ import annotations

import argparse
import filecmp
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

JAR_NAME = "hart-mqtt-race-fix.jar"
_OPTIONS_RE = re.compile(r'^(\s*default_options\s*=\s*)"(.*)"\s*$')
_NEW_CONF = (
    "# JMRI launcher options for this user. The --cp:p entry is HART's MQTT race overlay,\n"
    "# written by tools/jmri/mqtt_overlay/install_overlay.py; other options here are kept.\n"
)


def jmri_build(jmri_jar: Path) -> str:
    """'5.16.0 909e15189e' from jmri.jar's jmri/Version.properties."""
    with zipfile.ZipFile(jmri_jar) as z:
        text = z.read("jmri/Version.properties").decode("utf-8", "replace")
    props = dict(
        line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#")
    )
    return "{}.{}.{} {}".format(
        props.get("release.major", "?"), props.get("release.minor", "?"),
        props.get("release.build", "?"), props.get("release.revision_id", "?"),
    ).strip()


def overlay_base(jar: Path) -> str:
    with zipfile.ZipFile(jar) as z:
        manifest = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    for line in manifest.splitlines():
        if line.startswith("HART-JMRI-Base:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit(f"{jar}: no HART-JMRI-Base in its manifest")


def _is_ours(token: str) -> bool:
    return token.startswith("--cp:p=") and token.rstrip("\"'").replace("\\", "/").endswith("/" + JAR_NAME)


def edit_conf(text: str | None, jar_path: str | None) -> str:
    """Return jmri.conf text with our --cp:p set to jar_path (None takes it out).

    The last uncommented default_options line is the one the launcher's ``source`` keeps, so
    that is the one edited; an earlier one is left alone. With no such line, one is appended.
    """
    lines = [] if text is None else text.splitlines(keepends=True)
    idx = None
    for i, line in enumerate(lines):
        if _OPTIONS_RE.match(line.rstrip("\r\n")):
            idx = i
    if idx is None:
        if jar_path is None:
            return text or ""
        if text is None:
            lines = [_NEW_CONF]
        elif lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f'default_options="--cp:p={jar_path}"\n')
        return "".join(lines)
    raw = lines[idx]
    eol = raw[len(raw.rstrip("\r\n")):] or "\n"
    m = _OPTIONS_RE.match(raw.rstrip("\r\n"))
    assert m
    tokens = [t for t in m.group(2).split() if not _is_ours(t)]
    if jar_path is not None:
        tokens.insert(0, f"--cp:p={jar_path}")
    lines[idx] = f'{m.group(1)}"{" ".join(tokens)}"{eol}'
    return "".join(lines)


def _write_conf(conf: Path, new: str) -> bool:
    old = conf.read_text(encoding="utf-8") if conf.is_file() else None
    if new == (old or ""):
        return False
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(new, encoding="utf-8", newline="")
    return True


def remove(settings: Path) -> None:
    conf = settings / "jmri.conf"
    if conf.is_file() and _write_conf(conf, edit_conf(conf.read_text(encoding="utf-8"), None)):
        print(f"MQTT overlay: taken out of {conf}")
    dest = settings / JAR_NAME
    if dest.is_file():
        dest.unlink()
        print(f"MQTT overlay: removed {dest}")


def install(jar: Path, settings: Path, jmri_home: Path) -> int:
    want = overlay_base(jar)
    have = jmri_build(jmri_home / "jmri.jar")
    if have != want:
        print(f"WARNING MQTT overlay: {jmri_home} is JMRI {have}, the overlay is for {want}; "
              "JMRI runs stock (rebuild the overlay for this JMRI or drop it)")
        remove(settings)
        return 0
    dest = settings / JAR_NAME
    if " " in str(dest):
        # The launcher splits default_options on spaces.
        print(f"ERROR MQTT overlay: {dest} has a space; JMRI's launcher cannot take it", file=sys.stderr)
        return 1
    settings.mkdir(parents=True, exist_ok=True)
    if not (dest.is_file() and filecmp.cmp(jar, dest, shallow=False)):
        # A running JMRI holds the jar open: write beside it and swap, never truncate it in place.
        part = dest.with_name(dest.name + ".part")
        shutil.copyfile(jar, part)
        try:
            os.replace(part, dest)
        except OSError as e:  # Windows refuses while a JVM has it open
            part.unlink(missing_ok=True)
            print(f"WARNING MQTT overlay: could not replace {dest} ({e}); deploy again with JMRI closed")
            return 0
        print(f"MQTT overlay: {dest}")
    conf = settings / "jmri.conf"
    old = conf.read_text(encoding="utf-8") if conf.is_file() else None
    if _write_conf(conf, edit_conf(old, str(dest))):
        print(f"MQTT overlay: {conf} loads it (--cp:p)")
    else:
        print(f"MQTT overlay: {conf} already loads it")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jar", type=Path, help="hart-mqtt-race-fix.jar to install")
    ap.add_argument("--settings-dir", type=Path, required=True, help="the folder holding jmri.conf")
    ap.add_argument("--jmri-home", type=Path, help="the JMRI install (holds jmri.jar)")
    ap.add_argument("--remove", action="store_true", help="take the overlay out")
    a = ap.parse_args(argv)
    if a.remove:
        remove(a.settings_dir)
        return 0
    if a.jar is None or a.jmri_home is None:
        ap.error("--jar and --jmri-home are needed to install")
    return install(a.jar, a.settings_dir, a.jmri_home)


if __name__ == "__main__":
    sys.exit(main())
