#!/usr/bin/env bash
# Migrate Desktop HART ops tree into a new hart-ops repo (phase 1).
set -euo pipefail

DESKTOP_CARDS="${DESKTOP_CARDS:-$HOME/Desktop/HART/Car Cards}"
DESKTOP_IND="${DESKTOP_IND:-$HOME/Desktop/HART/Industries}"
TARGET="${TARGET:-$HOME/hart-ops}"

if [[ ! -d "$DESKTOP_CARDS/card_pipeline" ]]; then
  echo "Missing Desktop Car Cards at $DESKTOP_CARDS" >&2
  exit 1
fi

mkdir -p "$TARGET"

rsync -a --delete \
  --exclude '.DS_Store' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'card_pipeline/output/' \
  --exclude 'CarImagesFinal/' \
  --exclude 'CarImagesCardFill/' \
  --exclude 'Images/' \
  --exclude 'archive/' \
  --exclude 'sts-docker/' \
  --exclude 'sts-docker-helpers/' \
  --exclude 'sts-backups/' \
  --exclude 'OcrZoom/' \
  "$DESKTOP_CARDS/card_pipeline/" "$TARGET/card_pipeline/"

rsync -a --delete \
  --exclude '.DS_Store' \
  "$DESKTOP_CARDS/data/" "$TARGET/data/"

rsync -a --delete \
  --exclude '.DS_Store' \
  --exclude '__pycache__/' \
  "$DESKTOP_CARDS/publications/" "$TARGET/publications/"

rsync -a --delete \
  --exclude '.DS_Store' \
  "$DESKTOP_CARDS/docs/" "$TARGET/docs/published/"

rsync -a --delete \
  --exclude '.DS_Store' \
  "$DESKTOP_CARDS/operator_logos/" "$TARGET/operator_logos/"

if [[ -d "$DESKTOP_IND" ]]; then
  rsync -a --delete \
    --exclude '.DS_Store' \
    --exclude '__pycache__/' \
    "$DESKTOP_IND/" "$TARGET/industries/"
fi

echo "Migrated to $TARGET"
