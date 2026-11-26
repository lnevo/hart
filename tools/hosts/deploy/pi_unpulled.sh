#!/usr/bin/env bash
# Read-only: what the Pi holds that a deploy would replace, as the deploy gate sees it (pi_unpulled_words, common.sh):
# one word per changed set, "ops" (Operations Pro files, make ops-pull), "tables" (a PanelPro Store,
# make tables-pull-pi) and "roster" (the DecoderPro roster, make roster-pull), nothing when all are clean. It never
# pulls, quits PanelPro or stops a deploy; make orient's "waiting to ingest" lines run it, so its ssh waits 10 s for
# the Pi (ConnectTimeout, as deploy_status.sh), not the gate's 15. Exit 0 when the Pi
# answered; otherwise ssh's status (255: the Pi did not answer) or the check's own.
# Usage: tools/hosts/deploy/pi_unpulled.sh
set -euo pipefail
[[ $# -eq 0 ]] || { echo "usage: $0 (no arguments)" >&2; exit 2; }
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
ssh_opts_init
pi_unpulled_words
