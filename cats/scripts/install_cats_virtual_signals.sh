#!/usr/bin/env bash
# Install CATS Virtual signal system into a JMRI install (xml/signals/cats-masts).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/cats/resources/signals/cats-masts"
JMRI_HOME="${1:-${JMRI_HOME:-/Applications/JMRI}}"
DST="$JMRI_HOME/xml/signals/cats-masts"
if [[ ! -d "$SRC" ]]; then
  echo "Missing $SRC" >&2
  exit 1
fi
if [[ ! -d "$JMRI_HOME/xml/signals" ]]; then
  echo "Not a JMRI install: $JMRI_HOME" >&2
  exit 1
fi
mkdir -p "$DST"
cp -f "$SRC"/aspects.xml "$SRC"/appearance-cats-virtual.xml \
  "$SRC"/appearance-cats-virtual-2.xml "$SRC"/index.shtml "$DST/"
echo "Installed CATS Virtual signals -> $DST"
echo "Restart JMRI/CATS to load the signal system."
