#!/usr/bin/env bash
# Install the six Operations Pro files on this host (ADR-015).
#   install_ops_files.sh <source dir> <operations dir> [--guard]
# --guard is for the Pi, where JMRI writes session state into these files: stop
# if they changed since the last deploy or pull. Set HART_OVERWRITE_OPS=1 to
# discard those changes. A running JMRI would overwrite the files, so skip them.
set -euo pipefail
SRC="$1"
DEST="$2"
GUARD="${3:-}"
FILES=(Operations.xml OperationsCarRoster.xml OperationsEngineRoster.xml
       OperationsLocationRoster.xml OperationsRouteRoster.xml OperationsTrainRoster.xml)
STAMP="$DEST/.deployed.sha256"

hash_of() {
  local dir="$1" f
  (for f in "${FILES[@]}"; do cat "$dir/$f" 2>/dev/null || true; done) \
    | { command -v sha256sum >/dev/null && sha256sum || shasum -a 256; } | cut -d' ' -f1
}

mkdir -p "$DEST"
want="$(hash_of "$SRC")"
have="$(hash_of "$DEST")"
if [[ "$want" == "$have" ]]; then
  echo "$want" >"$STAMP"
  echo "Operations files already current -> $DEST"
  exit 0
fi
if pgrep -f 'java .*(apps\.PanelPro\.PanelPro|apps\.DecoderPro|cats\.apps\.Crandic)' >/dev/null 2>&1; then
  echo "SKIP Operations files: JMRI is running and would overwrite them. Deploy again with it closed."
  exit 0
fi
if [[ "$GUARD" == "--guard" && -f "$STAMP" && "$have" != "$(cat "$STAMP")" \
      && "${HART_OVERWRITE_OPS:-0}" != "1" ]]; then
  echo "STOP: $DEST changed since the last deploy. Run make ops-pull to bring the changes into the repo, or set HART_OVERWRITE_OPS=1." >&2
  exit 1
fi
backup="$DEST/backups/pre_deploy_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup"
for f in "${FILES[@]}"; do
  [[ -f "$DEST/$f" ]] && cp -f "$DEST/$f" "$backup/"
  cp -f "$SRC/$f" "$DEST/$f"
done
echo "$want" >"$STAMP"
echo "Operations files -> $DEST (backup $backup)"
