#!/usr/bin/env bash
# A PanelPro round trip of this checkout's generated tables.xml (ADR-029 gate 2): PanelPro loads it, JMRI
# derives the block paths from the panel, the configuration and panels are stored to a temporary file as the
# PanelPro menu "Store Configuration and Panels" does, PanelPro quits, and the Store and the generated file
# must be the same bytes once both are normalised (hartlib.tables_normal.normalise_store: the envelope and the
# derived block paths out, the panel past what a Store rewrites). Every staging block must have a derived path.
# It prints PASS or FAIL, then runs tools/audit/check_layout_facts.py --tables on the Store, the one place the
# stored-path leg check runs since tables.xml stores no paths; the run fails if either fails.
#
#   tools/hosts/run_panelpro_roundtrip.sh            # exit 0 when it passes, 1 when it fails or cannot run
#
# The Store is kept as roundtrip-<date>.xml in the pulled folder (<main checkout>/media/pulled-stores, or HART_PULLED_DIR;
# gitignored, shared by every worktree, profile_tables_guard.sh hart_pulled_dir) and the block path counts beside it (.paths.tsv), for a look and for split_store.py. It refuses while
# PanelPro, DecoderPro or CATS is open. The run lifecycle (profile backup and restore, Start Up items that run
# code off, stopping PanelPro on a timeout or a signal) is tools/hosts/panelpro_session.sh; PanelPro still
# connects to MQTT, so run it with the layout idle. HART_ROUNDTRIP_WAIT (seconds, default 180) bounds the
# waits for the panel and for steady paths.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
source "$ROOT/tools/hosts/panelpro_session.sh"
refuse_hart_tables "run the PanelPro round trip"
pp_profile
SCRIPT="$ROOT/jmri/layouts/hart/scripts/panelpro_roundtrip.py"
TABLES="$ROOT/jmri/layouts/hart/output/tables.xml"
LOG="${HART_ROUNDTRIP_LOG:-/tmp/hart_panelpro_roundtrip.log}"

pp_refuse_running "Quit PanelPro, DecoderPro and CATS first: the round trip needs this profile alone."

PULLED="$(hart_pulled_dir)" || exit 1
STORE="$PULLED/roundtrip-$(date +%Y%m%d-%H%M%S).xml"
COUNTS="$STORE.paths.tsv"
MARKER="$(mktemp "${TMPDIR:-/tmp}/hart_roundtrip_marker.XXXXXX")"
rm -f "$MARKER"
PP_TMP_FILES+=("$MARKER")

pp_begin "$SCRIPT"
export HART_ROUNDTRIP_STORE="$STORE"
export HART_ROUNDTRIP_PATHS="$COUNTS"
export HART_ROUNDTRIP_MARKER="$MARKER"
export HART_ROUNDTRIP_WAIT="${HART_ROUNDTRIP_WAIT:-180}"

echo "Launching PanelPro for the round trip of ${TABLES#"$ROOT"/} (MQTT still connects)..."
pp_launch "$LOG"
rc=0
pp_wait_marker "$MARKER" "${HART_PANELPRO_TIMEOUT:-$((HART_ROUNDTRIP_WAIT + 120))}" 2 || rc=$?
if (( rc != 0 )); then
  echo "The round trip did not finish (PanelPro quit or timed out). Log: $LOG" >&2
  tail -40 "$LOG" >&2 || true
  exit 1
fi
status="$(head -1 "$MARKER")"
detail="$(sed -n '2p' "$MARKER")"
pp_wait_exit "${HART_PANELPRO_EXIT_WAIT:-60}" || { echo "PanelPro did not quit after the round trip; stopping it" >&2; pp_stop_jmri; }
echo "PanelPro: $status $detail"
if [[ "$status" != "ok" ]]; then
  tail -60 "$LOG" >&2 || true
  exit 1
fi
if [[ ! -s "$STORE" || ! -s "$COUNTS" ]]; then
  echo "The round trip reported ok but left no Store or block path counts ($STORE). Log: $LOG" >&2
  exit 1
fi
echo "Store kept as $STORE"
PYTHONPATH="$ROOT/tools/hartlib/src" python3 -m hartlib.tables_roundtrip roundtrip \
  --store "$STORE" --paths "$COUNTS" --generated "$TABLES"
# The Store holds the block paths JMRI derived, so the stored-path leg check of check_layout_facts.py, which the
# generated file (no stored paths) cannot run, runs here.
echo "Switch legs against the Store's derived block paths:"
python3 "$ROOT/tools/audit/check_layout_facts.py" --tables "$STORE" \
  || { echo "FAIL: check_layout_facts.py --tables $STORE" >&2; exit 1; }
