#!/usr/bin/env bash
# Runs on the Pi (piped over ssh by sync_roster_from_pi.sh --status) and on the Mac in place. Prints one line per
# DecoderPro roster file in USERFILES, "<sha256> <path>", path relative to USERFILES: roster.xml and every file
# under roster/ but macOS AppleDouble files (._*), sorted. Nothing when there is no roster. It only reads.
# Usage: roster_digest.sh USERFILES
set -euo pipefail
uf="${1:?usage: roster_digest.sh USERFILES}"
[[ -d "$uf" ]] || exit 0
cd "$uf"
sha() { { command -v sha256sum >/dev/null && sha256sum || shasum -a 256; } | cut -d' ' -f1; }
{
  [[ ! -f roster.xml ]] || echo roster.xml
  [[ ! -d roster ]] || find roster -type f ! -name '._*'
} | LC_ALL=C sort | while IFS= read -r f; do
  printf '%s %s\n' "$(sha <"$f")" "$f"
done
