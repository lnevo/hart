#!/usr/bin/env bash
# Write a tar stream of the files in a roster stage folder to stdout, with names
# RELATIVE to that folder ("./2738.xml"). Skips subfolders and macOS AppleDouble
# (._*) files. sync_roster_from_pi.sh pipes this to the Windows host.
#
# The names must be relative: a stream with absolute paths ("Users/.../2738.xml")
# unpacks into nested folders on the other side, the installer then finds nothing to
# copy, and the sync reports success while changing nothing (found 2026-11-08).
#
# Usage: pack_roster_stage.sh STAGE_ROSTER_DIR | tar -xf - -C DESTINATION
set -euo pipefail
dir="${1:?usage: pack_roster_stage.sh STAGE_ROSTER_DIR}"
[[ -d "$dir" ]] || { echo "not a folder: $dir" >&2; exit 1; }
cd "$dir"
find . -maxdepth 1 -type f ! -name '._*' -print0 | tar --null -T - -cf -
