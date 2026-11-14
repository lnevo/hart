#!/usr/bin/env bash
# Install HART JMRI web home override (STS and mimic links) into local preference:/profile web/.
# SoR: jmri/resources/jmri-web/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${ROOT}/jmri/resources/jmri-web"
# Hosts receive it at cats/resources/jmri-web in the deploy package.
[[ -d "$SRC" ]] || SRC="${ROOT}/cats/resources/jmri-web"
HOME_HTML="${SRC}/servlet/home/Home.html"

if [[ ! -f "$HOME_HTML" ]]; then
  echo "Missing $HOME_HTML" >&2
  exit 1
fi

install_into() {
  local dest_root="$1"
  [[ -d "$dest_root" ]] || return 0
  mkdir -p "${dest_root}/web/servlet/home"
  cp -f "$HOME_HTML" "${dest_root}/web/servlet/home/Home.html"
  # Windows sets HART_APPS_HOST to name the Pi; empty (Pi, Mac) follows the page's own host.
  if [[ -n "${HART_APPS_HOST:-}" ]]; then
    sed -i.tmp "s/var HART_APPS_HOST = \"\";/var HART_APPS_HOST = \"${HART_APPS_HOST}\";/" \
      "${dest_root}/web/servlet/home/Home.html" && rm -f "${dest_root}/web/servlet/home/Home.html.tmp"
  fi
  # The Mac sets HART_MIMIC_PORT so the mimic link opens its own mimic server.
  if [[ -n "${HART_MIMIC_PORT:-}" ]]; then
    [[ "$HART_MIMIC_PORT" =~ ^[0-9]+$ ]] || { echo "HART_MIMIC_PORT must be a number" >&2; exit 1; }
    sed -i.tmp "s/var HART_MIMIC_PORT = \"\";/var HART_MIMIC_PORT = \"${HART_MIMIC_PORT}\";/" \
      "${dest_root}/web/servlet/home/Home.html" && rm -f "${dest_root}/web/servlet/home/Home.html.tmp"
  fi
  # The Mac sets HART_PI_HOST so the speed-match link, a Pi-only page, names the Pi.
  if [[ -n "${HART_PI_HOST:-}" ]]; then
    [[ "$HART_PI_HOST" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "HART_PI_HOST must be a host name" >&2; exit 1; }
    sed -i.tmp "s/var HART_PI_HOST = \"\";/var HART_PI_HOST = \"${HART_PI_HOST}\";/" \
      "${dest_root}/web/servlet/home/Home.html" && rm -f "${dest_root}/web/servlet/home/Home.html.tmp"
  fi
  rm -f "${dest_root}/web/sts.html"
  echo "Installed JMRI web home override -> ${dest_root}/web"
  # LCOS mimic page (served at /web/mimic/). Only with its generated layout, which the
  # deploy builds into the staged copy; the Mac keeps the tools/mqtt-mimic server.
  if [[ -f "${SRC}/mimic/index.html" && -f "${SRC}/mimic/mimic_layout.json" \
        && -f "${SRC}/mimic/mimic.css" && -f "${SRC}/mimic/mimic_view.js" ]]; then
    mkdir -p "${dest_root}/web/mimic"
    cp -f "${SRC}/mimic/index.html" "${SRC}/mimic/mimic.css" "${SRC}/mimic/mimic_view.js" \
      "${SRC}/mimic/mimic_layout.json" "${dest_root}/web/mimic/"
    echo "Installed LCOS mimic page -> ${dest_root}/web/mimic"
  fi
}

install_into "${HOME}/JMRI_UserFiles"

echo "DONE — refresh JMRI web home (or restart Digicon/PanelPro web server)"
