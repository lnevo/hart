#!/usr/bin/env bash
# The one hash of a DecoderPro roster (ADR-039 amendment 2026-11-26): roster.xml and the roster/ files it names (the
# fileName of each <locomotive>), each file's sha256 and its path relative to the folder, one line each in C sort
# order, hashed together; a named file that is missing hashes as "missing". Files roster.xml does not name are not
# part of it: JMRI's backups (*.bak), macOS litter, and old entry files left behind by a rename (the Mac's
# JMRI_UserFiles/roster holds 13 such). The deploy (tools/hosts/deploy/common.sh, on the repo master
# jmri/layouts/hart/roster), the Pi check (unpulled_changes.sh), the install (install_roster.sh) and the pull
# (tools/ops/pull_roster.sh) all use this, so they agree on what "the same roster" means.
#
# Sourced, it defines roster_files and roster_sha; run, it prints the hash of the folder given:
#   roster_sha.sh DIR     prints the hash, or "none" when DIR has no roster.xml (exit 0 both); exit 1 when
#                         roster.xml names a file outside roster/ (a path, not a plain *.xml name)
# unpulled_changes.sh runs piped over ssh with this file in front of it, so it must define only functions there.

# roster_files DIR: the file names DIR/roster.xml names, sorted and unique. Fails on a name that is not a plain *.xml.
roster_files() {
  local dir="${1:?roster_files needs a folder}" name names
  [[ -f "$dir/roster.xml" ]] || { echo "no roster.xml in $dir" >&2; return 1; }
  names="$(sed -n 's/.*<locomotive [^>]*fileName="\([^"]*\)".*/\1/p' "$dir/roster.xml" | LC_ALL=C sort -u)"
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    if [[ "$name" == */* || "$name" == .* || "$name" != *.xml ]]; then
      echo "roster.xml in $dir names '$name', which is not a plain roster/*.xml file name" >&2
      return 1
    fi
    echo "$name"
  done <<<"$names"
}

roster_sha() {
  local dir="${1:?roster_sha needs a folder}" names name
  [[ -f "$dir/roster.xml" ]] || { echo none; return 0; }
  names="$(roster_files "$dir")" || return 1
  {
    printf '%s roster.xml\n' "$(roster_sha_of <"$dir/roster.xml")"
    while IFS= read -r name; do
      [[ -n "$name" ]] || continue
      if [[ -f "$dir/roster/$name" ]]; then
        printf '%s roster/%s\n' "$(roster_sha_of <"$dir/roster/$name")" "$name"
      else
        printf 'missing roster/%s\n' "$name"
      fi
    done <<<"$names"
  } | roster_sha_of
}
roster_sha_of() { { command -v sha256sum >/dev/null && sha256sum || shasum -a 256; } | cut -d' ' -f1; }

if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
  [[ $# -eq 1 ]] || { echo "usage: roster_sha.sh DIR" >&2; exit 2; }
  [[ -d "$1" ]] || { echo "roster_sha.sh: no folder $1" >&2; exit 2; }
  roster_sha "$1"
fi
