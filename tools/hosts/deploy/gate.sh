#!/usr/bin/env bash
# Deploy step 1: every check, before anything is sent to a host or installed on this Mac. Run by
# tools/hosts/sync_hart_package.sh; it can run alone to check a deploy that is not yet wanted.
#
# Usage: gate.sh [--pi] [--win] [--mac] [--dry-run] [--check-only] [--stage-only] [--stage-dir DIR]
#   --pi --win   the hosts the deploy names (checks that need a host only run for those)
#   --mac        the Mac install will follow (its Store check runs)
#   --dry-run    no ssh, no Mac check: the local checks only
#   --check-only the host checks (ssh answers, the Pi's unpulled files) and stop there
#   --stage-only the local checks only, for a staging run (implies --dry-run)
#   --stage-dir  G7 builds the package into DIR and keeps it, for the run to ship (else a folder thrown away)
#
# Order (the first failure stops it; nothing has changed on any host or on the Mac):
#   G0  the HART_TABLES and unrestored-profile refusals, the live paths list, the parked features; a real deploy to
#       a host ships origin/main itself (HART_ALLOW_UNMERGED=1 overrides); main's push run for the commit is not
#       red (G0c, ci_pass.py --main-red; a dry run asks too)
#   G1  one ssh no-op to each host named
#   G2  the Pi's unpulled files (Operations Pro files, a PanelPro Store, the DecoderPro roster)
#   G3  the panel audit          G4  tables.xml is what the generator writes     G5  the Digicon mast check
#       (G4 is skipped for a real deploy to a host when CI's full check.sh pass covers the commit shipped:
#       ci_pass.py; it says which way it went)
#   G6  the Mac's own Store check
#   G7  a trial staging into a folder that is thrown away (a real deploy to a host only)
#   G8  Windows can take the package: scp and tar here, a temp folder and tar there (ssh read-only)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
DO_MAC_WEB=0
CHECK_ONLY=0
STAGE_ONLY=0
KEEP_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pi) DO_PI=1 ;;
    --win) DO_WIN=1 ;;
    --mac) DO_MAC_WEB=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --check-only) CHECK_ONLY=1 ;;
    --stage-only) STAGE_ONLY=1; DRY_RUN=1; DO_MAC_WEB=0 ;;
    --stage-dir) [[ $# -ge 2 && -n "$2" ]] || { echo "gate.sh: --stage-dir needs a folder" >&2; exit 1; }; KEEP_DIR="$2"; shift ;;
    *) echo "gate.sh: unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

TRIAL=""        # the trial staging folder, when it is not kept
# RESTART (common.sh) is 1 once a host answered: a PanelPro quit for this deploy comes back if a later check stops the run
on_exit() {
  local rc=$?
  [[ -z "$TRIAL" ]] || rm -rf "$TRIAL"
  if [[ "$RESTART" -eq 1 && "$rc" -ne 0 ]]; then
    RESTART=0
    pi_restart_if_due
  fi
  ssh_mux_close
}
trap on_exit EXIT

# ---- G0: before anything (no ssh) ----
refuse_before_changing
load_parked
# The shipped paths are listed in tools/hosts/live_paths.txt (deploy_status.sh counts commits that touch them).
# A run that stages or deploys stops if the list names a path that is gone, so the list cannot drift from the
# checkout; --help, --check-only and --dry-run only read and are not blocked.
if [[ "$CHECK_ONLY" -eq 0 && "$DRY_RUN" -eq 0 || "$STAGE_ONLY" -eq 1 ]]; then
  python3 "$ROOT/tools/hosts/live_paths.py" check || exit 1
fi
deploy_facts
# G0b: a real deploy to a host ships origin/main itself (check_on_main, common.sh); the Mac alone is not checked
if [[ ( "$DO_PI" -eq 1 || "$DO_WIN" -eq 1 ) && "$DRY_RUN" -eq 0 && "$CHECK_ONLY" -eq 0 ]]; then
  check_on_main || exit 1
fi

# G0c: main is not red. ci_pass.py --main-red decides and prints the line; only its exit 4 (the commit's push run of
# check.yml on main finished red) stops the deploy, before any ssh. Any other exit, a crash included, goes on; when
# the script did not end with its verdict (another exit, or no line), the gate says so in a line of its own. A
# deploy or dry run to the Pi or Windows asks; a redeploy, --check-only, --stage-only and the Mac alone do not.
main_not_red() {
  local line rc=0
  line="$(python3 "$DEPLOY_STEPS_DIR/ci_pass.py" --main-red --commit "$DEPLOY_COMMIT")" || rc=$?
  if [[ "$rc" -eq 4 ]]; then echo "$line" >&2; return 1; fi
  [[ -z "$line" ]] || echo "$line"
  if [[ "$rc" -ne 0 || -z "$line" ]]; then
    echo "main red check: ci_pass.py --main-red exited $rc without its verdict (its error is above); not blocking"
  fi
}
if [[ ( "$DO_PI" -eq 1 || "$DO_WIN" -eq 1 ) && "$CHECK_ONLY" -eq 0 && "$STAGE_ONLY" -eq 0 && -z "${HART_REDEPLOY_FROM:-}" ]]; then
  main_not_red || exit 1
fi
ssh_mux_open

# ---- G1: one ssh no-op to each host named (preflight_hosts, common.sh); a dry run and --stage-only skip it ----
if [[ "$DRY_RUN" -eq 0 ]]; then
  preflight_hosts
  [[ "$DO_PI" -eq 0 ]] || RESTART=1
fi

# ---- G2: the Pi's unpulled files (check_pi_unpulled, common.sh) ----
if [[ "$DO_PI" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  check_pi_unpulled
fi
if [[ "$CHECK_ONLY" -eq 1 ]]; then
  [[ "$DO_PI" -eq 0 ]] || echo "Pi check: nothing unpulled."
  echo "Host check: every host named answered over ssh."
  RESTART=0
  exit 0
fi

# ---- G3: the panel audit ----
PANEL_AUDIT="$ROOT/jmri/layouts/hart/scripts/audit_panel_contracts.py"
if [[ -n "$TABLES" && -f "$PANEL_AUDIT" ]]; then
  # The audit places masts by the schematic-maps plugin's slot rule (the submodule, or SCHEMATIC_PLUGIN, which
  # redeploy_commit.sh sets). Stop here with the fix rather than fail inside the audit.
  if [[ -z "${SCHEMATIC_PLUGIN:-}" && ! -f "$ROOT/external/model-railroad-skills/plugins/schematic-maps/schematic/slots.py" ]]; then
    echo "the panel audit needs the schematic-maps plugin: run git submodule update --init external/model-railroad-skills, or set SCHEMATIC_PLUGIN" >&2
    exit 1
  fi
  python3 "$PANEL_AUDIT" --strict
fi

# g4_covered_by_ci: 0 when CI's full check.sh pass covers the commit shipped (ci_pass.py), so G4's regeneration is
# skipped; 1 otherwise. It prints which way it went. Only a real deploy to the Pi or Windows asks (the one run that
# held its commit to origin/main); a dry run, --stage-only and the Mac alone run G4 and need no network.
g4_covered_by_ci() {
  if [[ ( "$DO_PI" -eq 0 && "$DO_WIN" -eq 0 ) || "$DRY_RUN" -eq 1 ]]; then
    echo "ran G4: a dry run, a staging run or the Mac alone does not ask CI"
    return 1
  fi
  local verdict ci_rc=0
  verdict="$(python3 "$DEPLOY_STEPS_DIR/ci_pass.py" --commit "$DEPLOY_COMMIT")" || ci_rc=$?
  case "$ci_rc" in
    0) echo "$verdict"; return 0 ;;
    1|3) echo "${verdict:-ran G4: the CI pass check said no and gave no reason (exit $ci_rc)}"; return 1 ;;
    *) echo "ran G4: the CI pass check failed (exit $ci_rc)${verdict:+: $verdict}"; return 1 ;;
  esac
}

# ---- G4: tables.xml is generated (ADR-029, R9c): ship it only when it is what build_tables.py writes from its
# sources, and with the Digicon masts' Signal Mast Logic stored disabled. A redeploy of a commit before R9c has no
# generator.
TABLES_BUILD="$ROOT/tools/schematic/build_tables.py"
if [[ -n "$TABLES" && -f "$TABLES_BUILD" && -n "${HART_REDEPLOY_FROM:-}" ]]; then
  # A redeploy runs this script from an old commit's worktree with the checkout's plugin (redeploy_commit.sh), so
  # a regeneration would draw with another plugin than the commit's and read STALE falsely: the commit's tables.xml
  # was checked when it was committed. The Digicon check below still runs.
  echo "Redeploy of an older commit: not regenerating tables.xml to check it (it was checked when committed); the Digicon check still runs."
elif [[ -n "$TABLES" && -f "$TABLES_BUILD" ]]; then
  # A real deploy to a host ships origin/main itself (G0b), and CI ran the full check.sh, the same
  # build_tables.py --check included, on that commit: ci_pass.py reads that record and the regeneration is skipped
  # when it covers the exact commit and clean checkout shipped. Any doubt runs G4.
  tables_rc=0
  if ! g4_covered_by_ci; then
    SCHEMATIC_REQUIRED=1 python3 "$TABLES_BUILD" --check || tables_rc=$?
  fi
  if (( tables_rc == 3 )); then
    echo "STOP: the tables check needs the schematic-maps plugin at its pin: run git submodule update --init external/model-railroad-skills, or set SCHEMATIC_PLUGIN. Nothing was sent to any host." >&2
    exit 1
  elif (( tables_rc == 2 )); then
    echo "STOP: tools/schematic/build_tables.py cannot make tables.xml from its sources: fix the source error above, or rerun discovery (jmri/layouts/hart/scripts/run_sml_discover.sh) when it names the Signal Mast Logic. Nothing was sent to any host." >&2
    exit 1
  elif (( tables_rc != 0 )); then
    echo "STOP: tables.xml is not what tools/schematic/build_tables.py writes from its sources; run make panels (or the script) and commit, then deploy. Nothing was sent to any host." >&2
    exit 1
  fi
  # G4b: the panel and the CATS desks are the ones the owner approved (check_approved.py, as make panels and check.sh
  # check them)
  if ! python3 "$ROOT/tools/schematic/check_approved.py" --check; then
    echo "STOP: the Layout Editor panel or a CATS desk is not the one the owner approved (check_approved.py names it above); get the owner's approval and record it (check_approved.py --approve <key>), then deploy. Nothing was sent to any host." >&2
    exit 1
  fi
fi
# ---- G5 ----
if [[ -n "$TABLES" ]] && ! python3 "$ROOT/jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py" --check --panel "$TABLES"; then
  echo "STOP: a Digicon mast's Signal Mast Logic is stored enabled in tables.xml; run python3 tools/schematic/build_tables.py and commit, then deploy. Nothing was sent to any host." >&2
  exit 1
fi
# The stamp names the tables shipped and whether they differ from the committed file (an uncommitted change).
tables_facts 1

# ---- G6: this Mac's own Store check, before the Mac install changes anything ----
if [[ "$DO_MAC_WEB" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  check_mac_store || exit 1
fi

# ---- G7: the package builds. stage.sh builds it into --stage-dir (kept: the run ships that same folder, so the
# package is built once) or, run alone, into a folder that is thrown away. ----
if [[ ( "$DO_PI" -eq 1 || "$DO_WIN" -eq 1 ) && "$DRY_RUN" -eq 0 ]]; then
  if [[ -n "$KEEP_DIR" ]]; then
    stage_to="$KEEP_DIR"
  else
    TRIAL="$(mktemp -d)"
    stage_to="$TRIAL/stage"
  fi
  trial_flags=()
  [[ "$DO_PI" -eq 0 ]] || trial_flags+=(--pi)
  [[ "$DO_WIN" -eq 0 ]] || trial_flags+=(--win)
  if ! bash "$DEPLOY_STEPS_DIR/stage.sh" "${trial_flags[@]}" "$stage_to" >/dev/null; then
    echo "STOP: the host package cannot be built (see above). Nothing was sent to any host, and the Mac install did not run." >&2
    exit 1
  fi
  [[ -n "$KEEP_DIR" ]] || { rm -rf "$TRIAL"; TRIAL=""; }
fi

# ---- G8: Windows can take the package (check_windows_can_take_package, common.sh; nothing in a dry run) ----
check_windows_can_take_package
RESTART=0
exit 0
