#!/usr/bin/env bash
# Install HART JMRI web home override (STS link) into local preference:/profile web/.
# SoR: cats/resources/jmri-web/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${ROOT}/cats/resources/jmri-web"
HOME_HTML="${SRC}/servlet/home/Home.html"
STS_HTML="${SRC}/sts.html"

if [[ ! -f "$HOME_HTML" ]]; then
  echo "Missing $HOME_HTML" >&2
  exit 1
fi

install_into() {
  local dest_root="$1"
  [[ -d "$dest_root" ]] || return 0
  mkdir -p "${dest_root}/web/servlet/home"
  cp -f "$HOME_HTML" "${dest_root}/web/servlet/home/Home.html"
  if [[ -f "$STS_HTML" ]]; then
    cp -f "$STS_HTML" "${dest_root}/web/sts.html"
  fi
  echo "Installed JMRI web STS override -> ${dest_root}/web"
}

# macOS JMRI preferences profiles
if [[ -d "${HOME}/Library/Preferences/JMRI" ]]; then
  for d in "${HOME}/Library/Preferences/JMRI"/*.jmri; do
    [[ -d "$d" ]] || continue
    install_into "$d"
  done
fi

# Linux / Pi: ~/.jmri profiles + JMRI_UserFiles (preference:)
if [[ -d "${HOME}/.jmri" ]]; then
  for d in "${HOME}/.jmri"/*.jmri; do
    [[ -d "$d" ]] || continue
    install_into "$d"
  done
fi
if [[ -d "${HOME}/JMRI_UserFiles" ]]; then
  install_into "${HOME}/JMRI_UserFiles"
fi

echo "DONE — refresh JMRI web home (or restart Digicon/PanelPro web server)"
