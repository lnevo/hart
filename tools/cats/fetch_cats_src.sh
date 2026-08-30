#!/usr/bin/env bash
# Clone CATS upstream source (open source) into tools/cats/src-repo.
# That is the SoR for reading CATS Java. Do NOT explode cats.jar into cats/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="$ROOT/tools/cats/src-repo"
URL="${CATS_SRC_GIT:-https://bitbucket.org/Kb0oys/cats.git}"

if [[ -d "$DEST/.git" ]]; then
  echo "Updating $DEST"
  git -C "$DEST" pull --ff-only
else
  echo "Cloning $URL → $DEST"
  git clone "$URL" "$DEST"
fi
echo "CATS source → $DEST"
echo "Read e.g. $DEST/cats/layout/items/TrackGroup.java"
echo "Do not copy or jar-xf classes into hart cats/ (that folder is HART panels/scripts)."
