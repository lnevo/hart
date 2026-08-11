#!/usr/bin/env bash
# Install CATS Virtual signal system into a JMRI install (xml/signals/cats-masts).
# Also refreshes the active JMRI profile copy when present. Profile resources
# override the app install; a stale Aaron Default (no show elements) causes
# SignalHeadSignalMast "1 heads but only 0 settings" floods / hangs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/cats/resources/signals/cats-masts"
JMRI_HOME="${1:-${JMRI_HOME:-/Applications/JMRI}}"
DST="$JMRI_HOME/xml/signals/cats-masts"

install_into() {
  local dest="$1"
  mkdir -p "$dest"
  cp -f "$SRC"/aspects.xml "$SRC"/appearance-cats-virtual.xml \
    "$SRC"/appearance-cats-virtual-2.xml "$SRC"/appearance-cats-virtual-3.xml \
    "$SRC"/index.shtml "$dest/"
  echo "Installed CATS Virtual signals -> $dest"
}

if [[ ! -d "$SRC" ]]; then
  echo "Missing $SRC" >&2
  exit 1
fi
if [[ ! -d "$JMRI_HOME/xml/signals" ]]; then
  echo "Not a JMRI install: $JMRI_HOME" >&2
  exit 1
fi
install_into "$DST"

# Profile override (Mac / Windows prefs; Linux ~/.jmri)
for pref in \
  ${JMRI_PROFILE:+"$JMRI_PROFILE"} \
  "$HOME/Library/Preferences/JMRI/My_JMRI_Railroad.jmri" \
  "$HOME/JMRI/My_JMRI_Railroad.jmri" \
  "$HOME/.jmri/My_JMRI_Railroad.jmri"
do
  [[ -d "$pref" ]] || continue
  install_into "$pref/resources/signals/cats-masts"
done

echo "Restart JMRI/CATS to load the signal system."
