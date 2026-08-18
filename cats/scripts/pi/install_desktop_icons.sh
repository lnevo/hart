#!/usr/bin/env bash
# Pi desktop: CATS CTC (HOLD_ONLY) + CATS ABS (stock, no hold). Removes ABS-RO / CTC SML / legacy.
set -euo pipefail
HART="${HART:-/home/pi/hart}"
SRC="$HART/cats/scripts/pi"
DESKTOP="${HOME}/Desktop"
APPS="${HOME}/.local/share/applications"
mkdir -p "$DESKTOP" "$APPS"

for pair in "CATS_CTC.desktop:CATS CTC.desktop" "CATS_ABS.desktop:CATS ABS.desktop"; do
  src="${pair%%:*}"
  dst="${pair##*:}"
  if [[ ! -f "$SRC/$src" ]]; then
    echo "Missing $SRC/$src" >&2
    exit 1
  fi
  cp "$SRC/$src" "$DESKTOP/$dst"
  cp "$SRC/$src" "$APPS/$dst"
  rm -f "$DESKTOP/$src" "$APPS/$src"
done

rm -f \
  "$DESKTOP/CATS_ABS-RO.desktop" \
  "$DESKTOP/CATS ABS-RO.desktop" \
  "$DESKTOP/CATS_CTC_SML.desktop" \
  "$DESKTOP/CATS CTC SML.desktop" \
  "$APPS/CATS_ABS-RO.desktop" \
  "$APPS/CATS_CTC_SML.desktop" \
  "$APPS/CATS.desktop"

chmod +x "$DESKTOP/CATS CTC.desktop" "$DESKTOP/CATS ABS.desktop" 2>/dev/null || true
echo "Pi Desktop: CATS CTC + CATS ABS"
